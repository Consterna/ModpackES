"""Medición de calidad con un banco de referencia: sirve para comparar motores, modelos y prompts.

Las métricas son automáticas y tienen límites: chrF (Popović, WMT 2015) mide cuánto se parece cada traducción a
una referencia por n-gramas de caracteres, así que una traducción correcta pero distinta de la referencia
también baja el puntaje. Por eso se mira junto con lo que no depende de la referencia: textos aceptados por
las reglas, términos del glosario respetados y textos que quedaron en inglés.
"""

from __future__ import annotations

import json
import random
import re
import statistics
import time
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..motores import fabrica
from ..motores.base import Motor
from ..nucleo import terminos as terminos_repetidos
from ..nucleo.ejemplos import CANTIDAD_EN_LA_APP, Ejemplos
from ..nucleo.glosario import Glosario
from ..nucleo.memoria import Memoria
from ..nucleo.traductor import Traductor
from ..proceso import Informe, InformeModulo
from . import revision
from .calidad import sale_el_termino, validar

_N_MAXIMO, _BETA = 6, 2.0


@dataclass(frozen=True, slots=True)
class Caso:
    ambito: str
    original: str
    referencia: str
    pista: str = ""  #: de dónde sale el texto (clave y tipo), como lo manda la app


@dataclass(slots=True)
class Banco:
    dialecto: str
    glosario: dict[str, str]
    casos: list[Caso]
    #: Traducciones ya hechas de otros textos del mismo modpack ({inglés: español}); guían al motor
    ejemplos: dict[str, str] = field(default_factory=dict[str, str])
    #: Nombres del propio juego ({inglés: español}, también los que no se traducen): entran como oficiales,
    #: igual que en la app. Vacío en los bancos viejos.
    juego: dict[str, str] = field(default_factory=dict[str, str])

    @classmethod
    def leer(cls, ruta: Path) -> Banco:
        datos: Any = json.loads(ruta.read_text(encoding="utf-8"))
        casos = [
            Caso(str(t["ambito"]), str(t["original"]), str(t["referencia"]), str(t.get("pista", "")))
            for t in datos["textos"]
        ]
        ejemplos = {str(k): str(v) for k, v in datos.get("ejemplos", {}).items()}
        juego = {str(k): str(v) for k, v in datos.get("juego", {}).items()}
        return cls(
            str(datos.get("dialecto", "es_mx")),
            {str(k): str(v) for k, v in datos["glosario"].items()},
            casos,
            ejemplos,
            juego,
        )


def _ngramas(texto: str, n: int) -> Counter[str]:
    sin_espacios = re.sub(r"\s+", "", texto)
    return Counter(sin_espacios[i : i + n] for i in range(len(sin_espacios) - n + 1))


def chrf(hipotesis: str, referencia: str) -> float:
    """chrF de una oración (0 a 100): F-beta (beta 2) de n-gramas de caracteres de 1 a 6, sin espacios."""
    precisiones: list[float] = []
    recalls: list[float] = []
    for n in range(1, _N_MAXIMO + 1):
        h, r = _ngramas(hipotesis, n), _ngramas(referencia, n)
        if not h or not r:
            continue
        comunes = sum((h & r).values())
        precisiones.append(comunes / sum(h.values()))
        recalls.append(comunes / sum(r.values()))
    if not precisiones:
        return 100.0 if hipotesis.strip() == referencia.strip() else 0.0
    p, r = sum(precisiones) / len(precisiones), sum(recalls) / len(recalls)
    if p == 0 and r == 0:
        return 0.0
    b2 = _BETA**2
    return 100 * (1 + b2) * p * r / (b2 * p + r)


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(c) != "Mn")


def terminos(casos: Iterable[tuple[str, str]], glosario: Mapping[str, str]) -> tuple[int, int]:
    """(términos que aparecen en los originales, cuántos de ellos se tradujeron como dice el glosario)."""
    presentes, respetados, _ = terminos_con_lema(casos, glosario)
    return presentes, respetados


def terminos_con_lema(casos: Iterable[tuple[str, str]], glosario: Mapping[str, str]) -> tuple[int, int, int]:
    """(presentes, respetados con la forma exacta, respetados con la forma exacta o una flexión).

    Es la exactitud de términos de la tarea de terminología de WMT25: cuenta como acierto la forma exacta o la
    misma palabra en otra forma («lingotes de hierro» por «lingote de hierro»), y se informan las dos.
    """
    presentes = exactos = flexibles = 0
    patrones = {en: re.compile(r"(?<![^\W_])" + re.escape(en.casefold()) + r"(?![^\W_])") for en in glosario}
    for original, traduccion in casos:
        for en, patron in patrones.items():
            if patron.search(original.casefold()):
                presentes += 1
                exacto = _sin_tildes(glosario[en]) in _sin_tildes(traduccion)
                exactos += exacto
                flexibles += exacto or sale_el_termino(glosario[en], traduccion)
    return presentes, exactos, flexibles


def intervalo(puntajes: list[float], remuestreos: int = 1000, semilla: int = 0) -> tuple[float, float] | None:
    """Intervalo de confianza al 95 % del promedio, por remuestreo (bootstrap). None si hay menos de 5 puntajes."""
    if len(puntajes) < 5:
        return None
    azar = random.Random(semilla)
    n = len(puntajes)
    medias = sorted(statistics.fmean(azar.choices(puntajes, k=n)) for _ in range(remuestreos))
    return medias[int(0.025 * remuestreos)], medias[int(0.975 * remuestreos) - 1]


_PALABRA_FIRMA = re.compile(r"[^\W\d_]{4,}")


def _palabras_firma(texto: str) -> set[str]:
    return set(_PALABRA_FIRMA.findall(_sin_tildes(texto)))


def _mas_distintivas(
    candidatas: list[str], dentro: Counter[str], fuera: Counter[str], n_dentro: int, n_fuera: int
) -> list[str]:
    """Las dos palabras que más distinguen a un grupo de nombres del resto."""

    def clave(w: str) -> tuple[float, int]:
        return dentro[w] / n_dentro - fuera[w] / max(n_fuera, 1), dentro[w]

    return sorted(candidatas, key=clave, reverse=True)[:2]


def consistencia(pares: Iterable[tuple[str, str]], minimo: int = 3) -> tuple[float, int]:
    """(consistencia de 0 a 1, términos evaluados): ¿los nombres que comparten un término lo traducen igual?

    Heurística sin alineación: para cada término que se repite en 3 o más nombres, mira las dos palabras en
    español que más distinguen a esos nombres del resto y calcula en qué parte de ellos aparecen. Si «Moon
    Berries» sale como «bayas lunares» en todos da 1; si sale «bayas de luna» en uno de seis, baja. Sirve para
    comparar dos corridas del mismo banco, no como medida absoluta.
    """
    unicos = sorted(set(pares))
    if not unicos:
        return 0.0, 0
    palabras = [_palabras_firma(t) for _, t in unicos]
    puntajes: list[float] = []
    for termino in terminos_repetidos.repetidos((o for o, _ in unicos), minimo=minimo):
        patron = re.compile(r"(?<![^\W_])" + re.escape(termino) + r"(?![^\W_])")
        dentro = [i for i, (o, _) in enumerate(unicos) if patron.search(o)]
        fuera = [i for i in range(len(unicos)) if i not in set(dentro)]
        if len(dentro) < minimo:
            continue
        df_dentro = Counter(w for i in dentro for w in palabras[i])
        df_fuera = Counter(w for i in fuera for w in palabras[i])
        candidatas = [w for w, c in df_dentro.items() if c >= 2]
        if not candidatas:
            continue

        mejores = _mas_distintivas(candidatas, df_dentro, df_fuera, len(dentro), len(fuera))
        puntajes.append(statistics.fmean(df_dentro[w] / len(dentro) for w in mejores))
    return (statistics.fmean(puntajes) if puntajes else 0.0), len(puntajes)


@dataclass(slots=True)
class Medicion:
    motor: str
    textos: int
    traducidos: int  #: los que pasaron las reglas (el resto quedaría en inglés)
    chrf: float  #: promedio sobre los traducidos
    terminos_presentes: int
    terminos_respetados: int
    costo_estimado: float | None
    segundos: float
    por_ambito: dict[str, float] = field(default_factory=dict[str, float])  #: chrF promedio por ámbito
    revision: str = ""
    ejemplos: list[dict[str, str]] = field(default_factory=list[dict[str, str]])  #: los de chrF más bajo
    chrf_intervalo: tuple[float, float] | None = None  #: intervalo al 95 % del chrF promedio
    consistencia: float | None = None  #: ver `consistencia()`; solo si hay términos que se repiten
    terminos_evaluados: int = 0
    rechazos: dict[str, int] = field(default_factory=dict[str, int])  #: motivo → textos que no pasaron las reglas
    descanso: float = 0.0  #: segundos de pausa de la carga segura (motores locales)
    traducciones: list[dict[str, str]] = field(default_factory=list[dict[str, str]])  #: todas, para juzgarlas
    terminos_respetados_lema: int = 0  #: como `terminos_respetados`, aceptando plurales y otras formas (WMT25)

    @property
    def porcentaje(self) -> float:
        return 100 * self.traducidos / max(self.textos, 1)

    def tabla(self) -> str:
        filas = [
            ("Motor", self.motor),
            ("Textos traducidos", f"{self.traducidos} de {self.textos} ({self.porcentaje:.0f} %)"),
            (
                "chrF promedio",
                "sin referencias (se juzga)"
                if not self.por_ambito
                else f"{self.chrf:.1f}"
                + (
                    f" (IC 95 %: {self.chrf_intervalo[0]:.1f} a {self.chrf_intervalo[1]:.1f})"
                    if self.chrf_intervalo
                    else ""
                ),
            ),
            *((f"  chrF {a}", f"{v:.1f}") for a, v in sorted(self.por_ambito.items())),
            (
                "Términos del glosario",
                f"{self.terminos_respetados} de {self.terminos_presentes}"
                + (
                    f" ({self.terminos_respetados_lema} contando plurales y otras formas)"
                    if self.terminos_respetados_lema
                    else ""
                ),
            ),
            *(
                [("Consistencia de términos", f"{self.consistencia:.2f} ({self.terminos_evaluados} términos)")]
                if self.consistencia is not None
                else []
            ),
            *(
                [
                    (
                        "Rechazados por",
                        ", ".join(f"{m} {n}" for m, n in sorted(self.rechazos.items(), key=lambda x: -x[1])),
                    )
                ]
                if self.rechazos
                else []
            ),
            ("Costo estimado", "desconocido" if self.costo_estimado is None else f"US$ {self.costo_estimado:.3f}"),
            (
                "Tiempo",
                f"{self.segundos:.0f} s" + (f" (de ellos {self.descanso:.0f} s de descanso)" if self.descanso else ""),
            ),
        ]
        if self.revision:
            filas.append(("Revisión", self.revision))
        return "\n".join(f"{k:<24} {v}" for k, v in filas)


def _medir(
    nombre: str, banco: Banco, traducciones: Mapping[tuple[str, str], str], costo: float | None, segundos: float
) -> Medicion:
    puntajes: dict[str, list[float]] = {}
    filas: list[tuple[float, Caso, str]] = []
    for caso in banco.casos:
        hecha = traducciones.get((caso.ambito, caso.original))
        if hecha is None:
            continue
        puntaje = chrf(hecha, caso.referencia) if caso.referencia else 0.0
        if caso.referencia:  # un banco sin referencias (misiones, libros) se juzga, no se puntúa con chrF
            puntajes.setdefault(caso.ambito, []).append(puntaje)
        filas.append((puntaje, caso, hecha))
    todos = [p for lista in puntajes.values() for p in lista]
    presentes, respetados, con_lema = terminos_con_lema(((c.original, t) for _, c, t in filas), banco.glosario)
    nivel, evaluados = consistencia((c.original, t) for _, c, t in filas)
    peores = sorted(filas, key=lambda f: f[0])[:8]
    return Medicion(
        motor=nombre,
        textos=len(banco.casos),
        traducidos=len(filas),
        chrf=sum(todos) / len(todos) if todos else 0.0,
        terminos_presentes=presentes,
        terminos_respetados=respetados,
        terminos_respetados_lema=con_lema,
        costo_estimado=costo,
        segundos=segundos,
        por_ambito={a: sum(v) / len(v) for a, v in puntajes.items()},
        chrf_intervalo=intervalo(todos),
        consistencia=nivel if evaluados else None,
        terminos_evaluados=evaluados,
        traducciones=[
            {"ambito": c.ambito, "original": c.original, "referencia": c.referencia, "traduccion": t, "pista": c.pista}
            for _, c, t in filas
        ],
        ejemplos=[
            {"original": c.original, "referencia": c.referencia, "traduccion": t, "chrf": f"{p:.1f}"}
            for p, c, t in peores
        ],
    )


def medir(
    motor: Motor,
    banco: Banco,
    nombre: str = "",
    modelo: str = "",
    motor_id: str = "gemini",
    revisar: bool = False,
    glosario_estricto: bool = True,
    hilos: int = 4,
    cantidad_ejemplos: int = CANTIDAD_EN_LA_APP,
    controles_de_forma: bool = True,
) -> list[Medicion]:
    """Traduce el banco con el motor (memoria vacía) y devuelve la medición; con `revisar`, también la de después."""
    glosario = Glosario()
    if banco.juego:  # como la app: el juego primero, oficial y con sus nombres que no se traducen
        glosario.agregar_pares(
            {k: k for k in banco.juego}, banco.juego, fuente="minecraft", oficial=True, proteger_iguales=True
        )
    glosario.agregar_pares({k: k for k in banco.glosario}, banco.glosario, fuente="banco")
    with Memoria(":memory:") as memoria:
        ejemplos = Ejemplos(cantidad=cantidad_ejemplos)
        ejemplos.agregar_pares(banco.ejemplos)
        limites = fabrica.limites_de_lote(motor)
        traductor = Traductor(
            motor, memoria, glosario, banco.dialecto, hilos, validador=validar, ejemplos=ejemplos,
            glosario_estricto=glosario_estricto, limite_caracteres=limites[0], limite_entradas=limites[1],
            controles_de_forma=controles_de_forma,
        )  # fmt: skip
        por_ambito: dict[str, list[str]] = {}
        pistas: dict[str, str] = {}
        for caso in banco.casos:
            por_ambito.setdefault(caso.ambito, []).append(caso.original)
            if caso.pista:
                pistas[caso.original] = caso.pista
        inicio = time.perf_counter()
        resultados = {ambito: traductor.traducir(textos, ambito, pistas) for ambito, textos in por_ambito.items()}
        segundos = time.perf_counter() - inicio
        informe = Informe(
            [
                InformeModulo(_GRUPO.get(a, a), a, "", len(t), len(t), sum(len(x) for x in t))
                for a, t in por_ambito.items()
            ]
        )
        hechas = {(a, o): t for a, r in resultados.items() for o, t in r.traducciones.items()}
        mediciones = [_medir(nombre or motor.nombre, banco, hechas, informe.costo(modelo, False, motor_id), segundos)]
        mediciones[0].rechazos = dict(
            Counter(m.split(":")[0] for r in resultados.values() for m in r.rechazados.values())
        )
        enfriador = getattr(motor, "enfriador", None)
        mediciones[0].descanso = float(getattr(enfriador, "pausas", 0.0))
        if revisar:
            inicio = time.perf_counter()
            resumen = revision.ResumenRevision()
            for ambito in ("mision", "libro"):
                if ambito in resultados:
                    resumen.sumar(revision.revisar_y_corregir(traductor, resultados[ambito].nuevas, ambito, {}))
            segundos_rev = time.perf_counter() - inicio
            hechas: dict[tuple[str, str], str] = {}
            for a, textos in por_ambito.items():  # lo rehecho ya está en la memoria: no se pide nada nuevo
                hechas.update({(a, o): t for o, t in traductor.conocidas(textos, a).items()})
            despues = _medir(
                f"{nombre or motor.nombre} + revisión", banco, hechas,
                informe.costo(modelo, False, motor_id, revisar=True), segundos + segundos_rev,
            )  # fmt: skip
            despues.revision = str(resumen)
            mediciones.append(despues)
    return mediciones


#: Ámbito del banco → grupo del informe, para estimar el costo igual que en la app.
_GRUPO = {"ui": "mods", "mision": "misiones", "libro": "libros", "script": "scripts"}


def guardar(mediciones: list[Medicion], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = [asdict(m) for m in mediciones]
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")

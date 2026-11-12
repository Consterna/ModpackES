"""Medición de calidad con un banco de referencia: sirve para comparar motores, modelos y prompts.

Las métricas son automáticas y tienen límites: chrF (Popović, WMT 2015) mide cuánto se parece cada traducción a
una referencia por n-gramas de caracteres, así que una traducción correcta pero distinta de la referencia
también baja el puntaje. Por eso se mira junto con lo que no depende de la referencia: textos aceptados por
las reglas, términos del glosario respetados y textos que quedaron en inglés.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..motores.base import Motor
from ..nucleo.ejemplos import Ejemplos
from ..nucleo.glosario import Glosario
from ..nucleo.memoria import Memoria
from ..nucleo.traductor import Traductor
from ..proceso import Informe, InformeModulo
from . import revision
from .calidad import validar

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

    @classmethod
    def leer(cls, ruta: Path) -> Banco:
        datos: Any = json.loads(ruta.read_text(encoding="utf-8"))
        casos = [
            Caso(str(t["ambito"]), str(t["original"]), str(t["referencia"]), str(t.get("pista", "")))
            for t in datos["textos"]
        ]
        ejemplos = {str(k): str(v) for k, v in datos.get("ejemplos", {}).items()}
        return cls(
            str(datos.get("dialecto", "es_mx")), {str(k): str(v) for k, v in datos["glosario"].items()}, casos, ejemplos
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
    presentes = respetados = 0
    patrones = {en: re.compile(r"(?<![^\W_])" + re.escape(en.casefold()) + r"(?![^\W_])") for en in glosario}
    for original, traduccion in casos:
        for en, patron in patrones.items():
            if patron.search(original.casefold()):
                presentes += 1
                respetados += _sin_tildes(glosario[en]) in _sin_tildes(traduccion)
    return presentes, respetados


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

    @property
    def porcentaje(self) -> float:
        return 100 * self.traducidos / max(self.textos, 1)

    def tabla(self) -> str:
        filas = [
            ("Motor", self.motor),
            ("Textos traducidos", f"{self.traducidos} de {self.textos} ({self.porcentaje:.0f} %)"),
            ("chrF promedio", f"{self.chrf:.1f}"),
            *((f"  chrF {a}", f"{v:.1f}") for a, v in sorted(self.por_ambito.items())),
            ("Términos del glosario", f"{self.terminos_respetados} de {self.terminos_presentes}"),
            ("Costo estimado", "desconocido" if self.costo_estimado is None else f"US$ {self.costo_estimado:.3f}"),
            ("Tiempo", f"{self.segundos:.0f} s"),
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
        puntaje = chrf(hecha, caso.referencia)
        puntajes.setdefault(caso.ambito, []).append(puntaje)
        filas.append((puntaje, caso, hecha))
    todos = [p for lista in puntajes.values() for p in lista]
    presentes, respetados = terminos(((c.original, t) for _, c, t in filas), banco.glosario)
    peores = sorted(filas, key=lambda f: f[0])[:8]
    return Medicion(
        motor=nombre,
        textos=len(banco.casos),
        traducidos=len(filas),
        chrf=sum(todos) / len(todos) if todos else 0.0,
        terminos_presentes=presentes,
        terminos_respetados=respetados,
        costo_estimado=costo,
        segundos=segundos,
        por_ambito={a: sum(v) / len(v) for a, v in puntajes.items()},
        ejemplos=[
            {"original": c.original, "referencia": c.referencia, "traduccion": t, "chrf": f"{p:.1f}"}
            for p, c, t in peores
        ],
    )


def medir(
    motor: Motor, banco: Banco, nombre: str = "", modelo: str = "", motor_id: str = "gemini", revisar: bool = False
) -> list[Medicion]:
    """Traduce el banco con el motor (memoria vacía) y devuelve la medición; con `revisar`, también la de después."""
    glosario = Glosario()
    glosario.agregar_pares({k: k for k in banco.glosario}, banco.glosario)
    with Memoria(":memory:") as memoria:
        ejemplos = Ejemplos()
        ejemplos.agregar_pares(banco.ejemplos)
        traductor = Traductor(motor, memoria, glosario, banco.dialecto, validador=validar, ejemplos=ejemplos)
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

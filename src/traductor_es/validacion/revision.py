"""Revisión automática opcional: otro pedido al motor juzga cada traducción nueva y se rehacen las malas.

La idea viene de GEMBA-MQM (Kocmi y Federmann, WMT 2023): el modelo marca errores con categoría y gravedad,
sin traducción de referencia. Como esas marcas no siempre coinciden con las de una persona, solo se usan
para decidir qué volver a traducir: la traducción nueva tiene que pasar las mismas reglas que la primera, y
si no las pasa queda la anterior. Nunca se tocan las correcciones del usuario.
"""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..motores.base import Cancelado, Entrada, Lote
from ..motores.instrucciones import CATEGORIAS, GRAVEDADES
from ..nucleo.dialectos import DIALECTOS
from ..nucleo.mascara import enmascarar
from ..nucleo.traductor import Traductor

#: Gravedades que hacen volver a traducir un texto.
A_REHACER = frozenset({"grave", "critica"})
_POR_LOTE = 30


@dataclass(frozen=True, slots=True)
class Hallazgo:
    original: str
    traduccion: str
    gravedad: str
    categoria: str
    explicacion: str


@dataclass(slots=True)
class ResumenRevision:
    revisados: int = 0
    marcados: dict[str, int] = field(default_factory=dict[str, int])  #: categoría → cuántos graves o críticos
    leves: int = 0
    corregidos: int = 0

    def sumar(self, otro: ResumenRevision) -> None:
        self.revisados += otro.revisados
        self.leves += otro.leves
        self.corregidos += otro.corregidos
        for c, n in otro.marcados.items():
            self.marcados[c] = self.marcados.get(c, 0) + n

    def __str__(self) -> str:
        graves = sum(self.marcados.values())
        if not graves:
            return f"Revisión: {self.revisados} textos, ninguno con errores graves."
        detalle = ", ".join(f"{c} {n}" for c, n in sorted(self.marcados.items()))
        return (
            f"Revisión: {self.revisados} textos, {graves} con errores graves ({detalle}); "
            f"{self.corregidos} quedaron corregidos."
        )


def interpretar_veredicto(valor: str) -> tuple[str, str, str] | None:
    """«grave|terminologia|explicación» → (gravedad, categoría, explicación); None si dice OK o no se entiende."""
    texto = valor.strip()
    if not texto or texto.upper().startswith("OK"):
        return None
    partes = [p.strip() for p in texto.split("|", 2)]
    if len(partes) < 3:
        return None
    gravedad = partes[0].lower().replace("í", "i")
    categoria = partes[1].lower().replace("í", "i")
    if gravedad not in GRAVEDADES or categoria not in CATEGORIAS:
        return None
    return gravedad, categoria, partes[2][:300]


def revisar(traductor: Traductor, pares: Mapping[str, str], ambito: str) -> list[Hallazgo]:
    """Pide al motor que juzgue cada par (núcleo original → traducción). Devuelve lo que marcó."""
    items = sorted(pares.items())
    lotes = [items[i : i + _POR_LOTE] for i in range(0, len(items), _POR_LOTE)]

    def un_lote(lote: list[tuple[str, str]]) -> list[Hallazgo]:
        if traductor.cancelar.is_set():
            raise Cancelado()
        entradas = tuple(
            Entrada(str(i), enmascarar(o).texto, traduccion=enmascarar(t).texto) for i, (o, t) in enumerate(lote)
        )
        pedido = Lote(
            entradas, ambito, DIALECTOS[traductor.dialecto], traductor.glosario.relevantes(o for o, _ in lote),
            traductor.contexto, tarea="revisar",
        )  # fmt: skip
        salida = traductor.motor.traducir_lote(pedido)
        hallazgos: list[Hallazgo] = []
        for i, (original, traduccion) in enumerate(lote):
            veredicto = interpretar_veredicto(str(salida.get(str(i), "")))
            if veredicto:
                hallazgos.append(Hallazgo(original, traduccion, *veredicto))
        return hallazgos

    with ThreadPoolExecutor(traductor.hilos) as ex:
        return [h for grupo in ex.map(un_lote, lotes) for h in grupo]


def revisar_y_corregir(
    traductor: Traductor, pares: Mapping[str, str], ambito: str, pistas: Mapping[str, str]
) -> ResumenRevision:
    """Revisa las traducciones nuevas y rehace las graves. Las correcciones del usuario no se revisan."""
    propios = {o: t for o, t in pares.items() if traductor.memoria.correccion(o, traductor.dialecto) is None}
    resumen = ResumenRevision(revisados=len(propios))
    if not propios:
        return resumen
    hallazgos = revisar(traductor, propios, ambito)
    a_rehacer: dict[str, tuple[str, str]] = {}
    for h in hallazgos:
        if h.gravedad in A_REHACER:
            resumen.marcados[h.categoria] = resumen.marcados.get(h.categoria, 0) + 1
            a_rehacer[h.original] = (h.traduccion, f"{h.categoria}: {h.explicacion}")
        else:
            resumen.leves += 1
    resumen.corregidos = len(traductor.rehacer(a_rehacer, ambito, pistas))
    return resumen

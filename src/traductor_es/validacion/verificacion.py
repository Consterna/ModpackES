"""Verificador a ciegas: decide si una traducción nueva es mejor que la anterior antes de reemplazarla.

Un modelo que corrige su propia traducción tiende a cambiar cosas que estaban bien. Por eso una corrección (de la
revisión, de un texto dudoso o de una muestra elegida) solo se queda si otro pedido al motor, sin saber cuál es la
nueva, la prefiere en los dos órdenes (A contra B y B contra A). Así no cuenta el sesgo de posición, y un empate o
un juez que se contradice deja la anterior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor

from ..motores.base import Cancelado, Entrada, Lote, Motor
from ..nucleo.dialectos import DIALECTOS
from ..nucleo.mascara import enmascarar

#: Pares por pedido al juez.
POR_LOTE = 20


def veredictos(
    motor: Motor,
    dialecto: str,
    ambito: str,
    casos: Sequence[tuple[str, str, str, str]],
    glosario: Mapping[str, str] | None = None,
    contexto: str = "",
    hilos: int = 4,
) -> list[str]:
    """Para cada (original, pista, A, B), «A», «B» o «igual» según el juez. Los códigos van enmascarados: el juez no
    los evalúa (ya se comprobaron) y así no se distrae con ellos."""
    lotes = [list(casos[i : i + POR_LOTE]) for i in range(0, len(casos), POR_LOTE)]

    def un_lote(lote: list[tuple[str, str, str, str]]) -> list[str]:
        entradas = tuple(
            Entrada(str(j), enmascarar(o).texto, pista, traduccion=enmascarar(a).texto, alternativa=enmascarar(b).texto)
            for j, (o, pista, a, b) in enumerate(lote)
        )
        pedido = Lote(entradas, ambito, DIALECTOS[dialecto], dict(glosario or {}), contexto, tarea="comparar")
        try:
            salida = motor.traducir_lote(pedido)
        except Cancelado:
            raise
        except Exception:  # sin juez no se cambia nada: queda la traducción anterior
            return ["igual"] * len(lote)
        votos: list[str] = []
        for j in range(len(lote)):
            v = str(salida.get(str(j), "")).strip().upper()
            votos.append("A" if v.startswith("A") else "B" if v.startswith("B") else "igual")
        return votos

    with ThreadPoolExecutor(max(1, hilos)) as ex:
        return [v for grupo in ex.map(un_lote, lotes) for v in grupo]


def gana_la_nueva(
    motor: Motor,
    dialecto: str,
    ambito: str,
    casos: Sequence[tuple[str, str, str, str]],
    glosario: Mapping[str, str] | None = None,
    contexto: str = "",
    hilos: int = 4,
) -> list[bool]:
    """Para cada (original, pista, anterior, nueva), si el juez prefiere la nueva en los dos órdenes."""
    if not casos:
        return []
    directo = veredictos(motor, dialecto, ambito, casos, glosario, contexto, hilos)
    inverso = veredictos(motor, dialecto, ambito, [(o, p, b, a) for o, p, a, b in casos], glosario, contexto, hilos)
    return [d == "B" and i == "A" for d, i in zip(directo, inverso, strict=True)]

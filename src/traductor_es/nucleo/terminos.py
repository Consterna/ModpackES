"""Términos que se repiten en los nombres de un modpack («Moon Berries» en «Moon Berries Pie», «Moon Berries Jam»…).

Si cada nombre se traduce por separado, el modelo puede decir «bayas lunares» en uno y «bayas de luna» en otro.
Traducir primero esos términos y fijarlos en el glosario hace que todos los nombres usen la misma palabra.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

#: Un nombre: de 1 a 5 palabras en Title Case, con conectores en minúscula («Pie of the Moon»).
_CONECTORES = frozenset({"of", "the", "and", "de", "del", "la", "el", "in", "on", "for", "to", "a", "an"})
_PALABRA_TITULO = re.compile(r"[A-Z][A-Za-z'’-]+")
_MAX_PALABRAS_NOMBRE = 5
_MAX_PALABRAS_TERMINO = 3


def _palabras_de_nombre(texto: str) -> list[str] | None:
    """Las palabras del texto si es un nombre en Title Case; None si no lo es."""
    palabras = texto.strip().split(" ")
    if not 1 <= len(palabras) <= _MAX_PALABRAS_NOMBRE:
        return None
    for i, p in enumerate(palabras):
        if _PALABRA_TITULO.fullmatch(p):
            continue
        if p in _CONECTORES and 0 < i < len(palabras) - 1:
            continue
        return None
    return palabras


def repetidos(textos: Iterable[str], minimo: int = 4, maximo: int = 30) -> list[str]:
    """Términos de 1 a 3 palabras que aparecen en `minimo` nombres distintos o más, los más repetidos primero.

    Un término que siempre aparece junto a otro más largo («Moon» dentro de «Moon Berries») no se devuelve:
    se prefiere el más largo.
    """
    cuenta: Counter[str] = Counter()
    for texto in set(textos):
        palabras = _palabras_de_nombre(texto)
        if palabras is None:
            continue
        trozos: set[str] = set()
        for i in range(len(palabras)):
            for j in range(i + 1, min(len(palabras), i + _MAX_PALABRAS_TERMINO) + 1):
                tramo = palabras[i:j]
                if tramo[0] in _CONECTORES or tramo[-1] in _CONECTORES:
                    continue
                trozos.add(" ".join(tramo))
        cuenta.update(trozos)
    candidatos = {t: c for t, c in cuenta.items() if c >= minimo and len(t) >= 4}
    finales = [
        t
        for t, c in candidatos.items()
        if not any(h != t and c == ch and f" {t} " in f" {h} " for h, ch in candidatos.items())
    ]
    finales.sort(key=lambda t: (-candidatos[t] * len(t), t))
    return finales[:maximo]

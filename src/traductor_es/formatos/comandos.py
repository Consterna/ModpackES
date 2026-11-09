"""Comandos de chat de Minecraft (`tellraw`, `title`, `say`, `msg`…): separa el texto que ve el jugador.

Sirve para una línea de un `.mcfunction` y para la cadena que un script de KubeJS le pasa a `runCommand`.
Solo reconoce la forma clásica, con el texto como JSON (`tellraw @a {"text":"Hola"}`) o como texto suelto
(`say Hola`). Lo que tenga otra forma (SNBT, macros `$`) no se toca.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_INICIO = re.compile(r"(?:^\s*/?|\brun\s+)(?P<orden>tellraw|title|say|msg|tell|w)[ \t]+")
#: `@a`, `@a[distance=..5, tag=x]` (con espacios dentro de los corchetes) o un nombre.
_SELECTOR = re.compile(r"(?:@[a-z]+(?:\[[^\]]*\])?|\S+)[ \t]+")
_TITULO = re.compile(r"(?:title|subtitle|actionbar)[ \t]+")
_CON_SELECTOR = frozenset({"tellraw", "title", "msg", "tell", "w"})


@dataclass(frozen=True, slots=True)
class Comando:
    prefijo: str  #: todo lo que va antes del texto (`execute as @a run tellraw @s `)
    cuerpo: str  #: lo que ve el jugador: un componente JSON o un texto suelto
    json: bool  #: el cuerpo es un componente JSON (tellraw, title) y no texto suelto (say, msg)


def analizar(texto: str) -> Comando | None:
    """El comando de chat que contiene el texto, o None si no es de los que muestran algo al jugador."""
    inicio = _INICIO.search(texto)
    if inicio is None:
        return None
    orden = inicio.group("orden")
    pos = inicio.end()
    if orden in _CON_SELECTOR:
        selector = _SELECTOR.match(texto, pos)
        if selector is None:
            return None
        pos = selector.end()
    if orden == "title":
        titulo = _TITULO.match(texto, pos)
        if titulo is None:  # title … times / clear / reset
            return None
        pos = titulo.end()
    cuerpo = texto[pos:]
    if not cuerpo.strip():
        return None
    return Comando(texto[:pos], cuerpo, json=orden in ("tellraw", "title"))

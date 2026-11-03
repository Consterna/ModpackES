"""SNBT (FTB Quests, FTB Library): escaneo sin pérdidas de las cadenas de texto.

No se reescribe el archivo entero: solo se reemplazan, en su sitio, las cadenas que se traducen.
Todo lo demás (espacios, orden, números, comentarios del autor) queda byte a byte igual.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from ..nucleo.mascara import ESCAPE_CRUDO

_CLAVE_SIN_COMILLAS: Final = re.compile(r"[A-Za-z0-9_.+\-]+")


@dataclass(frozen=True, slots=True)
class Cadena:
    inicio: int  #: posición del primer carácter dentro de las comillas
    fin: int  #: posición de la comilla de cierre
    campo: str | None  #: clave a la que pertenece (o la de la lista que la contiene)
    comilla: str
    texto: str  #: contenido ya sin escapes


def des_escapar(crudo: str, comilla: str) -> str:
    """Quita los escapes reconocidos (\\\\ y la comilla). Los demás se marcan para restaurarlos tal cual."""
    salida: list[str] = []
    i = 0
    while i < len(crudo):
        c = crudo[i]
        if c == "\\" and i + 1 < len(crudo):
            sig = crudo[i + 1]
            salida.append(sig if sig in ("\\", comilla) else ESCAPE_CRUDO + sig)
            i += 2
        else:
            salida.append(c)
            i += 1
    return "".join(salida)


def escapar(texto: str, comilla: str) -> str:
    salida: list[str] = []
    i = 0
    while i < len(texto):
        c = texto[i]
        if c == ESCAPE_CRUDO and i + 1 < len(texto):
            salida.append("\\" + texto[i + 1])
            i += 2
            continue
        salida.append("\\\\" if c == "\\" else "\\" + c if c == comilla else c)
        i += 1
    return "".join(salida)


def escanear(src: str) -> list[Cadena]:
    """Todas las cadenas entre comillas que son valores (no claves), con la clave a la que pertenecen."""
    res: list[Cadena] = []
    pila: list[tuple[str, str | None]] = []
    ultima: str | None = None
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            if j >= n:
                raise ValueError(f"Cadena sin cerrar en la posición {i}")
            k = j + 1
            while k < n and src[k] in " \t":
                k += 1
            if k < n and src[k] == ":":
                ultima = des_escapar(src[i + 1 : j], c)
            else:
                campo = pila[-1][1] if pila and pila[-1][0] == "[" else ultima
                res.append(Cadena(i + 1, j, campo, c, des_escapar(src[i + 1 : j], c)))
            i = j + 1
        elif c in "{[":
            pila.append((c, ultima))
            i += 1
        elif c in "}]":
            if pila:
                pila.pop()
            i += 1
        elif c.isalnum() or c in "_.+-":
            m = _CLAVE_SIN_COMILLAS.match(src, i)
            fin = m.end() if m else i + 1
            k = fin
            while k < n and src[k] in " \t":
                k += 1
            if k < n and src[k] == ":":
                ultima = src[i:fin]
                i = k + 1
            else:
                i = fin
        else:
            i += 1
    return res


def reemplazar(src: str, cadenas: Sequence[Cadena], nuevos: Mapping[int, str]) -> str:
    """Escribe los textos nuevos (por posición de inicio) en su sitio; lo demás queda intacto."""
    partes: list[str] = []
    ultimo = 0
    for c in sorted(cadenas, key=lambda c: c.inicio):
        if c.inicio in nuevos and nuevos[c.inicio] != c.texto:
            partes.append(src[ultimo : c.inicio])
            partes.append(escapar(nuevos[c.inicio], c.comilla))
            ultimo = c.fin
    partes.append(src[ultimo:])
    return "".join(partes)

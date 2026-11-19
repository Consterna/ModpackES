"""Archivos `.properties` de Java (el formato del idioma de los shaderpacks: `shaders/lang/en_US.lang`).

Solo lectura: clave y valor con los escapes de Java (`\\uXXXX`, `\\n`, `\\=`…), líneas que siguen con `\\` y
comentarios con `#` o `!`, como `java.util.Properties`.
"""

from __future__ import annotations

import re

_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}
_HEX4 = re.compile(r"[0-9a-fA-F]{4}")
_BLANCOS = " \t\f"


def _desescapar(texto: str) -> str:
    salida: list[str] = []
    i = 0
    while i < len(texto):
        c = texto[i]
        if c != "\\" or i + 1 >= len(texto):
            salida.append(c)
            i += 1
            continue
        siguiente = texto[i + 1]
        if siguiente == "u" and _HEX4.fullmatch(texto[i + 2 : i + 6]):
            salida.append(chr(int(texto[i + 2 : i + 6], 16)))
            i += 6
            continue
        salida.append(_ESCAPES.get(siguiente, siguiente))
        i += 2
    return "".join(salida)


def _lineas_logicas(texto: str) -> list[str]:
    """Junta cada línea que termina en un `\\` sin escapar con la siguiente (sin la sangría de esta)."""
    salida: list[str] = []
    actual: str | None = None
    for cruda in texto.splitlines():
        linea = cruda if actual is None else cruda.lstrip(_BLANCOS)
        barras = len(linea) - len(linea.rstrip("\\"))
        if barras % 2 == 1:
            actual = (actual or "") + linea[:-1]
            continue
        salida.append((actual or "") + linea)
        actual = None
    if actual is not None:
        salida.append(actual)
    return salida


def _partir(linea: str) -> tuple[str, str]:
    """Clave y valor crudos: la clave termina en el primer `=`, `:` o blanco sin escapar; después se saltan los
    blancos y, si hay, un `=` o `:` y más blancos."""
    i = 0
    while i < len(linea):
        c = linea[i]
        if c == "\\":
            i += 2
            continue
        if c in "=:" or c in _BLANCOS:
            break
        i += 1
    clave, resto = linea[:i], linea[i:].lstrip(_BLANCOS)
    if resto[:1] in ("=", ":"):
        resto = resto[1:].lstrip(_BLANCOS)
    return clave, resto


def leer(texto: str) -> dict[str, str]:
    """{clave: valor} de un `.properties`. Si una clave se repite, gana la última (como en Java)."""
    salida: dict[str, str] = {}
    for linea in _lineas_logicas(texto.removeprefix("﻿")):
        limpia = linea.lstrip(_BLANCOS)
        if not limpia or limpia[0] in "#!":
            continue
        clave, valor = _partir(limpia)
        if clave:
            salida[_desescapar(clave)] = _desescapar(valor)
    return salida

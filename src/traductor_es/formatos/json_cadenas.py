"""JSON sin pérdidas: localiza cada cadena con su ruta de claves y la reemplaza en su sitio.

Sirve para archivos de misiones (BetterQuesting, HQM, Heracles): todo lo que no se traduce queda
byte a byte igual (espacios, orden, números, escapes \\uXXXX de otras cadenas).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

Ruta = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class CadenaJson:
    inicio: int  #: posición de la comilla de apertura
    fin: int  #: posición siguiente a la comilla de cierre
    ruta: Ruta  #: claves e índices desde la raíz hasta este valor
    texto: str

    @property
    def campo(self) -> str | None:
        """La última clave de texto de la ruta (la de la lista si el valor está dentro de una)."""
        return next((p for p in reversed(self.ruta) if isinstance(p, str)), None)


@dataclass(slots=True)
class _Nivel:
    objeto: bool  #: True = objeto {…}, False = lista […]
    posicion: str | int  #: clave actual (objeto) o índice actual (lista)
    espera_clave: bool


def _fin_de_cadena(src: str, i: int) -> int:
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            return j + 1
        j += 1
    raise ValueError(f"Cadena JSON sin cerrar en la posición {i}")


def escanear(src: str) -> list[CadenaJson]:
    """Cadenas que son valores (no claves). Valida la sintaxis: un JSON roto lanza ValueError."""
    json.loads(src)  # que el archivo sea JSON válido antes de tocar nada
    res: list[CadenaJson] = []
    pila: list[_Nivel] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '"':
            fin = _fin_de_cadena(src, i)
            texto: str = json.loads(src[i:fin])
            arriba = pila[-1] if pila else None
            if arriba is not None and arriba.objeto and arriba.espera_clave:
                arriba.posicion = texto
                arriba.espera_clave = False
            else:
                res.append(CadenaJson(i, fin, tuple(nivel.posicion for nivel in pila), texto))
            i = fin
            continue
        if c == "{":
            pila.append(_Nivel(objeto=True, posicion="", espera_clave=True))
        elif c == "[":
            pila.append(_Nivel(objeto=False, posicion=0, espera_clave=False))
        elif c in "}]":
            pila.pop()
        elif c == "," and pila:
            nivel = pila[-1]
            if nivel.objeto:
                nivel.espera_clave = True
            elif isinstance(nivel.posicion, int):
                nivel.posicion += 1
        i += 1
    return res


def reemplazar(src: str, cadenas: Sequence[CadenaJson], nuevos: Mapping[int, str]) -> str:
    """Escribe los textos nuevos (por posición de inicio) en su sitio; lo demás queda intacto."""
    partes: list[str] = []
    ultimo = 0
    for c in sorted(cadenas, key=lambda c: c.inicio):
        nuevo = nuevos.get(c.inicio)
        if nuevo is not None and nuevo != c.texto:
            partes.append(src[ultimo : c.inicio])
            partes.append(json.dumps(nuevo, ensure_ascii=False))
            ultimo = c.fin
    partes.append(src[ultimo:])
    return "".join(partes)

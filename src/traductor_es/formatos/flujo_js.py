"""Mensajes que un script arma por partes y manda después.

    let mensaje = 'Te has ganado '
    mensaje += efecto.name            // «name» es un texto que ve el jugador
    mensaje += global.nombres[clave]   // «nombres» es una tabla de textos que ve el jugador
    player.tell(mensaje)

Aquí solo se lee el código para saber qué variables, miembros y tablas acaban en un mensaje. Decidir qué
cadenas se traducen es cosa del módulo de scripts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .javascript import CadenaJs

_IDENT = r"[A-Za-z_$][\w$]*"
_RUTA = rf"{_IDENT}(?:\.{_IDENT})*"
_AGREGADO = re.compile(rf"\b({_IDENT})\s*\+=\s*({_RUTA})(?:(\[[^\]\n]*\])(?:\.({_IDENT}))?)?")
_ASIGNADA = re.compile(rf"({_IDENT})\s*\+?=\s*$")
_CLAVE = re.compile(rf"(?:({_IDENT})|['\"]([^'\"\n]+)['\"])\s*:\s*$")
_VENTANA = 160  #: cuánto código hacia atrás se mira para saber a qué se asigna una cadena


@dataclass(frozen=True, slots=True)
class Flujo:
    variables: frozenset[str] = frozenset()  #: variables que se pasan a una llamada de texto: `tell(mensaje)`
    miembros: frozenset[str] = frozenset()  #: `mensaje += efecto.name` → «name»
    tablas: frozenset[str] = frozenset()  #: `mensaje += global.nombres[clave]` → «nombres»


def analizar(src: str, llamadas: str) -> Flujo:
    """`llamadas`: expresión regular con las llamadas cuyo argumento es texto para el jugador."""
    pasadas = re.compile(rf"(?:{llamadas})\s*\(\s*({_IDENT})\s*[,)]")
    variables = frozenset(pasadas.findall(src))
    if not variables:
        return Flujo()
    miembros: set[str] = set()
    tablas: set[str] = set()
    for variable, ruta, indice, miembro in _AGREGADO.findall(src):
        if variable not in variables:
            continue
        ultimo = ruta.rsplit(".", 1)[-1]
        if miembro:  # `efectos[i].name`: el texto es el miembro
            miembros.add(miembro)
        elif indice:  # `nombres[clave]`: el texto está en la tabla
            tablas.add(ultimo)
        elif "." in ruta:
            miembros.add(ultimo)
    return Flujo(variables, frozenset(miembros), frozenset(tablas))


def asignada_a(src: str, cadena: CadenaJs) -> str | None:
    """La variable a la que se asigna o se suma esta cadena (`msg = '…'`, `msg += '…'`)."""
    m = _ASIGNADA.search(src[max(0, cadena.inicio - _VENTANA) : cadena.inicio])
    return m.group(1) if m else None


def clave_de(src: str, cadena: CadenaJs) -> str | None:
    """La clave de objeto a la que pertenece esta cadena como valor (`name: '…'`)."""
    m = _CLAVE.search(src[max(0, cadena.inicio - _VENTANA) : cadena.inicio])
    return (m.group(1) or m.group(2)) if m else None


def cuerpos_de_tabla(src: str, cadenas: Sequence[CadenaJs], tablas: Iterable[str]) -> list[tuple[int, int]]:
    """Posiciones (inicio, fin) del contenido de las tablas `x.nombres = { … }` con esos nombres."""
    nombres = frozenset(tablas)
    if not nombres:
        return []
    en_cadena = {c.inicio: c.fin for c in cadenas}
    cuerpos: list[tuple[int, int]] = []
    for m in re.finditer(rf"({_RUTA})\s*=\s*\{{", src):
        if m.group(1).rsplit(".", 1)[-1] not in nombres:
            continue
        i, profundidad = m.end(), 1
        while i < len(src) and profundidad:
            if i in en_cadena:
                i = en_cadena[i]
                continue
            profundidad += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        cuerpos.append((m.end(), i))
    return cuerpos

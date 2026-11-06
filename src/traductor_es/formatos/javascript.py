"""JavaScript de KubeJS: localiza cada cadena (con la llamada en la que está) y la reemplaza en su sitio.

No es un analizador completo de JS: distingue comentarios, expresiones regulares, plantillas `${…}` y
cadenas, y para cada cadena recuerda la función a la que se pasa como argumento (p. ej. `player.tell`).
El resto del archivo queda byte a byte igual.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..nucleo.mascara import ESCAPE_CRUDO

_IDENT_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$")
_PALABRAS_CLAVE = frozenset({"if", "for", "while", "switch", "catch", "function", "return", "typeof", "with"})
#: Si lo anterior es uno de estos caracteres, una «/» empieza una expresión regular y no una división.
_ANTES_DE_REGEX = set("(,=:[!&|?{};+-*%<>~^")
# «\$» no se decodifica: en una plantilla separa «${» de una expresión de verdad y hay que conservarlo
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "`": "`"}


@dataclass(frozen=True, slots=True)
class CadenaJs:
    inicio: int  #: posición de la comilla de apertura
    fin: int  #: posición siguiente a la de cierre
    comilla: str
    texto: str  #: sin escapes
    funcion: str | None  #: nombre de la llamada que la recibe como argumento (p. ej. «tell»)
    receptor: str | None  #: lo que va antes del punto (p. ej. «player»)
    comparada: bool  #: está junto a un ==, !=, case… (es lógica, no texto)
    #: Llamadas que la envuelven, de fuera hacia dentro: «ItemEvents.tooltip», «onEvent:item.tooltip»…
    contexto: tuple[str, ...] = ()
    arg: int = -1  #: posición (desde 0) del argumento de la llamada en la que está; -1 si no es un argumento


@dataclass(slots=True)
class _Marco:
    tipo: str  #: «(», «[» o «{»
    funcion: str | None = None
    receptor: str | None = None
    primera: str | None = None  #: primera cadena pasada directamente a esta llamada (p. ej. el evento de onEvent)
    arg: int = 0  #: en qué argumento va el escaneo (cuenta las comas de esta llamada)

    def nombre(self) -> str:
        base = f"{self.receptor}.{self.funcion}" if self.receptor else str(self.funcion)
        return f"{base}:{self.primera}" if self.primera is not None else base


def des_escapar(crudo: str) -> str:
    salida: list[str] = []
    i = 0
    while i < len(crudo):
        c = crudo[i]
        if c == "\\" and i + 1 < len(crudo):
            sig = crudo[i + 1]
            salida.append(_ESCAPES.get(sig, ESCAPE_CRUDO + sig))
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
        if c == "\\":
            salida.append("\\\\")
        elif c == comilla:
            salida.append("\\" + c)
        elif c == "\n":
            salida.append("\\n")
        elif c == "\r":
            salida.append("\\r")
        else:
            salida.append(c)
        i += 1
    return "".join(salida)


def _llamada(src: str, parentesis: int) -> tuple[str | None, str | None]:
    """Nombre y receptor de la llamada cuyo «(» está en esa posición: `player.tell(` → (tell, player)."""
    nombre, inicio = _ident_antes(src, parentesis)
    if not nombre or nombre in _PALABRAS_CLAVE or nombre[0].isdigit():
        return None, None
    k = inicio - 1
    while k >= 0 and src[k] in " \t\r\n":
        k -= 1
    if k >= 0 and src[k] == ".":
        receptor, _ = _ident_antes(src, k)
        return nombre, receptor or None
    return nombre, None


def _ident_antes(src: str, pos: int) -> tuple[str, int]:
    """El identificador que termina justo antes de `pos` (saltando espacios) y dónde empieza."""
    j = pos - 1
    while j >= 0 and src[j] in " \t\r\n":
        j -= 1
    fin = j + 1
    while j >= 0 and src[j] in _IDENT_CHARS:
        j -= 1
    return src[j + 1 : fin], j + 1


def _fin_cadena(src: str, i: int, comilla: str) -> int:
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == comilla:
            return j + 1
        if comilla != "`" and c == "\n":
            break
        if comilla == "`" and c == "$" and j + 1 < len(src) and src[j + 1] == "{":
            j = _fin_expresion(src, j + 2)
            continue
        j += 1
    raise ValueError(f"Cadena sin cerrar en la posición {i}")


def _fin_expresion(src: str, j: int) -> int:
    """Salta el contenido de `${…}` (puede tener llaves y cadenas dentro)."""
    profundidad = 1
    while j < len(src) and profundidad:
        c = src[j]
        if c in "'\"`":
            j = _fin_cadena(src, j, c)
            continue
        profundidad += {"{": 1, "}": -1}.get(c, 0)
        j += 1
    return j


def _significativo_antes(src: str, i: int) -> str:
    j = i - 1
    while j >= 0 and src[j] in " \t\r\n":
        j -= 1
    return src[j] if j >= 0 else ""


def _comparada(src: str, inicio: int, fin: int) -> bool:
    antes = src[max(0, inicio - 6) : inicio].rstrip()
    despues = src[fin : fin + 6].lstrip()
    return antes.endswith(("==", "!=", "case")) or despues.startswith(("==", "!=", ":"))


def escanear(src: str) -> list[CadenaJs]:
    res: list[CadenaJs] = []
    pila: list[_Marco] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            fin = src.find("\n", i)
            i = n if fin < 0 else fin
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            fin = src.find("*/", i + 2)
            i = n if fin < 0 else fin + 2
            continue
        if c == "/" and (_significativo_antes(src, i) in _ANTES_DE_REGEX or _significativo_antes(src, i) == ""):
            i = _fin_regex(src, i)
            continue
        if c in "'\"`":
            fin = _fin_cadena(src, i, c)
            crudo = src[i + 1 : fin - 1]
            texto = des_escapar(crudo)
            marco = next((m for m in reversed(pila) if m.tipo != "["), None)
            funcion, receptor = (marco.funcion, marco.receptor) if marco and marco.tipo == "(" else (None, None)
            if pila and pila[-1].tipo == "(" and pila[-1].primera is None:
                pila[-1].primera = texto
            contexto = tuple(m.nombre() for m in pila if m.tipo == "(" and m.funcion)
            argumento = marco.arg if marco and marco.tipo == "(" else -1
            res.append(CadenaJs(i, fin, c, texto, funcion, receptor, _comparada(src, i, fin), contexto, argumento))
            i = fin
            continue
        if c == "(":
            pila.append(_Marco("(", *_llamada(src, i)))
        elif c in "[{":
            pila.append(_Marco(c))
        elif c == "," and pila and pila[-1].tipo == "(":
            pila[-1].arg += 1
        elif c in ")]}" and pila:
            pila.pop()
        i += 1
    return res


def _fin_regex(src: str, i: int) -> int:
    j, en_clase = i + 1, False
    while j < len(src) and src[j] != "\n":
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "[":
            en_clase = True
        elif c == "]":
            en_clase = False
        elif c == "/" and not en_clase:
            j += 1
            while j < len(src) and src[j].isalpha():
                j += 1
            return j
        j += 1
    return i + 1  # no era una expresión regular: se sigue como división


def reemplazar(src: str, cadenas: Sequence[CadenaJs], nuevos: Mapping[int, str]) -> str:
    partes: list[str] = []
    ultimo = 0
    for c in sorted(cadenas, key=lambda c: c.inicio):
        nuevo = nuevos.get(c.inicio)
        if nuevo is not None and nuevo != c.texto:
            partes.append(src[ultimo : c.inicio])
            partes.append(c.comilla + escapar(nuevo, c.comilla) + c.comilla)
            ultimo = c.fin
    partes.append(src[ultimo:])
    return "".join(partes)

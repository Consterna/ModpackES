"""NBT binario (FTB Quests 1.12 guarda las misiones así): lectura y escritura sin pérdidas.

Las cadenas usan el «UTF-8 modificado» de Java (el carácter nulo va como C0 80 y los emojis como dos
sustitutos de 3 bytes). Los números se conservan como bytes crudos, así que reescribir un archivo sin
cambios da exactamente el mismo NBT.
"""

from __future__ import annotations

import gzip
import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

FIN, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LISTA, COMPUESTO, INT_ARRAY, LONG_ARRAY = range(13)
_TAMANO_FIJO = {BYTE: 1, SHORT: 2, INT: 4, LONG: 8, FLOAT: 4, DOUBLE: 8}
_TAMANO_ARRAY = {BYTE_ARRAY: 1, INT_ARRAY: 4, LONG_ARRAY: 8}
Compresion = Literal["gzip", "zlib", "ninguna"]


@dataclass(slots=True)
class Lista:
    tipo: int
    elementos: list[Valor] = field(default_factory=list["Valor"])


@dataclass(slots=True)
class Compuesto:
    hijos: dict[str, tuple[int, Valor]] = field(default_factory=dict[str, tuple[int, "Valor"]])


Valor = bytes | str | Lista | Compuesto  #: bytes = número o array crudo


@dataclass(slots=True)
class Raiz:
    tipo: int
    nombre: str
    valor: Valor


# ------------------------------------------------------------------ UTF-8 modificado de Java


def mutf8_decodificar(datos: bytes) -> str:
    unidades: list[int] = []
    i = 0
    while i < len(datos):
        b = datos[i]
        if b < 0x80:
            unidades.append(b)
            i += 1
        elif b >> 5 == 0b110:
            unidades.append(((b & 0x1F) << 6) | (datos[i + 1] & 0x3F))
            i += 2
        elif b >> 4 == 0b1110:
            unidades.append(((b & 0x0F) << 12) | ((datos[i + 1] & 0x3F) << 6) | (datos[i + 2] & 0x3F))
            i += 3
        else:
            raise ValueError(f"Byte no válido en UTF-8 modificado: {b:#x}")
    # Junta pares de sustitutos en caracteres completos
    salida: list[str] = []
    j = 0
    while j < len(unidades):
        u = unidades[j]
        if 0xD800 <= u <= 0xDBFF and j + 1 < len(unidades) and 0xDC00 <= unidades[j + 1] <= 0xDFFF:
            salida.append(chr(0x10000 + ((u - 0xD800) << 10) + (unidades[j + 1] - 0xDC00)))
            j += 2
        else:
            salida.append(chr(u))
            j += 1
    return "".join(salida)


def mutf8_codificar(texto: str) -> bytes:
    salida = bytearray()
    for ch in texto:
        punto = ord(ch)
        unidades = (
            [punto] if punto < 0x10000 else [0xD800 + ((punto - 0x10000) >> 10), 0xDC00 + ((punto - 0x10000) & 0x3FF)]
        )
        for u in unidades:
            if 0 < u < 0x80:
                salida.append(u)
            elif u < 0x800:
                salida += bytes((0xC0 | (u >> 6), 0x80 | (u & 0x3F)))
            else:
                salida += bytes((0xE0 | (u >> 12), 0x80 | ((u >> 6) & 0x3F), 0x80 | (u & 0x3F)))
    return bytes(salida)


# ------------------------------------------------------------------ lectura


class _Lector:
    def __init__(self, datos: bytes) -> None:
        self.datos = datos
        self.pos = 0

    def tomar(self, n: int) -> bytes:
        if self.pos + n > len(self.datos):
            raise ValueError("NBT cortado")
        trozo = self.datos[self.pos : self.pos + n]
        self.pos += n
        return trozo

    def entero(self, formato: str) -> int:
        n = struct.calcsize(formato)
        return int(struct.unpack(formato, self.tomar(n))[0])

    def cadena(self) -> str:
        return mutf8_decodificar(self.tomar(self.entero(">H")))

    def valor(self, tipo: int) -> Valor:
        if tipo in _TAMANO_FIJO:
            return self.tomar(_TAMANO_FIJO[tipo])
        if tipo in _TAMANO_ARRAY:
            largo_crudo = self.tomar(4)
            (largo,) = struct.unpack(">i", largo_crudo)
            return largo_crudo + self.tomar(max(0, largo) * _TAMANO_ARRAY[tipo])
        if tipo == STRING:
            return self.cadena()
        if tipo == LISTA:
            tipo_elem = self.entero(">b")
            largo = self.entero(">i")
            return Lista(tipo_elem, [self.valor(tipo_elem) for _ in range(max(0, largo))])
        if tipo == COMPUESTO:
            c = Compuesto()
            while (t := self.entero(">b")) != FIN:
                nombre = self.cadena()
                c.hijos[nombre] = (t, self.valor(t))
            return c
        raise ValueError(f"Tipo de etiqueta NBT desconocido: {tipo}")


def descomprimir(datos: bytes) -> tuple[bytes, Compresion]:
    if datos[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(datos), "gzip"
        except (EOFError, OSError, zlib.error) as e:  # gzip truncado o dañado: un solo tipo de error para quien llama
            raise ValueError(f"Archivo NBT comprimido dañado: {e}") from e
    if datos[:1] == b"\x78":
        try:
            return zlib.decompress(datos), "zlib"
        except zlib.error:
            pass
    return datos, "ninguna"


def leer(datos: bytes) -> tuple[Raiz, Compresion]:
    crudo, compresion = descomprimir(datos)
    lector = _Lector(crudo)
    tipo = lector.entero(">b")
    nombre = lector.cadena()
    raiz = Raiz(tipo, nombre, lector.valor(tipo))
    if lector.pos != len(crudo):
        raise ValueError("Sobran bytes después del NBT")
    return raiz, compresion


# ------------------------------------------------------------------ escritura


def _cadena(texto: str) -> bytes:
    datos = mutf8_codificar(texto)
    if len(datos) > 0xFFFF:
        raise ValueError("Cadena NBT demasiado larga")
    return struct.pack(">H", len(datos)) + datos


def _valor(tipo: int, valor: Valor) -> bytes:
    if tipo in _TAMANO_FIJO or tipo in _TAMANO_ARRAY:
        assert isinstance(valor, bytes)
        return valor
    if tipo == STRING:
        assert isinstance(valor, str)
        return _cadena(valor)
    if tipo == LISTA:
        assert isinstance(valor, Lista)
        return struct.pack(">bi", valor.tipo, len(valor.elementos)) + b"".join(
            _valor(valor.tipo, e) for e in valor.elementos
        )
    if tipo == COMPUESTO:
        assert isinstance(valor, Compuesto)
        partes = [struct.pack(">b", t) + _cadena(k) + _valor(t, v) for k, (t, v) in valor.hijos.items()]
        return b"".join(partes) + b"\x00"
    raise ValueError(f"Tipo de etiqueta NBT desconocido: {tipo}")


def escribir(raiz: Raiz, compresion: Compresion = "gzip") -> bytes:
    crudo = struct.pack(">b", raiz.tipo) + _cadena(raiz.nombre) + _valor(raiz.tipo, raiz.valor)
    if compresion == "gzip":
        return gzip.compress(crudo, mtime=0)
    if compresion == "zlib":
        return zlib.compress(crudo)
    return crudo


# ------------------------------------------------------------------ recorrido de textos


@dataclass(frozen=True, slots=True)
class CadenaNbt:
    """Una cadena dentro del árbol, con la clave a la que pertenece y cómo reemplazarla."""

    campo: str | None
    texto: str
    contenedor: Compuesto | Lista
    posicion: str | int


def cadenas(raiz: Raiz) -> Iterator[CadenaNbt]:
    def recorrer(valor: Valor, campo: str | None) -> Iterator[CadenaNbt]:
        if isinstance(valor, Compuesto):
            for k, (t, v) in valor.hijos.items():
                if t == STRING and isinstance(v, str):
                    yield CadenaNbt(k, v, valor, k)
                else:
                    yield from recorrer(v, k)
        elif isinstance(valor, Lista):
            for i, e in enumerate(valor.elementos):
                if valor.tipo == STRING and isinstance(e, str):
                    yield CadenaNbt(campo, e, valor, i)
                else:
                    yield from recorrer(e, campo)

    yield from recorrer(raiz.valor, None)


def poner(cadena: CadenaNbt, texto: str) -> None:
    if isinstance(cadena.contenedor, Compuesto):
        assert isinstance(cadena.posicion, str)
        tipo, _ = cadena.contenedor.hijos[cadena.posicion]
        cadena.contenedor.hijos[cadena.posicion] = (tipo, texto)
    else:
        assert isinstance(cadena.posicion, int)
        cadena.contenedor.elementos[cadena.posicion] = texto

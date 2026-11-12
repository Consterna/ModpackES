"""Piezas comunes de los módulos de contenido (misiones, libros, scripts, mods)."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..formatos import json_texto
from ..fuentes.instancia import Instancia
from ..nucleo.dialectos import DIALECTO_POR_DEFECTO, VARIANTES
from ..nucleo.mascara import es_traducible
from ..nucleo.traductor import Traductor
from ..salida.copias import Respaldo
from ..salida.resource_pack import PackSalida

#: Clave de traducción en lugar de texto: «quest.x.title», «{ftbquests.chapter.x}». La traduce el módulo de mods.
_CLAVE = re.compile(r"\{?[a-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)+\}?")


def contar(n: int, singular: str, plural: str = "") -> str:
    """«1 mod», «3 mods»."""
    return f"{n} {singular if n == 1 else plural or singular + 's'}"


def parece_clave(texto: str) -> bool:
    return bool(_CLAVE.fullmatch(texto.strip()))


def unidades(texto: str, literal: bool = False) -> list[str]:
    """Las partes traducibles de un texto: el texto entero o las de un componente JSON."""
    if not texto.strip() or parece_clave(texto):
        return []
    partes = json_texto.extraer(texto, literal)
    candidatos = [texto] if partes is None else partes
    return [p for p in candidatos if es_traducible(p) and not parece_clave(p)]


def aplicar(texto: str, traducciones: Mapping[str, str], literal: bool = False) -> str:
    if not texto.strip() or parece_clave(texto):
        return texto
    return json_texto.reconstruir(texto, traducciones, literal)


@dataclass(slots=True)
class Contexto:
    instancia: Instancia
    respaldo: Respaldo
    dialecto: str = DIALECTO_POR_DEFECTO
    variantes: tuple[str, ...] = VARIANTES
    registro: Callable[[str], None] = field(default=lambda _m: None)
    pack: PackSalida | None = None  #: resource pack de salida (libros y mods)

    def pack_listo(self) -> PackSalida:
        """El pack de salida, preparado (pack.mcmeta y marca) la primera vez que se pide."""
        if self.pack is None:
            self.pack = PackSalida(self.instancia)
        if not (self.pack.raiz / "pack.mcmeta").is_file():
            self.pack.preparar()
        return self.pack


@dataclass(frozen=True, slots=True)
class Pieza:
    texto: str
    pista: str = ""


@dataclass(slots=True)
class Resumen:
    archivos: list[Path] = field(default_factory=list[Path])
    traducidos: int = 0
    pendientes: int = 0  #: textos que siguen en inglés (sin traducción disponible)

    def __str__(self) -> str:
        escritos = contar(len(self.archivos), "archivo escrito", "archivos escritos")
        traducidos = contar(self.traducidos, "texto traducido", "textos traducidos")
        extra = ", " + contar(self.pendientes, "sigue en inglés", "siguen en inglés") if self.pendientes else ""
        return f"{escritos}, {traducidos}{extra}"


class Modulo(Protocol):
    nombre: str
    ambito: str

    def detectar(self) -> bool: ...

    def describir(self) -> str: ...

    def recolectar(self) -> list[Pieza]: ...

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen: ...

    def restaurar(self) -> list[Path]: ...


#: Cuántos caracteres de un texto vecino o de un título se mandan como contexto.
LARGO_VECINO = 100
MARCAS_VECINDAD = ("dentro de «", "viene después de «")


def _recortar(texto: str) -> str:
    plano = " ".join(texto.split())
    return plano if len(plano) <= LARGO_VECINO else plano[: LARGO_VECINO - 1] + "…"


def con_vecindad(piezas: Sequence[Pieza], es_titulo: Callable[[Pieza], bool]) -> list[Pieza]:
    """Le agrega a cada pieza el título bajo el que está y el texto que viene justo antes (en el mismo archivo).

    Una descripción de misión o un párrafo de un libro suelto no dicen de qué tratan; con el título y la línea
    anterior el motor puede elegir el sentido, el tono y los términos. Los títulos no llevan contexto propio.
    """
    titulo = anterior = ""
    salida: list[Pieza] = []
    for p in piezas:
        if es_titulo(p):
            titulo, anterior = _recortar(p.texto), ""
            salida.append(p)
            continue
        partes = [p.pista] if p.pista else []
        if titulo:
            partes.append(f"dentro de «{titulo}»")
        if anterior:
            partes.append(f"viene después de «{anterior}»")
        salida.append(Pieza(p.texto, " · ".join(partes)))
        anterior = _recortar(p.texto)
    return salida


def quitar_vecindad(pista: str) -> str:
    """La pista sin lo que agrega `con_vecindad` (para medir cuánto aporta)."""
    return " · ".join(parte for parte in pista.split(" · ") if not parte.startswith(MARCAS_VECINDAD))


#: Cuántas pistas distintas se mandan por texto cuando el mismo texto sale en varios sitios.
MAX_PISTAS = 3


def reunir_pistas(piezas: list[Pieza]) -> dict[str, str]:
    """{texto: pista}. Si el mismo texto sale con varias pistas (claves distintas), se juntan hasta 3."""
    por_texto: dict[str, list[str]] = {}
    for p in piezas:
        if p.pista:
            vistas = por_texto.setdefault(p.texto, [])
            if p.pista not in vistas and len(vistas) < MAX_PISTAS:
                vistas.append(p.pista)
    return {texto: " | ".join(vistas) for texto, vistas in por_texto.items()}


def traducir_modulo(modulo: Modulo, traductor: Traductor) -> Resumen:
    """Recolecta los textos del módulo, los traduce (memoria, glosario o motor) y escribe el resultado."""
    piezas = modulo.recolectar()
    pistas = reunir_pistas(piezas)
    resultado = traductor.traducir([p.texto for p in piezas], modulo.ambito, pistas)
    return modulo.escribir(resultado.traducciones)

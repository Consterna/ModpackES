"""Piezas comunes de los módulos de contenido (misiones, libros, scripts, mods)."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
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
        extra = f", {self.pendientes} siguen en inglés" if self.pendientes else ""
        return f"{len(self.archivos)} archivos escritos, {self.traducidos} textos traducidos{extra}"


class Modulo(Protocol):
    nombre: str
    ambito: str

    def detectar(self) -> bool: ...

    def describir(self) -> str: ...

    def recolectar(self) -> list[Pieza]: ...

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen: ...

    def restaurar(self) -> list[Path]: ...


def traducir_modulo(modulo: Modulo, traductor: Traductor) -> Resumen:
    """Recolecta los textos del módulo, los traduce (memoria, glosario o motor) y escribe el resultado."""
    piezas = modulo.recolectar()
    pistas = {p.texto: p.pista for p in piezas if p.pista}
    resultado = traductor.traducir([p.texto for p in piezas], modulo.ambito, pistas)
    return modulo.escribir(resultado.traducciones)

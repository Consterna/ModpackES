"""Lectura de options.txt: idioma del juego y resource packs activados (en orden de prioridad)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Packs internos del juego y de los loaders, que no son archivos de la carpeta resourcepacks.
INTERNOS = frozenset({"vanilla", "mod_resources", "fabric", "programer_art", "programmer_art", "high_contrast"})


@dataclass(frozen=True, slots=True)
class Opciones:
    idioma: str | None = None
    packs: tuple[str, ...] = field(default_factory=tuple[str, ...])  #: nombres de archivo, de menor a mayor prioridad
    con_prefijo: bool = False  #: si la instancia escribe los packs como «file/Nombre»


def leer(juego: Path) -> Opciones:
    try:
        lineas = (juego / "options.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return Opciones()
    idioma: str | None = None
    crudos: list[str] = []
    for linea in lineas:
        clave, _, valor = linea.partition(":")
        if clave == "lang":
            idioma = valor.strip().lower() or None
        elif clave == "resourcePacks":
            try:
                lista: Any = json.loads(valor)
            except ValueError:
                continue
            if isinstance(lista, list):
                crudos = [str(x) for x in lista]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    con_prefijo = any(p.startswith("file/") for p in crudos)
    packs = tuple(p.removeprefix("file/") for p in crudos if p.removeprefix("file/") not in INTERNOS)
    return Opciones(idioma, packs, con_prefijo)

"""Instancias de los lanzadores conocidos, para elegirlas de una lista."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .instancia import resolver_carpeta_juego


@dataclass(frozen=True, slots=True)
class InstanciaEncontrada:
    lanzador: str
    nombre: str
    juego: Path


def _carpeta_instancias_prism(base: Path) -> Path:
    """Prism y MultiMC permiten cambiar la carpeta de instancias en su .cfg."""
    for cfg in (base / "prismlauncher.cfg", base / "multimc.cfg"):
        try:
            texto = cfg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if m := re.search(r"^InstanceDir=(.+)$", texto, re.M):
            ruta = Path(m.group(1).strip())
            return ruta if ruta.is_absolute() else base / ruta
    return base / "instances"


def _nombre_prism(carpeta: Path) -> str:
    try:
        texto = (carpeta / "instance.cfg").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return carpeta.name
    m = re.search(r"^name=(.+)$", texto, re.M)
    return m.group(1).strip() if m else carpeta.name


def _nombre_json(ruta: Path, clave: str, defecto: str) -> str:
    try:
        datos: Any = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return defecto
    valor = cast(dict[str, Any], datos).get(clave) if isinstance(datos, dict) else None
    return str(valor) if isinstance(valor, str) and valor.strip() else defecto


def _subcarpetas(base: Path) -> list[Path]:
    """Las carpetas dentro de `base`, en orden; ninguna si no existe o no se puede leer (sin permiso, red caída)."""
    try:
        return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    except OSError:
        return []


def buscar() -> list[InstanciaEncontrada]:
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    home = Path.home()
    encontradas: list[InstanciaEncontrada] = []

    def agregar(lanzador: str, carpeta: Path, nombre: str) -> None:
        juego = resolver_carpeta_juego(carpeta)
        if juego is not None:
            encontradas.append(InstanciaEncontrada(lanzador, nombre, juego))

    for lanzador, base in (("Prism Launcher", appdata / "PrismLauncher"), ("MultiMC", home / "MultiMC")):
        for c in _subcarpetas(_carpeta_instancias_prism(base)):
            if not c.name.startswith(".") and (c / "instance.cfg").exists():
                nombre = _nombre_prism(c)
                agregar(lanzador, c, nombre if nombre == c.name else f"{nombre} ({c.name})")
    for c in _subcarpetas(home / "curseforge" / "minecraft" / "Instances"):
        agregar("CurseForge", c, _nombre_json(c / "minecraftinstance.json", "name", c.name))
    for lanzador, base in (
        ("Modrinth", appdata / "ModrinthApp" / "profiles"),
        ("ATLauncher", appdata / "ATLauncher" / "instances"),
        ("GDLauncher", appdata / "gdlauncher_carbon" / "data" / "instances"),
    ):
        for c in _subcarpetas(base):
            agregar(lanzador, c, c.name)
    oficial = appdata / ".minecraft"
    if (oficial / "mods").is_dir():
        agregar("Launcher oficial", oficial, ".minecraft")
    return encontradas

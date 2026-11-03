"""Idiomas oficiales de Minecraft (inglés del jar del juego y español de los assets del lanzador)."""

from __future__ import annotations

import json
import os
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ..formatos import lang_json, lang_legacy
from .version import Version, formato_desde_jar


def raices_de_lanzadores() -> list[Path]:
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    return [
        appdata / "PrismLauncher",
        appdata / ".minecraft",
        Path.home() / "curseforge" / "minecraft" / "Install",
        appdata / "ModrinthApp" / "meta",
        appdata / "ATLauncher",
        Path.home() / "MultiMC",
    ]


@dataclass(slots=True)
class Vanilla:
    """Textos oficiales: {idioma: {clave: texto}} más el formato de pack que dice el propio jar."""

    textos: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])
    formato_recursos: tuple[int, int] | None = None
    formato_datos: tuple[int, int] | None = None
    jar: Path | None = None


def _jar_cliente(raiz: Path, v: str) -> Path | None:
    for ruta in (
        raiz / "libraries" / "com" / "mojang" / "minecraft" / v / f"minecraft-{v}-client.jar",
        raiz / "versions" / v / f"{v}.jar",
    ):
        if ruta.is_file():
            return ruta
    return None


def _indice(raiz: Path, v: str) -> str | None:
    for ruta in (raiz / "meta" / "net.minecraft" / f"{v}.json", raiz / "versions" / v / f"{v}.json"):
        try:
            datos: Any = json.loads(ruta.read_text(encoding="utf-8"))
            return str(cast(dict[str, Any], datos)["assetIndex"]["id"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def _desde_assets(raiz: Path, indice: str | None, idioma: str, legacy: bool) -> dict[str, str]:
    """Solo el índice exacto de la versión: el de otra versión trae otras claves y engañaría a la tabla."""
    if indice is None:
        return {}
    idx = raiz / "assets" / "indexes" / f"{indice}.json"
    try:
        objetos = cast(dict[str, Any], json.loads(idx.read_text(encoding="utf-8"))["objects"])
    except (OSError, ValueError, KeyError):
        return {}
    nombres = [f"minecraft/lang/{idioma}.json"] if not legacy else [f"minecraft/lang/{idioma}.lang"]
    if legacy:
        nombres.append(f"minecraft/lang/{idioma[:3]}{idioma[3:].upper()}.lang")
    for nombre in nombres:
        if nombre in objetos:
            h = str(objetos[nombre]["hash"])
            ruta = raiz / "assets" / "objects" / h[:2] / h
            if ruta.is_file():
                datos = ruta.read_bytes()
                return lang_legacy.leer(datos) if legacy else lang_json.leer(datos)
    return {}


def cargar(version: Version, idiomas: Iterable[str], raices: Iterable[Path] | None = None) -> Vanilla:
    legacy = version < Version.de("1.13")
    v = version.texto
    res = Vanilla()
    for raiz in raices if raices is not None else raices_de_lanzadores():
        jar = _jar_cliente(raiz, v)
        if jar is None:
            continue
        res.jar = jar
        try:
            with zipfile.ZipFile(jar) as z:
                nombres = set(z.namelist())
                if "version.json" in nombres:
                    vj = z.read("version.json")
                    res.formato_recursos = formato_desde_jar(vj, "resource")
                    res.formato_datos = formato_desde_jar(vj, "data")
                ingles = "assets/minecraft/lang/en_us.lang" if legacy else "assets/minecraft/lang/en_us.json"
                if ingles in nombres:
                    datos = z.read(ingles)
                    res.textos["en_us"] = lang_legacy.leer(datos) if legacy else lang_json.leer(datos)
        except (zipfile.BadZipFile, OSError):
            continue
        indice = _indice(raiz, v)
        for idioma in idiomas:
            if idioma not in res.textos and (t := _desde_assets(raiz, indice, idioma, legacy)):
                res.textos[idioma] = t
        break
    return res

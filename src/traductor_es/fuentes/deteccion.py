"""Versión de Minecraft y loader de una instancia, sin importar el lanzador.

Orden de confianza: metadatos del lanzador → logs/latest.log → metadatos de los mods → nombres de los jars.
"""

from __future__ import annotations

import json
import re
import tomllib
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .version import Version

LOADERS = ("forge", "neoforge", "fabric", "quilt")


@dataclass(frozen=True, slots=True)
class Deteccion:
    version: Version | None
    loader: str | None  #: «forge», «neoforge», «fabric», «quilt» o None (vanilla / no se sabe)
    origen: str  #: de dónde salió el dato, para mostrarlo al usuario


def _json(ruta: Path) -> Any:
    try:
        return json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _version(texto: object) -> Version | None:
    if not isinstance(texto, str):
        return None
    try:
        return Version.de(texto)
    except ValueError:
        return None


def _prism(juego: Path) -> Deteccion | None:
    datos = _json(juego.parent / "mmc-pack.json")
    if not isinstance(datos, dict):
        return None
    componentes = cast(list[object], cast(dict[str, Any], datos).get("components", []))
    uids = {
        cast(dict[str, Any], c).get("uid"): cast(dict[str, Any], c).get("version")
        for c in componentes
        if isinstance(c, dict)
    }
    loader = next(
        (n for uid, n in (("net.neoforged", "neoforge"), ("net.minecraftforge", "forge"),
                          ("net.fabricmc.fabric-loader", "fabric"), ("org.quiltmc.quilt-loader", "quilt"))
         if uid in uids),
        None,
    )  # fmt: skip
    version = _version(uids.get("net.minecraft"))
    return Deteccion(version, loader, "Prism/MultiMC (mmc-pack.json)") if version else None


def _curseforge(juego: Path) -> Deteccion | None:
    for ruta in (juego / "minecraftinstance.json", juego.parent / "minecraftinstance.json"):
        datos = _json(ruta)
        if isinstance(datos, dict):
            d = cast(dict[str, Any], datos)
            base = d.get("baseModLoader")
            nombre = str(cast(dict[str, Any], base).get("name", "")).lower() if isinstance(base, dict) else ""
            loader = next((ld for ld in ("neoforge", "forge", "fabric", "quilt") if nombre.startswith(ld)), None)
            version = _version(d.get("gameVersion"))
            if version:
                return Deteccion(version, loader, "CurseForge (minecraftinstance.json)")
    return None


_LOG_FABRIC = re.compile(r"Loading Minecraft (\d+(?:\.\d+){1,2}) with (Fabric|Quilt) Loader")
_LOG_MC = re.compile(r"--fml\.mcVersion,\s*(\d+(?:\.\d+){1,2})")
_LOG_ANTIGUO = re.compile(r"Minecraft Forge v[\d.]+ Initialized|MinecraftForge v[\d.]+ Initialized")
_LOG_VERSION_ANTIGUA = re.compile(r"Minecraft (?:version|Version)?\s*:?\s*(1\.\d+(?:\.\d+)?)\b")


def _log(juego: Path) -> Deteccion | None:
    ruta = juego / "logs" / "latest.log"
    try:
        with ruta.open(encoding="utf-8", errors="replace") as f:
            inicio = f.read(200_000)
    except OSError:
        return None
    if m := _LOG_FABRIC.search(inicio):
        return Deteccion(Version.de(m.group(1)), m.group(2).lower(), "logs/latest.log")
    if m := _LOG_MC.search(inicio):
        loader = "neoforge" if "neoForgeVersion" in inicio or "fml.neoForgeVersion" in inicio else "forge"
        return Deteccion(Version.de(m.group(1)), loader, "logs/latest.log")
    if _LOG_ANTIGUO.search(inicio) and (m := _LOG_VERSION_ANTIGUA.search(inicio)):
        return Deteccion(Version.de(m.group(1)), "forge", "logs/latest.log")
    return None


_RANGO = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def _de_mods(jars: Iterable[Path]) -> Deteccion | None:
    """Vota con los metadatos de cada mod: el loader para el que está hecho y la versión de Minecraft que pide."""
    loaders: Counter[str] = Counter()
    versiones: Counter[str] = Counter()
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as z:
                nombres = set(z.namelist())
                if "META-INF/neoforge.mods.toml" in nombres:
                    loaders["neoforge"] += 1
                    versiones.update(_toml_mc(z.read("META-INF/neoforge.mods.toml")))
                elif "META-INF/mods.toml" in nombres:
                    loaders["forge"] += 1
                    versiones.update(_toml_mc(z.read("META-INF/mods.toml")))
                elif "quilt.mod.json" in nombres:
                    loaders["quilt"] += 1
                elif "fabric.mod.json" in nombres:
                    loaders["fabric"] += 1
                    versiones.update(_fabric_mc(z.read("fabric.mod.json")))
                elif "mcmod.info" in nombres:
                    loaders["forge"] += 1
                    versiones.update(_mcmod_mc(z.read("mcmod.info")))
        except (zipfile.BadZipFile, OSError, KeyError):
            continue
    if not loaders:
        return None
    loader = loaders.most_common(1)[0][0]
    version = _version(versiones.most_common(1)[0][0]) if versiones else None
    return Deteccion(version, loader, "metadatos de los mods")


def _toml_mc(datos: bytes) -> list[str]:
    try:
        toml = tomllib.loads(datos.decode("utf-8", errors="replace"))
    except tomllib.TOMLDecodeError:
        return []
    salida: list[str] = []
    for deps in cast(dict[str, Any], toml.get("dependencies", {})).values():
        for dep in cast(list[Any], deps) if isinstance(deps, list) else []:
            if isinstance(dep, dict) and cast(dict[str, Any], dep).get("modId") == "minecraft":
                rango = str(cast(dict[str, Any], dep).get("versionRange", ""))
                if m := _RANGO.search(rango):
                    salida.append(m.group(1))
    return salida


def _fabric_mc(datos: bytes) -> list[str]:
    try:
        meta: Any = json.loads(datos.decode("utf-8", errors="replace"), strict=False)
    except ValueError:
        return []
    deps: object = cast(dict[str, Any], meta).get("depends", {}) if isinstance(meta, dict) else {}
    valor = cast(dict[str, Any], deps).get("minecraft") if isinstance(deps, dict) else None
    textos = (
        [valor]
        if isinstance(valor, str)
        else [v for v in cast(list[Any], valor) if isinstance(v, str)]
        if isinstance(valor, list)
        else []
    )
    return [m.group(1) for t in textos if (m := _RANGO.search(t))]


def _mcmod_mc(datos: bytes) -> list[str]:
    try:
        meta: Any = json.loads(datos.decode("utf-8", errors="replace"), strict=False)
    except ValueError:
        return []
    lista = cast(dict[str, Any], meta).get("modList", []) if isinstance(meta, dict) else meta
    return [
        str(cast(dict[str, Any], m)["mcversion"])
        for m in (cast(list[Any], lista) if isinstance(lista, list) else [])
        if isinstance(m, dict) and "mcversion" in m
    ]


_EN_NOMBRE = re.compile(r"(?<![\d.])(1\.(?:[7-9]|1\d|2\d)(?:\.\d{1,2})?|2\d\.\d(?:\.\d)?)(?![\d.])")


def _de_nombres(jars: Iterable[Path]) -> Deteccion | None:
    votos: Counter[str] = Counter(v for j in jars for v in _EN_NOMBRE.findall(j.name))
    if not votos:
        return None
    return Deteccion(Version.de(votos.most_common(1)[0][0]), None, "nombres de los jars")


def detectar(juego: Path, jars: list[Path]) -> Deteccion:
    """Combina las fuentes: la primera que da versión manda; el loader se completa con la siguiente que lo sepa."""
    encontradas = [d for d in (_prism(juego), _curseforge(juego), _log(juego)) if d]
    if not encontradas or encontradas[0].loader is None:
        for extra in (_de_mods(jars), _de_nombres(jars)):
            if extra:
                encontradas.append(extra)
    version = next((d for d in encontradas if d.version), None)
    loader = next((d.loader for d in encontradas if d.loader), None)
    if version is None:
        return Deteccion(None, loader, "no se pudo detectar")
    return Deteccion(version.version, loader, version.origen)

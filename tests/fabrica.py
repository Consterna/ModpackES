"""Fábrica de instancias de Minecraft falsas para las pruebas."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from pathlib import Path

Archivos = Mapping[str, "bytes | str | Mapping[str, object]"]


def _bytes(contenido: bytes | str | Mapping[str, object]) -> bytes:
    if isinstance(contenido, bytes):
        return contenido
    if isinstance(contenido, str):
        return contenido.encode("utf-8")
    return json.dumps(contenido, ensure_ascii=False).encode("utf-8")


def zip_en_memoria(archivos: Archivos, anidados: Mapping[str, Archivos] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for nombre, contenido in archivos.items():
            z.writestr(nombre, _bytes(contenido))
        for nombre, contenido in (anidados or {}).items():
            z.writestr(nombre, zip_en_memoria(contenido))
    return buffer.getvalue()


def jar(ruta: Path, archivos: Archivos, anidados: Mapping[str, Archivos] | None = None) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(zip_en_memoria(archivos, anidados))
    return ruta


def lang(namespace: str, idioma: str, textos: Mapping[str, str], legacy: bool = False) -> dict[str, bytes]:
    if legacy:
        return {f"assets/{namespace}/lang/{idioma}.lang": "\n".join(f"{k}={v}" for k, v in textos.items()).encode()}
    return {f"assets/{namespace}/lang/{idioma}.json": json.dumps(dict(textos), ensure_ascii=False).encode()}


def prism(base: Path, version: str, loader: str | None = "forge", nombre: str = "Pack") -> Path:
    """Instancia de Prism: <base>/<nombre>/{instance.cfg, mmc-pack.json, minecraft/}. Devuelve la carpeta del juego."""
    carpeta = base / nombre
    juego = carpeta / "minecraft"
    (juego / "mods").mkdir(parents=True, exist_ok=True)
    (carpeta / "instance.cfg").write_text(f"name={nombre}\n", encoding="utf-8")
    uid = {"forge": "net.minecraftforge", "neoforge": "net.neoforged", "fabric": "net.fabricmc.fabric-loader",
           "quilt": "org.quiltmc.quilt-loader"}  # fmt: skip
    componentes: list[dict[str, str]] = [{"uid": "net.minecraft", "version": version}]
    if loader:
        componentes.append({"uid": uid[loader], "version": "1.0"})
    (carpeta / "mmc-pack.json").write_text(json.dumps({"components": componentes}), encoding="utf-8")
    return juego


def curseforge(base: Path, version: str, loader: str, nombre: str = "Pack") -> Path:
    juego = base / nombre
    (juego / "mods").mkdir(parents=True, exist_ok=True)
    datos = {"name": nombre, "gameVersion": version, "baseModLoader": {"name": f"{loader}-1.0"}}
    (juego / "minecraftinstance.json").write_text(json.dumps(datos), encoding="utf-8")
    return juego


def opciones(juego: Path, packs: list[str], idioma: str = "es_mx", extra: str = "") -> Path:
    ruta = juego / "options.txt"
    ruta.write_text(f"version:3465\nresourcePacks:{json.dumps(packs)}\nlang:{idioma}\n{extra}", encoding="utf-8")
    return ruta

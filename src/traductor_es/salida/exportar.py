"""Exportar la traducción: el resource pack en un .zip y un kit para servidores."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from .copias import Respaldo
from .resource_pack import NOMBRE

#: Lo que lee el servidor: misiones, scripts de servidor y datos (logros, funciones).
#: Los client_scripts los ejecuta cada jugador.
_DEL_SERVIDOR = ("config/", "kubejs/server_scripts/", "kubejs/startup_scripts/", "kubejs/data/", "patchouli_books/")

LEEME_KIT = """KIT DE TRADUCCIÓN PARA SERVIDOR
================================

1. Copia las carpetas de este kit (config, kubejs…) en la carpeta del servidor, encima de las que ya
   tiene. Son las misiones y scripts ya traducidos.
2. Los jugadores necesitan {pack}.zip: pásaselo para que lo pongan en su carpeta resourcepacks y lo
   activen, o configúralo como resource pack del servidor (server.properties → resource-pack).
3. Reinicia el servidor.

Para volver al inglés, copia de nuevo los archivos originales del modpack.
"""


def _agregar_carpeta(zf: zipfile.ZipFile, carpeta: Path, prefijo: str = "") -> int:
    n = 0
    for ruta in sorted(carpeta.rglob("*")):
        if ruta.is_file() and not ruta.name.endswith(".tmp"):
            zf.write(ruta, prefijo + ruta.relative_to(carpeta).as_posix())
            n += 1
    return n


def exportar_pack(juego: Path, destino: Path) -> int:
    """El resource pack de la traducción como .zip listo para compartir. Devuelve cuántos archivos lleva."""
    pack = juego / "resourcepacks" / NOMBRE
    if not (pack / "pack.mcmeta").is_file():
        raise ValueError("Todavía no hay traducción de mods ni de libros para exportar: traduce primero.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        return _agregar_carpeta(zf, pack)


def exportar_kit_servidor(juego: Path, destino: Path) -> int:
    """Kit para servidores: archivos traducidos que lee el servidor, el resource pack y unas instrucciones."""
    respaldo = Respaldo(juego)
    archivos = [r for r in respaldo.registrados() if r.startswith(_DEL_SERVIDOR)]
    pack = juego / "resourcepacks" / NOMBRE
    if not archivos and not (pack / "pack.mcmeta").is_file():
        raise ValueError("Todavía no hay nada traducido para el servidor: traduce primero.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for relativa in archivos:
            ruta = juego / relativa
            if ruta.is_file():
                zf.write(ruta, relativa)
                n += 1
        if (pack / "pack.mcmeta").is_file():
            interno = io.BytesIO()
            with zipfile.ZipFile(interno, "w", zipfile.ZIP_DEFLATED) as zpack:
                _agregar_carpeta(zpack, pack)
            zf.writestr(f"{NOMBRE}.zip", interno.getvalue())
            n += 1
        zf.writestr("LEEME.txt", LEEME_KIT.format(pack=NOMBRE))
    return n

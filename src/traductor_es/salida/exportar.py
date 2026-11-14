"""Exportar la traducción: el resource pack listo para publicar y un kit para servidores."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast

from .. import NOMBRE as NOMBRE_APP
from .. import REPOSITORIO, __version__
from ..fuentes.modpack import DatosModpack, datos_del_modpack
from ..fuentes.recursos import MARCA
from ..fuentes.version import rango_publicable
from ..modulos.datos import clasificar, entradas_del_zip
from .copias import Respaldo
from .paquete import nombre_de_archivo
from .resource_pack import NOMBRE, leer_marca, motores_de

#: El ícono de la app (dibujado para el proyecto) sirve de pack.png.
_ICONO = Path(__file__).resolve().parent.parent / "ui" / "icono.png"
#: Lo que el pack publicado lleva además de los archivos de la carpeta del pack.
_LEEME_PACK = "LEEME.txt"

#: Lo que lee el servidor: misiones y scripts de servidor, más los datos (logros y funciones) donde estén.
#: Los client_scripts los ejecuta cada jugador.
_DEL_SERVIDOR = ("config/", "kubejs/server_scripts/", "kubejs/startup_scripts/", "patchouli_books/")

LEEME_KIT = """KIT DE TRADUCCIÓN PARA SERVIDOR
================================

1. Copia las carpetas de este kit (config, kubejs…) en la carpeta del servidor, encima de las que ya
   tiene. Son las misiones y scripts ya traducidos.
2. Los jugadores necesitan {pack}.zip: pásaselo para que lo pongan en su carpeta resourcepacks y lo
   activen, o configúralo como resource pack del servidor (server.properties → resource-pack).
3. Reinicia el servidor.

Para volver al inglés, copia de nuevo los archivos originales del modpack.
"""


def _es_dato_del_servidor(juego: Path, relativa: str) -> bool:
    """Funciones y logros de un datapack los lee el servidor; los tips son de cliente.

    Un `.zip` (datapack comprimido) cuenta por lo que lleva dentro, no por su propia ruta.
    """
    ruta = Path(relativa)
    if ruta.suffix.lower() == ".zip":
        comprimido = juego / ruta
        return comprimido.is_file() and any(f.nombre != "tip" for _, f in entradas_del_zip(comprimido))
    formato = clasificar(ruta)
    return formato is not None and formato.nombre != "tip"


def nombre_sugerido(juego: Path) -> str:
    """Traduccion_ES_<modpack>_<versión>.zip: así se sabe para qué versión del pack es."""
    return nombre_de_archivo(datos_del_modpack(juego), ".zip", NOMBRE)


def _credito(motor: str) -> str:
    if motor.startswith("pack:"):
        return f"el resource pack «{motor.removeprefix('pack:')}»"
    proveedor, _, modelo = motor.partition(":")
    return f"{proveedor} ({modelo})" if modelo else motor


def leeme_pack(datos: DatosModpack, motores: list[str], revisado: bool, mods: list[str]) -> str:
    """Instrucciones, aviso de traducción automática y créditos del pack publicado."""
    titulo = f"{datos.nombre} {datos.version}".strip()
    hecha = "con " + ", ".join(_credito(m) for m in motores) if motores else "de forma automática"
    lineas = [
        f"TRADUCCIÓN AL ESPAÑOL DE {titulo.upper()}",
        "=" * min(80, len(titulo) + 26),
        "",
        "AVISO: es una traducción automática, hecha con " + f"{NOMBRE_APP} {__version__} {hecha}.",
        "Una persona la revisó, pero puede tener errores."
        if revisado
        else "Nadie la revisó a mano: puede tener errores.",
        "No es una traducción oficial del modpack ni de sus mods.",
        "",
        "CÓMO USARLA",
        "1. Pon este .zip, sin descomprimirlo, en la carpeta resourcepacks de la instancia.",
        "2. En el juego: Opciones → Paquetes de recursos → actívalo y súbelo por encima de los demás.",
        "3. Elige un idioma español en Opciones → Idioma.",
        "",
        "CRÉDITOS",
        f"- Textos originales: los autores de {datos.nombre} y de cada mod. Siguen siendo suyos.",
        f"- Traducción: generada con {NOMBRE_APP} ({REPOSITORIO}).",
    ]
    if mods:
        muestra = ", ".join(mods[:40]) + (f" y {len(mods) - 40} más" if len(mods) > 40 else "")
        lineas += ["", f"Traduce textos de {len(mods)} mods: {muestra}."]
    return "\n".join(lineas) + "\n"


def mcmeta_publicable(original: bytes, datos: DatosModpack) -> bytes:
    """El pack.mcmeta del pack, con la descripción del modpack y `supported_formats` cuando corresponde."""
    try:
        meta: Any = json.loads(original.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return original
    pack = cast(dict[str, Any], meta).get("pack") if isinstance(meta, dict) else None
    if not isinstance(pack, dict):
        return original
    campos = cast(dict[str, Any], pack)
    campos["description"] = f"§eTraducción al español de {datos.nombre} {datos.version}".strip()
    formato = campos.get("pack_format")
    if isinstance(formato, int) and "min_format" not in campos and (rango := rango_publicable(formato)):
        campos["supported_formats"] = list(rango)
    return (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def exportar_pack(juego: Path, destino: Path, revisado: bool = False) -> int:
    """El resource pack de la traducción como .zip listo para publicar. Devuelve cuántos archivos lleva."""
    pack = juego / "resourcepacks" / NOMBRE
    if not (pack / "pack.mcmeta").is_file():
        raise ValueError("Todavía no hay traducción de mods ni de libros para exportar: traduce primero.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        return _escribir_pack(zf, juego, revisado)


def _escribir_pack(zf: zipfile.ZipFile, juego: Path, revisado: bool) -> int:
    """Los archivos del pack publicado dentro de `zf`: los del pack, más pack.png y el LEEME."""
    pack = juego / "resourcepacks" / NOMBRE
    datos = datos_del_modpack(juego)
    assets = pack / "assets"
    mods = sorted(p.name for p in assets.iterdir() if p.is_dir() and p.name != "minecraft") if assets.is_dir() else []
    n = 0
    for ruta in sorted(pack.rglob("*")):
        relativa = ruta.relative_to(pack).as_posix()
        if not ruta.is_file() or ruta.name.endswith(".tmp") or relativa in ("pack.png", _LEEME_PACK):
            continue
        datos_archivo = ruta.read_bytes()
        if relativa == "pack.mcmeta":
            datos_archivo = mcmeta_publicable(datos_archivo, datos)
        elif relativa == MARCA:  # el índice de cambios es interno y puede ser enorme: no viaja con el pack
            marca = {k: v for k, v in leer_marca(pack).items() if k != "indice"}
            datos_archivo = (json.dumps(marca, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        zf.writestr(relativa, datos_archivo)
        n += 1
    icono = pack / "pack.png" if (pack / "pack.png").is_file() else _ICONO
    if icono.is_file():
        zf.write(icono, "pack.png")
        n += 1
    motores = motores_de(leer_marca(pack))
    zf.writestr(_LEEME_PACK, leeme_pack(datos, motores, revisado, mods))
    return n + 1


def exportar_kit_servidor(juego: Path, destino: Path) -> int:
    """Kit para servidores: archivos traducidos que lee el servidor, el resource pack y unas instrucciones."""
    respaldo = Respaldo(juego)
    archivos = [r for r in respaldo.registrados() if r.startswith(_DEL_SERVIDOR) or _es_dato_del_servidor(juego, r)]
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
                _escribir_pack(zpack, juego, revisado=False)  # el mismo pack que «Exportar pack…»
            zf.writestr(f"{NOMBRE}.zip", interno.getvalue())
            n += 1
        zf.writestr("LEEME.txt", LEEME_KIT.format(pack=NOMBRE))
    return n

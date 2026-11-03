"""Activa el pack en options.txt (arriba del todo) y, si se pide, cambia el idioma del juego.

Hay que hacerlo con el juego cerrado: al salir, Minecraft reescribe options.txt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _lista_de(linea: str) -> list[str] | None:
    """La lista JSON que va después de «clave:», o None si está dañada."""
    try:
        valor: Any = json.loads(linea.split(":", 1)[1])
    except (ValueError, IndexError):
        return None
    return [str(x) for x in valor] if isinstance(valor, list) else None  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def _linea_lista(clave: str, lista: list[str]) -> str:
    return f"{clave}:" + json.dumps(lista, ensure_ascii=False, separators=(",", ":"))


def _subir_pack(linea: str, nombre_pack: str) -> tuple[str, str | None]:
    """resourcePacks con el pack al final (arriba del todo en el juego), respetando el prefijo «file/»."""
    lista = _lista_de(linea)
    if lista is None:
        raise ValueError("No pude leer la lista de resource packs de options.txt: actívalo a mano en el juego.")
    entrada = f"file/{nombre_pack}" if any(p.startswith("file/") for p in lista) else nombre_pack
    nueva = [p for p in lista if p.removeprefix("file/") != nombre_pack] + [entrada]
    if nueva == lista:
        return linea, None
    return _linea_lista("resourcePacks", nueva), "pack activado arriba del todo"


def _sacar_de_incompatibles(linea: str, nombre_pack: str) -> str:
    lista = _lista_de(linea)
    if lista is None:
        return linea
    nueva = [p for p in lista if p.removeprefix("file/") != nombre_pack]
    return linea if nueva == lista else _linea_lista("incompatibleResourcePacks", nueva)


def activar(juego: Path, nombre_pack: str, idioma: str | None) -> list[str]:
    """Devuelve la lista de cambios hechos. Si no hay options.txt, no crea uno (el juego lo hace al abrirse).

    Lanza ValueError si options.txt tiene la lista de packs dañada (no se toca nada en ese caso).
    """
    ruta = juego / "options.txt"
    if not ruta.is_file():
        return []
    crudo = ruta.read_bytes()
    salto = "\r\n" if b"\r\n" in crudo else "\n"
    lineas = crudo.decode("utf-8", errors="replace").splitlines()
    cambios: list[str] = []
    vio_packs = vio_idioma = False
    for i, linea in enumerate(lineas):
        clave = linea.split(":", 1)[0]
        cambio: str | None = None
        if clave == "resourcePacks":
            vio_packs = True
            lineas[i], cambio = _subir_pack(linea, nombre_pack)
        elif clave == "incompatibleResourcePacks":
            lineas[i] = _sacar_de_incompatibles(linea, nombre_pack)
        elif clave == "lang" and idioma:
            vio_idioma = True
            if linea != f"lang:{idioma}":
                lineas[i], cambio = f"lang:{idioma}", f"idioma del juego: {idioma}"
        if cambio:
            cambios.append(cambio)
    if not vio_packs:
        lineas.append(_linea_lista("resourcePacks", ["vanilla", f"file/{nombre_pack}"]))
        cambios.append("pack activado")
    if idioma and not vio_idioma:
        lineas.append(f"lang:{idioma}")
        cambios.append(f"idioma del juego: {idioma}")
    if cambios:
        temporal = ruta.with_name("options.txt.tmp")
        temporal.write_bytes((salto.join(lineas) + salto).encode("utf-8"))
        temporal.replace(ruta)
    return cambios

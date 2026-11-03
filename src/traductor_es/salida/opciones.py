"""Activa el pack en options.txt (arriba del todo) y, si se pide, cambia el idioma del juego.

Hay que hacerlo con el juego cerrado: al salir, Minecraft reescribe options.txt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def activar(juego: Path, nombre_pack: str, idioma: str | None) -> list[str]:
    """Devuelve la lista de cambios hechos. Si no hay options.txt, no crea uno (el juego lo hace al abrirse)."""
    ruta = juego / "options.txt"
    if not ruta.is_file():
        return []
    crudo = ruta.read_bytes()
    salto = "\r\n" if b"\r\n" in crudo else "\n"
    lineas = crudo.decode("utf-8", errors="replace").splitlines()
    cambios: list[str] = []
    vistos = {"packs": False, "idioma": False}

    def lista_de(linea: str) -> list[str] | None:
        try:
            valor: Any = json.loads(linea.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
        return [str(x) for x in valor] if isinstance(valor, list) else None  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]

    for i, linea in enumerate(lineas):
        clave = linea.split(":", 1)[0]
        if clave == "resourcePacks":
            vistos["packs"] = True
            lista = lista_de(linea)
            if lista is None:
                continue
            entrada = f"file/{nombre_pack}" if any(p.startswith("file/") for p in lista) else nombre_pack
            nueva = [p for p in lista if p.removeprefix("file/") != nombre_pack] + [entrada]
            if nueva != lista:
                lineas[i] = "resourcePacks:" + json.dumps(nueva, ensure_ascii=False, separators=(",", ":"))
                cambios.append("pack activado arriba del todo")
        elif clave == "incompatibleResourcePacks":
            lista = lista_de(linea)
            if lista is not None:
                nueva = [p for p in lista if p.removeprefix("file/") != nombre_pack]
                if nueva != lista:
                    lineas[i] = "incompatibleResourcePacks:" + json.dumps(
                        nueva, ensure_ascii=False, separators=(",", ":")
                    )
        elif clave == "lang" and idioma:
            vistos["idioma"] = True
            if linea != f"lang:{idioma}":
                lineas[i] = f"lang:{idioma}"
                cambios.append(f"idioma del juego: {idioma}")
    if not vistos["packs"]:
        lineas.append("resourcePacks:" + json.dumps(["vanilla", f"file/{nombre_pack}"], separators=(",", ":")))
        cambios.append("pack activado")
    if idioma and not vistos["idioma"]:
        lineas.append(f"lang:{idioma}")
        cambios.append(f"idioma del juego: {idioma}")
    if cambios:
        temporal = ruta.with_name("options.txt.tmp")
        temporal.write_bytes((salto.join(lineas) + salto).encode("utf-8"))
        temporal.replace(ruta)
    return cambios

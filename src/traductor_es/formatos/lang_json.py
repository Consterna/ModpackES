"""Archivos de idioma JSON (Minecraft 1.13+): `assets/<mod>/lang/<idioma>.json`."""

from __future__ import annotations

import json
from typing import Any, cast

import json5

from .lang_legacy import BOM


def leer(datos: bytes | str) -> dict[str, str]:
    """Lee un lang JSON. Acepta comentarios y comas finales (hay mods que los dejan). Solo devuelve textos."""
    texto = datos.decode("utf-8-sig", errors="replace") if isinstance(datos, bytes) else datos.lstrip(BOM)
    try:
        crudo: Any = json.loads(texto)
    except json.JSONDecodeError:
        crudo = json5.loads(texto)
    if not isinstance(crudo, dict):
        raise ValueError("El archivo de idioma no es un objeto JSON")
    return {str(k): v for k, v in cast(dict[str, object], crudo).items() if isinstance(v, str)}


def escribir(textos: dict[str, str]) -> bytes:
    return (json.dumps(textos, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

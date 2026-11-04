"""Aviso de versión nueva: consulta la última release publicada en GitHub. No descarga ni instala nada.

Es una consulta corta a la API pública de GitHub (sin datos del usuario: solo el nombre y la versión de la
app en el User-Agent). Si falla por lo que sea, no pasa nada: se intenta en el próximo arranque.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

import httpx

from . import NOMBRE, REPOSITORIO, __version__
from .registro import LOGGER

API = REPOSITORIO.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"
TIEMPO_MAXIMO = 5.0


@dataclass(frozen=True, slots=True)
class Novedad:
    version: str
    enlace: str


def numeros(version: str) -> tuple[int, ...] | None:
    """«v2.1.0» → (2, 1, 0). None si no es una versión estable (p. ej. «2.1.0-rc1»)."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    return tuple(int(n) for n in m.groups()) if m else None


def buscar(actual: str = __version__, cliente: httpx.Client | None = None) -> Novedad | None:
    """La release más nueva que la versión actual, o None si no hay o no se pudo consultar."""
    propio = cliente is None
    http = cliente or httpx.Client(timeout=TIEMPO_MAXIMO)
    try:
        respuesta = http.get(
            API, headers={"Accept": "application/vnd.github+json", "User-Agent": f"{NOMBRE}/{__version__}"}
        )
        if not respuesta.is_success:
            LOGGER.info("Aviso de versión nueva: GitHub respondió %s", respuesta.status_code)
            return None
        datos: Any = respuesta.json()
    except (httpx.HTTPError, ValueError) as e:
        LOGGER.info("Aviso de versión nueva: no se pudo consultar (%s)", e)
        return None
    finally:
        if propio:
            http.close()
    if not isinstance(datos, dict):
        return None
    release = cast(dict[str, Any], datos)
    if release.get("draft") or release.get("prerelease"):
        return None
    etiqueta = str(release.get("tag_name", ""))
    nueva, vieja = numeros(etiqueta), numeros(actual)
    if nueva is None or vieja is None or nueva <= vieja:
        return None
    enlace = str(release.get("html_url") or f"{REPOSITORIO}/releases/latest")
    return Novedad(etiqueta.lstrip("v"), enlace)

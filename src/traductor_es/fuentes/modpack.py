"""Nombre y versión del modpack de una instancia, sacados de los metadatos que dejan el lanzador y el propio pack.

Orden: la configuración de BetterCompatibilityChecker (la escribe el autor del pack), los datos del lanzador
(Prism, CurseForge) y los manifiestos de Modrinth o CurseForge. Si nada lo dice, el nombre de la carpeta.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

#: Lo que BetterCompatibilityChecker escribe hasta que el autor del pack lo cambia.
_SIN_CAMBIAR = frozenset({"", "CHANGE_ME"})


@dataclass(frozen=True, slots=True)
class DatosModpack:
    nombre: str
    version: str = ""  #: vacía si no se sabe


def _json(ruta: Path) -> Any:
    try:
        return json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _texto(valor: object) -> str:
    """Un texto útil, o vacío. BCC 2 guarda {"value": "…", "comments": […]}; el formato viejo, el texto solo."""
    if isinstance(valor, dict):
        valor = cast(dict[str, Any], valor).get("value")
    if not isinstance(valor, str) or valor.strip() in _SIN_CAMBIAR:
        return ""
    return valor.strip()


def _buscar_claves(datos: object, nombre: str, version: str) -> tuple[str, str]:
    """Busca las dos claves en cualquier nivel (el .toml de BCC las pone dentro de una sección)."""
    if not isinstance(datos, dict):
        return "", ""
    d = cast(dict[str, Any], datos)
    hallado = (_texto(d.get(nombre)), _texto(d.get(version)))
    if hallado[0]:
        return hallado
    for valor in d.values():
        if isinstance(valor, dict) and (anidado := _buscar_claves(cast(object, valor), nombre, version))[0]:
            return anidado
    return hallado


def _bcc(juego: Path) -> Iterator[tuple[str, str]]:
    config = juego / "config"
    for nombre in ("bcc-common.json", "bcc.json"):
        yield _buscar_claves(_json(config / nombre), "modpackName", "modpackVersion")
    try:
        datos: Any = tomllib.loads((config / "bcc-common.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    yield _buscar_claves(datos, "modpackName", "modpackVersion")


def _prism(juego: Path) -> Iterator[tuple[str, str]]:
    try:
        texto = (juego.parent / "instance.cfg").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    valores = dict(re.findall(r"^(\w+)=(.*)$", texto, re.M))
    yield _texto(valores.get("ManagedPackName")), _texto(valores.get("ManagedPackVersionName"))
    yield _texto(valores.get("name")), ""


def _manifiestos(juego: Path) -> Iterator[tuple[str, str]]:
    instancia: Any = _json(juego / "minecraftinstance.json")  # CurseForge
    if isinstance(instancia, dict):
        datos = cast(dict[str, Any], instancia)
        yield _buscar_claves(datos.get("manifest"), "name", "version")
        yield _texto(datos.get("name")), ""
    for carpeta in (juego, juego.parent):
        yield _buscar_claves(_json(carpeta / "modrinth.index.json"), "name", "versionId")
        yield _buscar_claves(_json(carpeta / "manifest.json"), "name", "version")


def datos_del_modpack(juego: Path) -> DatosModpack:
    """El primer nombre que aparezca, con la primera versión que se sepa de cualquier fuente."""
    nombre = version = ""
    for n, v in (*_bcc(juego), *_prism(juego), *_manifiestos(juego)):
        if n and not nombre:
            nombre = n
        if v and not version:
            version = v
        if nombre and version:
            break
    if not nombre:
        nombre = juego.parent.name if juego.name in (".minecraft", "minecraft") else juego.name
    return DatosModpack(nombre, version)

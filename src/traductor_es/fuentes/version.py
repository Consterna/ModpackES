"""Versiones de Minecraft y formatos de pack (tabla oficial de la wiki, comprobada con los jars del juego)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Any, Final, cast


@total_ordering
@dataclass(frozen=True, slots=True, eq=False)
class Version:
    """Se compara por los números: «1.20» y «1.20.0» son la misma versión. `texto` conserva cómo se escribió."""

    texto: str
    partes: tuple[int, ...]

    def __eq__(self, otra: object) -> bool:
        return isinstance(otra, Version) and self.partes == otra.partes

    def __hash__(self) -> int:
        return hash(self.partes)

    @classmethod
    def de(cls, texto: str) -> Version:
        m = re.match(r"\s*(\d+(?:\.\d+){1,2})", texto)
        if not m:
            raise ValueError(f"Versión de Minecraft no reconocida: {texto!r}")
        partes = tuple(int(x) for x in m.group(1).split("."))
        return cls(m.group(1), partes + (0,) * (3 - len(partes)))

    def __lt__(self, otra: object) -> bool:
        if not isinstance(otra, Version):
            return NotImplemented
        return self.partes < otra.partes

    def __str__(self) -> str:
        return self.texto


# (desde la versión, formato) en orden descendente. Formatos con decimal se guardan como (mayor, menor).
_RECURSOS: Final[tuple[tuple[str, tuple[int, int]], ...]] = (
    ("26.3", (97, 1)), ("26.2", (88, 0)), ("26.1", (84, 0)), ("1.21.11", (75, 0)), ("1.21.9", (69, 0)),
    ("1.21.7", (64, 0)), ("1.21.6", (63, 0)), ("1.21.5", (55, 0)), ("1.21.4", (46, 0)), ("1.21.2", (42, 0)),
    ("1.21", (34, 0)), ("1.20.5", (32, 0)), ("1.20.3", (22, 0)), ("1.20.2", (18, 0)), ("1.20", (15, 0)),
    ("1.19.4", (13, 0)), ("1.19.3", (12, 0)), ("1.19", (9, 0)), ("1.18", (8, 0)), ("1.17", (7, 0)),
    ("1.16.2", (6, 0)), ("1.15", (5, 0)), ("1.13", (4, 0)), ("1.11", (3, 0)), ("1.9", (2, 0)), ("1.6", (1, 0)),
)  # fmt: skip
_DATOS: Final[tuple[tuple[str, tuple[int, int]], ...]] = (
    ("26.3", (121, 0)), ("26.2", (107, 1)), ("26.1", (101, 1)), ("1.21.11", (94, 1)), ("1.21.9", (88, 0)),
    ("1.21.7", (81, 0)), ("1.21.6", (80, 0)), ("1.21.5", (71, 0)), ("1.21.4", (61, 0)), ("1.21.2", (57, 0)),
    ("1.21", (48, 0)), ("1.20.5", (41, 0)), ("1.20.3", (26, 0)), ("1.20.2", (18, 0)), ("1.20", (15, 0)),
    ("1.19.4", (12, 0)), ("1.19", (10, 0)), ("1.18.2", (9, 0)), ("1.18", (8, 0)), ("1.17", (7, 0)),
    ("1.16.2", (6, 0)), ("1.15", (5, 0)), ("1.13", (4, 0)),
)  # fmt: skip

#: Desde estos formatos el pack.mcmeta usa min_format/max_format (Java 1.21.9+).
_NUEVO_RECURSOS, _NUEVO_DATOS = 65, 82


def _buscar(tabla: tuple[tuple[str, tuple[int, int]], ...], version: Version) -> tuple[int, int] | None:
    for desde, formato in tabla:
        if version >= Version.de(desde):
            return formato
    return None


def formato_recursos(version: Version) -> tuple[int, int]:
    return _buscar(_RECURSOS, version) or (1, 0)


def formato_datos(version: Version) -> tuple[int, int] | None:
    """None antes de 1.13 (no había data packs con este formato)."""
    return _buscar(_DATOS, version)


def formato_desde_jar(version_json: bytes, tipo: str) -> tuple[int, int] | None:
    """Lee `pack_version` del version.json que trae el jar del juego (la fuente oficial)."""
    try:
        datos: Any = json.loads(version_json)
    except (ValueError, UnicodeDecodeError):
        return None
    pv: object = cast(dict[str, Any], datos).get("pack_version") if isinstance(datos, dict) else None
    if isinstance(pv, int):  # 1.16-1.17: un solo número para ambos
        return (pv, 0)
    if isinstance(pv, dict):
        campos = cast(dict[str, object], pv)
        mayor = campos.get(tipo) if tipo in campos else campos.get(f"{tipo}_major")
        if isinstance(mayor, int):
            menor = campos.get(f"{tipo}_minor", 0)
            return (mayor, menor if isinstance(menor, int) else 0)
    return None


def mcmeta(formato: tuple[int, int], descripcion: str, tipo: str = "resource") -> dict[str, Any]:
    """pack.mcmeta para exactamente ese formato, con la sintaxis que corresponde a la versión."""
    mayor, menor = formato
    limite = _NUEVO_RECURSOS if tipo == "resource" else _NUEVO_DATOS
    pack: dict[str, Any] = {"description": descripcion}
    if mayor >= limite:
        pack["min_format"] = [mayor, menor] if menor else mayor
        pack["max_format"] = mayor  # un entero como máximo cubre todas las versiones menores
    else:
        pack["pack_format"] = mayor
    return {"pack": pack}


#: `supported_formats` existe desde 1.20.2 (formato 18) y se reemplazó por min_format/max_format en 1.21.9 (65).
_PRIMERO_CON_RANGO = 18


def rango_publicable(formato: int) -> tuple[int, int] | None:
    """Rango de `supported_formats` para un pack que solo trae textos, o None si a ese formato no le corresponde.

    Abarca los formatos de la misma línea de versiones (1.20.x, 1.21.x…): un pack de idiomas no depende del
    formato, y así el juego no lo marca como «hecho para otra versión» si el modpack sube de versión menor.
    """
    if not _PRIMERO_CON_RANGO <= formato < _NUEVO_RECURSOS:
        return None
    propias = [Version.de(v) for v, (f, _) in _RECURSOS if f <= formato]
    if not propias:
        return None
    linea = max(propias).partes[:2]  # la versión más nueva con ese formato o uno anterior
    formatos = [f for v, (f, _) in _RECURSOS if Version.de(v).partes[:2] == linea]
    desde = max(min(formatos), _PRIMERO_CON_RANGO)
    hasta = min(max(formatos), _NUEVO_RECURSOS - 1)
    return min(desde, formato), max(hasta, formato)

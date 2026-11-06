"""Texto de un componente de Minecraft, sea cual sea la versión: JSON o SNBT.

- Hasta 1.21.4 los componentes (`tellraw`, `title`, títulos de logros…) son JSON: `{"text":"Hola"}`.
- Desde 1.21.5 se guardan como NBT y en los comandos se escriben en SNBT: `{text:"Hola"}` (Minecraft Wiki,
  «Text component format»). Una cadena suelta entre comillas y las listas valen en los dos formatos.

Solo se traduce lo que ve el jugador: los campos `text`, las cadenas sueltas y el contenido de `extra`. Los
colores, las claves `translate`, los `score`/`selector`/`nbt` (los resuelve el servidor) y las acciones quedan igual.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..nucleo.mascara import es_traducible
from . import json_texto, snbt

#: Campos SNBT cuyo valor es texto visible: `text`, el contenido de `extra` y las cadenas sueltas (sin campo).
_CAMPOS_VISIBLES = frozenset({None, "text", "extra"})


def _cadenas_snbt(cuerpo: str) -> list[snbt.Cadena] | None:
    t = cuerpo.strip()
    if not t or t[0] not in "{[\"'":
        return None
    try:
        return [c for c in snbt.escanear(cuerpo) if c.campo in _CAMPOS_VISIBLES]
    except ValueError:
        return None


def unidades(cuerpo: str) -> list[str] | None:
    """Los textos visibles del componente, o None si no se reconoce el formato (no se toca)."""
    partes = json_texto.extraer(cuerpo, literal=True)
    if partes is not None:
        return [p for p in partes if es_traducible(p)]
    cadenas = _cadenas_snbt(cuerpo)
    return None if cadenas is None else [c.texto for c in cadenas if c.texto.strip() and es_traducible(c.texto)]


def reconstruir(cuerpo: str, traducciones: Mapping[str, str]) -> str:
    """El componente con los textos traducidos; lo demás (formato, colores, espacios del SNBT) queda igual."""
    if json_texto.cargar(cuerpo, literal=True) is not None:
        return json_texto.reconstruir(cuerpo, traducciones, literal=True)
    cadenas = _cadenas_snbt(cuerpo)
    if cadenas is None:
        return cuerpo
    return snbt.reemplazar(
        cuerpo, cadenas, {c.inicio: traducciones[c.texto] for c in cadenas if c.texto in traducciones}
    )

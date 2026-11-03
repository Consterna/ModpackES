"""Componentes de texto JSON de Minecraft (`["", {"text": "Hola", "color": "red"}]`).

Solo se traducen los campos `text` y las cadenas sueltas; colores, eventos y claves quedan iguales.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, cast


def _parece_componente(texto: str, literal: bool) -> bool:
    t = texto.strip()
    if t.startswith("["):
        return t.endswith("]")
    if literal and len(t) >= 2 and t.startswith('"') and t.endswith('"'):
        return True
    return t.startswith('{"') and t.endswith("}")


def cargar(texto: str, literal: bool = False) -> Any | None:
    """El componente ya decodificado, o None si el texto no es un componente JSON.

    `literal`: aceptar también una cadena JSON entre comillas (`"Hola"`), como guarda Heracles sus títulos.
    En FTB Quests no se usa: allí un texto entre comillas es una cita literal.
    """
    if not _parece_componente(texto, literal):
        return None
    try:
        datos: Any = json.loads(texto)
    except json.JSONDecodeError:
        return None
    if isinstance(datos, (list, dict)):
        return cast("list[Any] | dict[str, Any]", datos)
    return datos if literal and isinstance(datos, str) else None


def _recorrer(nodo: Any, hacer: Callable[[str], str]) -> Any:
    if isinstance(nodo, str):
        return hacer(nodo)
    if isinstance(nodo, list):
        return [_recorrer(x, hacer) for x in cast(list[Any], nodo)]
    if isinstance(nodo, dict):
        d = dict(cast(dict[str, Any], nodo))
        if isinstance(d.get("text"), str):
            d["text"] = hacer(d["text"])
        if "extra" in d:
            d["extra"] = _recorrer(d["extra"], hacer)
        evento = d.get("hoverEvent") or d.get("hover_event")
        if isinstance(evento, dict):
            evento = dict(cast(dict[str, Any], evento))
            for c in ("contents", "value", "text"):
                if c in evento and isinstance(evento[c], (str, list, dict)):
                    evento[c] = _recorrer(evento[c], hacer)
            d["hoverEvent" if "hoverEvent" in d else "hover_event"] = evento
        return d
    return nodo


def extraer(texto: str, literal: bool = False) -> list[str] | None:
    datos = cargar(texto, literal)
    if datos is None:
        return None
    vistos: list[str] = []

    def juntar(s: str) -> str:
        if s.strip():
            vistos.append(s)
        return s

    _recorrer(datos, juntar)
    return vistos


def reconstruir(texto: str, traducciones: Mapping[str, str], literal: bool = False) -> str:
    datos = cargar(texto, literal)
    if datos is None:
        return traducciones.get(texto, texto)
    nuevo = _recorrer(datos, lambda s: traducciones.get(s, s))
    return texto if nuevo == datos else json.dumps(nuevo, ensure_ascii=False)

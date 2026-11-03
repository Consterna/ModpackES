"""Variantes de español que Minecraft reconoce y cómo se le describen al traductor."""

from __future__ import annotations

from typing import Final

#: Códigos de idioma de Minecraft para el español (todos los que tiene el juego).
VARIANTES: Final[tuple[str, ...]] = ("es_ar", "es_cl", "es_ec", "es_es", "es_mx", "es_uy", "es_ve")

#: Dialecto en el que se escribe la traducción base, y cómo se le pide al motor.
DIALECTOS: Final[dict[str, str]] = {
    "es_mx": "español latinoamericano neutro (como la versión es_mx oficial de Minecraft)",
    "es_es": "español de España (como la versión es_es oficial de Minecraft)",
}

DIALECTO_POR_DEFECTO: Final = "es_mx"


def nombre_archivo_lang(codigo: str, version: tuple[int, ...] | None) -> str:
    """Nombre del archivo de idioma según la versión: 1.10 y anteriores usan es_ES, 1.11+ todo en minúsculas."""
    if version is not None and version < (1, 11):
        idioma, region = codigo.split("_")
        return f"{idioma}_{region.upper()}"
    return codigo

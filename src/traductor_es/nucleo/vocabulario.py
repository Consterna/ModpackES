"""Vocabulario base: palabras del juego que no salen sueltas en sus archivos de idioma, escritas como las escribe
el propio juego.

Regla: **lo que el español del juego ya traduce manda**. El vocabulario solo completa lo que el juego no tiene
como entrada propia («Netherite» sola: el juego dice «Hacha de netherita», «Lingote de netherita»…) y se agrega
después de los nombres del juego, así que nunca los pisa. Si el juego no es igual en todos los dialectos (es_mx
dice «ítem» y es_es «objeto»), cada dialecto sigue al suyo. El glosario del usuario manda sobre todo.
"""

from __future__ import annotations

from .glosario import Glosario

#: {inglés: español}. Solo palabras que el juego escribe así en es_mx y en es_es.
VOCABULARIO: dict[str, str] = {
    "Netherite": "Netherita",
}
#: Palabras que no son del juego y que se corrigen en los términos que traen los mods («inframundita»: el juego
#: dice «netherita»). No incluye nada que el juego use.
SUSTITUCIONES: dict[str, str] = {"inframundita": "netherita"}


def preparar_sustituciones(glosario: Glosario) -> None:
    """Antes de cargar nada: que los términos de los mods usen la palabra del juego."""
    glosario.sustituir(SUSTITUCIONES)


def agregar_vocabulario(glosario: Glosario) -> None:
    """Después de los nombres del juego: completa lo que el juego no trae suelto, sin pisar lo que sí trae."""
    glosario.agregar_pares({en: en for en in VOCABULARIO}, VOCABULARIO, fuente="vocabulario", oficial=True)

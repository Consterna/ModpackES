"""Vocabulario base: palabras del juego que no salen sueltas en sus archivos de idioma, escritas como las escribe
el propio juego.

Regla: **lo que el español del juego ya traduce manda**. El vocabulario solo completa lo que el juego no tiene
como entrada propia («Netherite» sola: el juego dice «Hacha de netherita», «Lingote de netherita»…) y se agrega
después de los nombres del juego, así que nunca los pisa. Si el juego no es igual en todos los dialectos (es_mx
dice «ítem» y es_es «objeto»), cada dialecto sigue al suyo. El glosario del usuario manda sobre todo.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from .glosario import Glosario

#: {inglés: español}. Solo palabras que el juego escribe así en es_mx y en es_es.
VOCABULARIO: dict[str, str] = {
    "Netherite": "Netherita",
}
#: Palabras que no son del juego y que se corrigen en los términos que traen los mods («inframundita»: el juego
#: dice «netherita»). No incluye nada que el juego use.
#: «crafteo» es un calco de «crafting»: el juego dice «fabricación» («recetas de fabricación»).
SUSTITUCIONES: dict[str, str] = {"inframundita": "netherita", "crafteo": "fabricación", "crafteos": "fabricaciones"}
#: Familias de objetos que no dan una palabra suelta (estandartes, plantillas, cerámica, huevos, discos).
_NO_SON_FAMILIA = ("banner_pattern", "smithing_template", "spawn_egg", "sherd", "music_disc", "_pattern")


def preparar_sustituciones(glosario: Glosario) -> None:
    """Antes de cargar nada: que los términos de los mods usen la palabra del juego."""
    glosario.sustituir(SUSTITUCIONES)


def nucleos_de_objetos(ingles: Mapping[str, str], traducido: Mapping[str, str]) -> dict[str, str]:
    """Las palabras sueltas que el juego usa en sus familias de objetos, en el dialecto de `traducido`.

    «Iron Chestplate» → «Pechera de hierro», «Diamond Chestplate» → «Pechera de diamante»…: «Chestplate» es «Pechera»
    en es_mx (y «Peto» en es_es). Solo nombres de objetos del juego, con al menos 4 de la familia y el 90 % de acuerdo,
    y nunca una palabra que ya es un nombre del juego.
    """
    familias: dict[str, Counter[str]] = {}
    for clave, en in ingles.items():
        es = traducido.get(clave)
        if not es or not clave.startswith("item.minecraft.") or clave.count(".") != 2:
            continue
        if any(x in clave for x in _NO_SON_FAMILIA):
            continue
        palabras_en, palabras_es = en.split(), es.split()
        if len(palabras_en) >= 2 and len(palabras_es) >= 2:
            familias.setdefault(palabras_en[-1], Counter())[palabras_es[0]] += 1
    nombres = set(ingles.values())
    salida: dict[str, str] = {}
    for nucleo, conteo in familias.items():
        palabra, veces = conteo.most_common(1)[0]
        if nucleo not in nombres and sum(conteo.values()) >= 4 and veces >= 0.9 * sum(conteo.values()):
            salida[nucleo] = palabra
    return salida


def agregar_nucleos(glosario: Glosario, ingles: Mapping[str, str], traducido: Mapping[str, str]) -> None:
    """Después de los nombres del juego: sus palabras sueltas («Chestplate» → «Pechera»), como oficiales."""
    nucleos = nucleos_de_objetos(ingles, traducido)
    glosario.agregar_pares({en: en for en in nucleos}, nucleos, fuente="minecraft", oficial=True)


def agregar_vocabulario(glosario: Glosario) -> None:
    """Después de los nombres del juego: completa lo que el juego no trae suelto, sin pisar lo que sí trae."""
    glosario.agregar_pares({en: en for en in VOCABULARIO}, VOCABULARIO, fuente="vocabulario", oficial=True)

"""Archivos de traducción de FTB Quests 26.x: `config/ftbquests/quests/lang/<idioma>/**/*.json5`.

Cada archivo es un objeto plano: `"<tipo>.<id>.<campo>": "texto"` o, para `quest_desc` y `chapter_subtitle`, una
lista de textos (`TranslationTable.fromJson` de FTB Quests). FTB Quests los lee con un parser JSON5, que también
acepta JSON normal: se escriben en JSON, sin comentarios, como un objeto plano con las mismas claves.
"""

from __future__ import annotations

import json
from typing import Any, cast

import json5

from .lang_legacy import BOM

Valor = str | list[str]


def leer(datos: bytes | str) -> dict[str, Valor]:
    """Las claves con texto o con una lista de textos. Lo demás se ignora, como en FTB Quests."""
    texto = datos.decode("utf-8-sig") if isinstance(datos, bytes) else datos.lstrip(BOM)
    try:
        crudo: Any = json5.loads(texto)
    except RecursionError as e:  # miles de niveles de anidamiento: se trata como un archivo roto
        raise ValueError("Archivo de traducción con demasiados niveles de anidamiento") from e
    if not isinstance(crudo, dict):
        raise ValueError("El archivo de traducción no es un objeto")
    salida: dict[str, Valor] = {}
    for clave, valor in cast(dict[object, object], crudo).items():
        if isinstance(valor, str):
            salida[str(clave)] = valor
        elif isinstance(valor, list):
            salida[str(clave)] = [v for v in cast(list[object], valor) if isinstance(v, str)]
    return salida


def escribir(textos: dict[str, Valor]) -> bytes:
    """JSON válido también como JSON5. U+2028 y U+2029 van escapados: en JSON5 cortan la línea fuera de una cadena."""
    texto = json.dumps(textos, ensure_ascii=False, indent=2)
    return (texto.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029") + "\n").encode("utf-8")

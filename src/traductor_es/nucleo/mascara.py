"""Protección de códigos: todo lo que el traductor no debe tocar se cambia por ⟦n⟧ antes de enviarlo.

Al volver, la traducción solo se acepta si trae exactamente los mismos marcadores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

#: Carácter de uso privado con el que los formatos marcan escapes que hay que conservar tal cual.
ESCAPE_CRUDO: Final = chr(0xE000)

_PATRONES: Final[tuple[str, ...]] = (
    ESCAPE_CRUDO + r".",  # escapes del formato de origen (\n en SNBT, etc.)
    r"\$\([^)]*\)",  # macros de Patchouli: $(l) $(item) $(l:ruta) $()
    r"\{[^{}\n]*\}",  # FTB Quests {image:..} {@pagebreak} {clave}, {0} de Java
    r"%(?:\d+\$)?[-#+0,(]*\d*(?:\.\d+)?[sdfxXcbeEgGoh%n]",  # printf: %s %1$s %d %.1f %%
    r"[§&][0-9a-fk-orA-FK-OR]",  # códigos de color y estilo
    r"<NEWLINE>",  # salto de los libros de Citadel
    r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>",  # etiquetas: GuideME <ItemLink .../>, <br>, <b>
    r"!\[[^\]]*\]\([^)\s]*\)",  # imagen markdown completa
    r"\]\([^)\s]+\)",  # destino de un enlace markdown: el texto sí se traduce
    r"https?://[^\s)\]}>\"']+",  # enlaces
    r"\\[nrt]",  # \n escrito como texto
    r"[\n\r\t]",  # saltos reales
    r"(?<![\w/:.])/[a-z][a-z0-9_]*",  # comandos como /home o /tpa
    r"\b[a-z0-9_.-]+:[a-z0-9_./-]*[a-z0-9_/]",  # ids de recursos: minecraft:stone, create:item/x
)
PROTEGER: Final = re.compile("|".join(f"(?:{p})" for p in _PATRONES))
TOKEN: Final = re.compile(r"⟦(\d+)⟧")
_LETRAS: Final = re.compile(r"[^\W\d_]{2}")


@dataclass(frozen=True, slots=True)
class Enmascarado:
    texto: str
    tokens: tuple[str, ...]


def enmascarar(texto: str) -> Enmascarado:
    tokens: list[str] = []

    def cambiar(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return f"⟦{len(tokens) - 1}⟧"

    return Enmascarado(PROTEGER.sub(cambiar, texto), tuple(tokens))


def desenmascarar(traducido: str, tokens: tuple[str, ...]) -> str | None:
    """Restaura los códigos. Devuelve None si el traductor perdió, repitió o inventó algún marcador."""
    vistos = sorted(int(n) for n in TOKEN.findall(traducido))
    if vistos != list(range(len(tokens))):
        return None
    restaurado = TOKEN.sub(lambda m: tokens[int(m.group(1))], traducido)
    return None if "⟦" in restaurado or "⟧" in restaurado else restaurado


def es_traducible(texto: str) -> bool:
    """Hay algo que traducir si, quitando los códigos, quedan al menos dos letras seguidas."""
    return bool(_LETRAS.search(TOKEN.sub(" ", enmascarar(texto).texto)))


def separar_bordes(texto: str) -> tuple[str, str, str]:
    """Separa espacios iniciales y finales, que se conservan tal cual y no se mandan a traducir."""
    nucleo = texto.strip()
    if not nucleo:
        return texto, "", ""
    inicio = len(texto) - len(texto.lstrip())
    return texto[:inicio], nucleo, texto[inicio + len(nucleo) :]

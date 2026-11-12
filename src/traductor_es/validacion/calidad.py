"""Reglas de calidad para cada traducción. Una traducción que no las pasa se reintenta y, si sigue mal,
el texto se queda en inglés (mejor inglés correcto que español roto).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

_PALABRA = re.compile(r"[^\W\d_]+")
#: Palabras muy comunes del inglés que casi nunca aparecen en un texto en español.
_INGLES = frozenset({
    "the", "and", "with", "your", "you", "this", "that", "from", "have", "will", "which", "when", "into", "are",
    "is", "of", "to", "for", "it", "can", "be", "an", "or", "not", "on", "by", "its", "they", "there", "their",
})  # fmt: skip
_ESPANOL = frozenset({
    "el", "la", "los", "las", "de", "del", "y", "que", "en", "un", "una", "con", "por", "para", "es", "se", "su",
    "al", "lo", "como", "más", "o", "tu", "puedes", "este", "esta",
})  # fmt: skip
_MARCADOR = re.compile(r"⟦\d+⟧")


def _palabras(texto: str) -> list[str]:
    return [p.lower() for p in _PALABRA.findall(_MARCADOR.sub(" ", texto))]


def validar(original: str, traduccion: str) -> str | None:
    """Motivo del rechazo, o None si la traducción es aceptable."""
    t = traduccion.strip()
    if not t:
        return "vacía"
    if "\n" in traduccion and "\n" not in original:
        return "salto de línea nuevo"
    largo = len(original.strip())
    if largo >= 12:
        proporcion = len(t) / largo
        if proporcion > 4 or proporcion < 0.2:
            return "largo raro"
    palabras = _palabras(t)
    ingles = sum(1 for p in palabras if p in _INGLES)
    espanol = sum(1 for p in palabras if p in _ESPANOL)
    if t == original.strip() and largo >= 30 and ingles >= 3:
        return "sin traducir"
    if len(palabras) >= 8 and ingles >= 4 and ingles >= 0.25 * len(palabras) and espanol < 2:
        return "inglés residual"
    return None


def sin_traducir(original: str, traduccion: str) -> bool:
    """El motor devolvió el texto igual y parece inglés: dos o más palabras y ninguna palabra común del español."""
    if traduccion.strip() != original.strip():
        return False
    palabras = _palabras(original)
    return len(palabras) >= 2 and not any(p in _ESPANOL for p in palabras)


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(c) != "Mn")


def _raiz(palabra: str) -> str:
    """El comienzo de una palabra que sobrevive a plurales y a terminaciones comunes («lingotes» → «lingo»)."""
    return palabra[: max(4, len(palabra) - 2)] if len(palabra) > 4 else palabra


def _sale_el_termino(esperado: str, traduccion: str) -> bool:
    """¿Aparece `esperado` en `traduccion`? Tolera tildes, mayúsculas y plurales o formas cercanas."""
    destino = _sin_tildes(traduccion)
    if _sin_tildes(esperado) in destino:
        return True
    palabras_destino = _PALABRA.findall(destino)
    significativas = [p for p in _PALABRA.findall(_sin_tildes(esperado)) if len(p) >= 4]
    if not significativas:
        return False
    return all(any(d.startswith(_raiz(p)) for d in palabras_destino) for p in significativas)


def terminos_faltantes(original: str, traduccion: str, glosario: Mapping[str, str]) -> dict[str, str]:
    """{inglés: traducción esperada} de los términos del glosario que salen en el original y no en la traducción.

    Solo se exige lo que cambia al traducir (un término igual en los dos idiomas no se comprueba) y se tolera
    que la palabra venga en plural o con otra terminación: es una red contra olvidos, no un corrector de estilo.
    """
    minusculas = original.casefold()
    faltan: dict[str, str] = {}
    for ingles, esperado in glosario.items():
        if not esperado.strip() or _sin_tildes(ingles) == _sin_tildes(esperado):
            continue
        if not re.search(r"(?<![^\W_])" + re.escape(ingles.casefold()) + r"(?![^\W_])", minusculas):
            continue
        if not _sale_el_termino(esperado, traduccion):
            faltan[ingles] = esperado
    return faltan


@dataclass(slots=True)
class Revision:
    """Avisos sobre el conjunto (no rechazan nada): términos del glosario que no se respetaron."""

    inconsistentes: dict[str, int] = field(default_factory=dict[str, int])

    def __str__(self) -> str:
        if not self.inconsistentes:
            return "Glosario respetado en todas las traducciones."
        peores = sorted(self.inconsistentes.items(), key=lambda par: -par[1])[:5]
        return "Términos del glosario no respetados: " + ", ".join(f"{t} ({n})" for t, n in peores)


def revisar_glosario(traducciones: Mapping[str, str], glosario: Mapping[str, str], terminos: Iterable[str]) -> Revision:
    """Cuenta las veces que un término del glosario aparece en el original pero su traducción no sale."""
    revision = Revision()
    for termino in terminos:
        oficial = glosario.get(termino)
        if not oficial:
            continue
        patron = re.compile(r"(?<![^\W_])" + re.escape(termino.lower()) + r"(?![^\W_])")
        for original, traducida in traducciones.items():
            if patron.search(original.lower()) and oficial.lower() not in traducida.lower():
                revision.inconsistentes[termino] = revision.inconsistentes.get(termino, 0) + 1
    return revision

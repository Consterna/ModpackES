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


def sale_el_termino(esperado: str, traduccion: str) -> bool:
    """¿Aparece `esperado` en `traduccion`? Tolera tildes, mayúsculas y plurales o formas cercanas."""
    destino = _sin_tildes(traduccion)
    if _sin_tildes(esperado) in destino:
        return True
    palabras_destino = _PALABRA.findall(destino)
    significativas = [p for p in _PALABRA.findall(_sin_tildes(esperado)) if len(p) >= 4]
    if not significativas:
        return False
    return all(any(d.startswith(_raiz(p)) for d in palabras_destino) for p in significativas)


def _patron_palabra(termino: str, flags: int = 0) -> re.Pattern[str]:
    """`termino` como palabra (o frase) completa: no vale dentro de otra palabra."""
    return re.compile(r"(?<![^\W_])" + re.escape(termino) + r"(?![^\W_])", flags)


def _inicio_de_frase(texto: str, posicion: int) -> bool:
    """¿La posición abre el texto o una frase (después de «.», «!», «?», «:» o un salto de línea)?"""
    antes = texto[:posicion].rstrip(" \t\"'«“¿¡([")
    return not antes or antes[-1] in ".!?:\n"


def _en_estilo_titulo(original: str, termino: str) -> bool:
    """¿El original pone mayúscula a todo («Speed Upgrade Module (Tier VIII)», «Put the Iron Ingot in the Chest»)?
    Entonces la mayúscula de un término no dice que sea un nombre propio. Es una frase normal si tiene al menos
    una palabra de 4 letras o más en minúscula fuera del término («Defeat the Death Knights and craft…»)."""
    propias = {p.casefold() for p in _PALABRA.findall(termino)}
    return not any(len(p) >= 4 and p.islower() and p.casefold() not in propias for p in _PALABRA.findall(original))


def es_nombre_propio_en(termino: str, original: str) -> bool:
    """¿El original escribe `termino` como nombre propio (con mayúscula) en medio de una frase en minúscula?

    «Use the Quantum Ring to craft it» sí; «Quantum rings are…» al empezar la frase no dice nada, salvo que todas
    sus palabras largas vayan en mayúscula («Quantum Ring is strong»). En un texto que pone mayúscula a todo
    («Speed Upgrade Module») tampoco: así se escriben los nombres de objetos en inglés.
    """
    if _en_estilo_titulo(original, termino):
        return False
    for m in _patron_palabra(termino, re.IGNORECASE).finditer(original):
        palabras = [p for p in _PALABRA.findall(m.group(0)) if len(p) >= 3]
        if not palabras or not all(p[0].isupper() for p in palabras):
            continue
        if not _inicio_de_frase(original, m.start()) or len(palabras) >= 2:
            return True
    return False


def terminos_faltantes(original: str, traduccion: str, glosario: Mapping[str, str]) -> dict[str, str]:
    """{inglés: traducción esperada} de los términos del glosario que salen en el original y no en la traducción.

    Se tolera que la palabra venga en plural o con otra terminación: es una red contra olvidos, no un corrector
    de estilo. Un término que queda igual en los dos idiomas («Creeper», un jefe, un mod) solo se exige cuando
    el original lo escribe como nombre propio: así no se obliga a dejar en inglés una palabra común.
    """
    minusculas = original.casefold()
    faltan: dict[str, str] = {}
    for ingles, esperado in glosario.items():
        if not esperado.strip():
            continue
        if not _patron_palabra(ingles.casefold()).search(minusculas):
            continue
        if _sin_tildes(ingles) == _sin_tildes(esperado) and not es_nombre_propio_en(ingles, original):
            continue
        if not sale_el_termino(esperado, traduccion):
            faltan[ingles] = esperado
    return faltan


def _escrito_como_nombre_propio(termino: str) -> bool:
    """Una palabra con mayúscula («Fluix») o varias con al menos dos en mayúscula («Anillo Cuántico»)."""
    palabras = _PALABRA.findall(termino)
    if not palabras or not palabras[0][0].isupper():
        return False
    return len(palabras) == 1 or sum(1 for p in palabras if p[0].isupper()) >= 2


def ajustar_mayusculas(original: str, traduccion: str, glosario: Mapping[str, str]) -> str:
    """Escribe los términos del glosario con sus mayúsculas cuando el original los trata como nombre propio.

    «Use the Quantum Ring» con «Quantum Ring» = «Anillo Cuántico» en el glosario: si el modelo escribió «el anillo
    cuántico», queda «el Anillo Cuántico». No toca lo que está todo en mayúsculas (un título que grita) ni los
    términos que el original escribe en minúscula. Un término de varias palabras en el estilo del juego
    («Lingote de hierro») tampoco: en medio de una frase en español va en minúscula; solo se respetan los que el
    glosario escribe como nombre propio («Caballeros de la Muerte», «Fluix»).
    """
    for ingles, esperado in sorted(glosario.items(), key=lambda par: -len(par[1])):
        if not _escrito_como_nombre_propio(esperado) or not es_nombre_propio_en(ingles, original):
            continue

        def corregir(m: re.Match[str], esperado: str = esperado) -> str:
            hallado = m.group(0)
            return hallado if hallado.isupper() and len(hallado) > 1 else esperado

        traduccion = _patron_palabra(esperado, re.IGNORECASE).sub(corregir, traduccion)
    return traduccion


def _sigue_en_ingles(original: str, traduccion: str, terminos: Iterable[str]) -> bool:
    """¿Lo que rodea a los términos sigue en inglés? Más de la mitad de sus palabras de 3 letras o más son las del
    original («Iron Gear» → «Iron Gear»). Entonces cambiar solo el término daría una mezcla («Iron Engranaje»)."""
    propias = {p for t in terminos for p in _palabras(t)}
    del_original = set(_palabras(original))
    resto = [p for p in _palabras(traduccion) if len(p) >= 3 and p not in propias]
    return bool(resto) and sum(1 for p in resto if p in del_original) > len(resto) / 2


def reemplazar_en_ingles(traduccion: str, faltan: Mapping[str, str], original: str = "") -> tuple[str, dict[str, str]]:
    """Cambia por su traducción los términos que el modelo dejó tal cual en inglés.

    Devuelve la traducción y los términos que siguen faltando (los que no aparecían en inglés: esos no se pueden
    arreglar sin entender la frase). Si con `original` se ve que el resto del texto también quedó en inglés, no se
    cambia nada: una traducción a medias es peor que avisar.
    """
    if original and _sigue_en_ingles(original, traduccion, faltan):
        return traduccion, dict(faltan)
    siguen: dict[str, str] = {}
    for ingles, esperado in faltan.items():
        patron = _patron_palabra(ingles, re.IGNORECASE)
        if patron.search(traduccion):
            traduccion = patron.sub(lambda _m, e=esperado: e, traduccion)
        else:
            siguen[ingles] = esperado
    return traduccion, siguen


#: Largo mínimo de una palabra para comparar raíces al buscar repeticiones, y largo de la raíz.
_RAIZ_REPETIDA = 5
#: Solo se buscan repeticiones en textos cortos (nombres, botones): en una frase larga repetir es normal.
_MAX_PALABRAS_REPETICION = 6


def palabra_repetida(original: str, traduccion: str) -> str | None:
    """Palabra que la traducción repite (con la misma raíz) y el original no: «Mejora de Salud mejorada».

    Devuelve la palabra repetida, o None. Solo mira textos cortos y solo si el original no repite nada.
    """
    destino = _palabras(traduccion)
    if len(destino) > _MAX_PALABRAS_REPETICION:
        return None

    def repetidas(palabras: list[str]) -> dict[str, str]:
        vistas: dict[str, str] = {}
        dobles: dict[str, str] = {}
        for p in palabras:
            if len(p) < _RAIZ_REPETIDA:
                continue
            raiz = _sin_tildes(p)[:_RAIZ_REPETIDA]
            if raiz in vistas:
                dobles[raiz] = vistas[raiz]
            vistas.setdefault(raiz, p)
        return dobles

    if repetidas(_palabras(original)):
        return None
    dobles = repetidas(destino)
    return next(iter(dobles.values())) if dobles else None


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
    """Cuenta las veces que un término del glosario aparece en el original pero su traducción no sale.

    Usa la misma regla que el rechazo de cada traducción (`terminos_faltantes`): tolera tildes, mayúsculas y plurales.
    """
    revision = Revision()
    elegidos = {t: glosario[t] for t in terminos if glosario.get(t)}
    for original, traducida in traducciones.items():
        for termino in terminos_faltantes(original, traducida, elegidos):
            revision.inconsistentes[termino] = revision.inconsistentes.get(termino, 0) + 1
    return revision

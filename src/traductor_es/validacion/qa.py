"""Control de calidad determinista: lo que una herramienta de QA de localización revisaría en cada traducción.

Cada control arregla solo lo que es seguro arreglar sin entender la frase (espacios, ¿¡, puntuación final que
se perdió, comillas del dialecto, meses con mayúscula) y marca como duda lo demás (números distintos, paréntesis
sin pareja, usted en vez de tú, palabras en inglés, omisiones). Nada de esto llama al modelo.

Los arreglos se hacen sobre el texto con los códigos protegidos (⟦n⟧), así que nunca tocan un `§a`, un `%s`, un
`$(l)` ni una etiqueta. Las ideas vienen de los controles de herramientas como Weblate, Translate Toolkit
(pofilter), Xbench y memoQ, y de las convenciones del español del propio Minecraft (tú, ¿¡, `...`); el código es
propio.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Final, Literal

from ..nucleo.mascara import TOKEN, desenmascarar, enmascarar

Gravedad = Literal["bloquea", "duda", "info"]


@dataclass(frozen=True, slots=True)
class Hallazgo:
    codigo: str
    gravedad: Gravedad
    detalle: str = ""
    arreglado: bool = False


_MARCADOR: Final = r"⟦\d+⟧"
_PALABRA: Final = re.compile(r"[^\W\d_]+")
_ANCHO_CERO: Final = re.compile("[\u200b‌‍⁠﻿]")
_PALABRA_DOBLE: Final = re.compile(r"\b([^\W\d_]{2,})(\s+)\1\b", re.IGNORECASE)
_ESPACIO_ANTES: Final = re.compile(r"(?<=\S) +(?=[,.;:!?)\]»])")
_ESPACIO_DESPUES: Final = re.compile(r"([¿¡(\[«]) +")
#: Inicio de la frase: se salta lo que va antes de la primera letra (códigos, guiones, comillas, paréntesis)
_INICIO: Final = re.compile(rf"^(?:{_MARCADOR}|[\s\"'«“(\[\-–—*•])*")
_TERMINOS_DE_FRASE: Final = re.compile(r"[.!?…](?=\s|$|⟦)")
_MESES_Y_DIAS: Final = frozenset({
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "setiembre",
    "octubre", "noviembre", "diciembre", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
})  # fmt: skip
#: Formas de usted que el español del juego no usa (tutea en es_mx y en es_es)
_USTED: Final = re.compile(
    r"\b(usted|haga|coloque|utilice|asegúrese|presione|pulse|seleccione|elija|intente|introduzca|"
    r"mantenga|compruebe|verifique|tenga en cuenta)\b",
    re.IGNORECASE,
)
#: Palabras del inglés que no existen en español: si sobreviven, quedó inglés a medio traducir
_INGLES: Final = frozenset({
    "the", "and", "with", "your", "you", "this", "that", "from", "have", "will", "which", "when", "into", "are",
    "is", "of", "to", "for", "it", "can", "be", "an", "or", "not", "on", "by", "its", "they", "there", "their",
    "click", "right", "left", "using", "use", "while", "item", "items", "block", "blocks",
})  # fmt: skip
_NUMERO: Final = re.compile(r"\d+(?:[.,]\d+)*")
_PAREJAS: Final = (("(", ")"), ("[", "]"), ("«", "»"), ("“", "”"))
#: Largo máximo razonable de un texto de interfaz en español frente al inglés (expansión de 20–30 % más margen)
_FACTOR_LARGO, _MARGEN_LARGO = 1.6, 10


def _visible(texto: str) -> str:
    return TOKEN.sub(" ", texto)


def _una_frase(texto: str) -> bool:
    """¿Es una sola frase? Ningún punto, ¡, ? o salto antes del final."""
    cuerpo = _visible(texto).rstrip()[:-1]
    return not _TERMINOS_DE_FRASE.search(cuerpo) and "\n" not in cuerpo


def _abrir(texto: str, signo: str) -> str:
    inicio = _INICIO.match(texto)
    corte = inicio.end() if inicio else 0
    return texto[:corte] + signo + texto[corte:]


#: Del uno al doce se escriben a menudo con letras («say that 3 times» → «dilo tres veces»)
_CON_LETRAS: Final = {
    "uno": "1", "una": "1", "un": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6",
    "siete": "7", "ocho": "8", "nueve": "9", "diez": "10", "once": "11", "doce": "12",
}  # fmt: skip


def _numeros(texto: str) -> Counter[str]:
    """Las cifras del texto sin separadores: «1,000», «1.000» y «1000» cuentan igual; «1.5» y «1,5» también."""
    return Counter(re.sub(r"[.,]", "", n) for n in _NUMERO.findall(_visible(texto)))


def _faltan_numeros(fuente: str, texto: str) -> bool:
    """¿Hay cifras del original que no están en la traducción, ni con letras, o cifras nuevas?"""
    original, traducido = _numeros(fuente), _numeros(texto)
    if original == traducido:
        return False
    escritas = Counter(_CON_LETRAS[p.lower()] for p in _PALABRA.findall(_visible(texto)) if p.lower() in _CON_LETRAS)
    faltan = original - traducido
    return bool(faltan - escritas) or bool(traducido - original)


#: Una frase nueva: punto, ¡, ? o … seguido de espacio y de una mayúscula (no cuentan «e.g.» ni «etc.» en medio)
_LIMITE_DE_FRASE: Final = re.compile(r"(?<![\s.][a-z])(?<!\betc)[.!?…]\s+[¿¡\"«(]*[A-ZÁÉÍÓÚÑ]")


def _final(texto: str) -> str:
    """El último carácter visible (sin espacios ni códigos al final)."""
    visible = re.sub(rf"(?:{_MARCADOR}|\s)+$", "", texto)
    return visible[-1:] if visible else ""


class _Revision:
    """El texto (con los códigos protegidos) y lo que se va encontrando."""

    def __init__(self, fuente: str, texto: str) -> None:
        self.fuente = fuente
        self.texto = texto
        self.hallazgos: list[Hallazgo] = []

    def arreglo(self, codigo: str, nuevo: str) -> None:
        if nuevo != self.texto:
            self.texto = nuevo
            self.hallazgos.append(Hallazgo(codigo, "info", arreglado=True))

    def marca(self, codigo: str, gravedad: Gravedad, detalle: str) -> None:
        self.hallazgos.append(Hallazgo(codigo, gravedad, detalle))


def _espacios(r: _Revision) -> None:
    """Espacios dobles o antes de la puntuación, caracteres invisibles y palabras repetidas que el original no tiene."""
    if not _ANCHO_CERO.search(r.fuente):
        r.arreglo("ancho_cero", _ANCHO_CERO.sub("", r.texto))
    if "  " not in r.fuente:
        r.arreglo("espacios", re.sub(r"(?<=\S) {2,}(?=\S)", " ", r.texto))
    if not _ESPACIO_ANTES.search(r.fuente):
        r.arreglo("espacios", _ESPACIO_DESPUES.sub(r"\1", _ESPACIO_ANTES.sub("", r.texto)))
    if not _PALABRA_DOBLE.search(r.fuente):
        r.arreglo("palabra_doble", _PALABRA_DOBLE.sub(r"\1", r.texto))


def _palabras_inglesas(texto: str) -> list[str]:
    """Palabras que solo existen en inglés, si son bastantes para decir que el texto quedó (en parte) en inglés."""
    palabras = [p.lower() for p in _PALABRA.findall(_visible(texto))]
    inglesas = [p for p in palabras if p in _INGLES]
    return inglesas if inglesas and (len(inglesas) >= 2 or len(palabras) <= 4) else []


#: Palabras que en un texto en español solo aparecen si quedó inglés: con una basta para no decorarlo con ¿¡
_SOLO_INGLES: Final = frozenset({
    "the", "and", "with", "your", "you", "this", "that", "from", "have", "will", "which", "when", "into", "are",
    "is", "isn", "don", "doesn", "can", "won", "it", "its", "of", "to", "for", "not",
})  # fmt: skip


def _parece_ingles(texto: str, fuente: str) -> bool:
    """¿Quedó en inglés? Lleva una palabra que solo existe en inglés, o la mitad de sus palabras son del original."""
    palabras = [p.lower() for p in _PALABRA.findall(_visible(texto)) if len(p) >= 3]
    if any(p.lower() in _SOLO_INGLES for p in _PALABRA.findall(_visible(texto))):
        return True
    del_original = {p.lower() for p in _PALABRA.findall(_visible(fuente))}
    return bool(palabras) and sum(p in del_original for p in palabras) >= len(palabras) / 2


def _pares_de_comillas(texto: str) -> int:
    return texto.count('"') // 2 + texto.count("«") + texto.count("“")


def _signos(r: _Revision) -> None:
    """¿ y ¡ de apertura, y la puntuación final que el original tiene y la traducción perdió."""
    for cierre, apertura in (("?", "¿"), ("!", "¡")):
        if _parece_ingles(r.texto, r.fuente):  # un texto que quedó en inglés no se decora: se marca como duda
            break
        if _final(r.texto) == cierre and apertura not in r.texto:
            if _una_frase(r.texto):
                r.arreglo("signo_apertura", _abrir(r.texto, apertura))
            else:
                r.marca("signo_apertura", "duda", f"falta «{apertura}»")
    fin_fuente, fin, texto = _final(r.fuente), _final(r.texto), r.texto.rstrip()
    if r.fuente.rstrip().endswith("...") and not texto.endswith("..."):
        if texto.endswith("…"):
            r.arreglo("puntuacion_final", texto[:-1] + "...")
        elif fin and fin not in ".!?:" and not texto.endswith("⟧"):
            r.arreglo("puntuacion_final", texto + "...")
    elif fin_fuente == ":" and fin != ":" and not texto.endswith("⟧"):
        r.arreglo("puntuacion_final", (texto[:-1] if fin == "." else texto) + ":")
    elif (fin_fuente == "." and fin not in ".!?…:") or (fin_fuente not in ".!?…:" and fin == "."):
        r.marca("puntuacion_final", "info", "el punto final no coincide con el original")


def _al_inicio(texto: str, posicion: int) -> bool:
    antes = re.sub(rf"(?:{_MARCADOR}|\s)+$", "", texto[:posicion])
    return not antes or antes[-1] in ".!?¿¡:\n"


def _comillas_y_fechas(r: _Revision, dialecto: str) -> None:
    """Comillas del dialecto, solo si el original las usa (es_es «», es_mx ""), y meses y días en minúscula."""
    # Solo si el original usa comillas y la traducción tiene los mismos pares (no se tocan comillas que el
    # original no tenía, como las de un nombre que el modelo destacó)
    if ('"' in r.fuente or "“" in r.fuente) and _pares_de_comillas(r.texto) == _pares_de_comillas(r.fuente):
        if dialecto == "es_es":
            r.arreglo("comillas", re.sub(r'"([^"\n]+)"', r"«\1»", r.texto))
        else:
            r.arreglo("comillas", re.sub(r"[«“]([^»”\n]+)[»”]", r'"\1"', r.texto))
    texto = r.texto
    r.arreglo(
        "mes_dia",
        _PALABRA.sub(
            lambda m: (
                m.group(0).lower()
                if m.group(0).lower() in _MESES_Y_DIAS and not _al_inicio(texto, m.start())
                else m.group(0)
            ),
            texto,
        ),
    )


def _dudas(r: _Revision) -> None:
    """Lo que no se puede arreglar sin entender la frase."""
    fuente, texto = r.fuente, r.texto
    if _faltan_numeros(fuente, texto):
        r.marca("numeros", "duda", "las cifras no coinciden con el original")
    for abre, cierra in _PAREJAS:
        if texto.count(abre) != texto.count(cierra) and fuente.count(abre) == fuente.count(cierra):
            r.marca("pareja", "duda", f"«{abre}» sin pareja")
    if texto.count('"') % 2 and not fuente.count('"') % 2:
        r.marca("pareja", "duda", "comillas sin pareja")
    if _USTED.search(_visible(texto)) and not _USTED.search(_visible(fuente)):
        r.marca("usted", "duda", "trata de usted; el juego tutea")
    if inglesas := _palabras_inglesas(texto):
        r.marca("ingles", "duda", "quedan palabras en inglés: " + ", ".join(sorted(set(inglesas))))
    largo_fuente, largo = len(_visible(fuente).strip()), len(_visible(texto).strip())
    frases_fuente = len(_LIMITE_DE_FRASE.findall(_visible(fuente)))
    # Unir dos frases con «:» o «;» es legítimo: solo cuenta si faltan dos o más, o la mitad del largo
    if (largo_fuente >= 40 and largo < 0.5 * largo_fuente) or (
        frases_fuente - len(_LIMITE_DE_FRASE.findall(_visible(texto))) >= 2
    ):
        r.marca("omision", "duda", "parece que falta parte del original")


def _informacion(r: _Revision, ambito: str, rol: str) -> None:
    """Se cuenta, pero no se arregla ni se marca como duda."""
    largo_fuente, largo = len(_visible(r.fuente).strip()), len(_visible(r.texto).strip())
    if ambito == "ui" and largo > _FACTOR_LARGO * largo_fuente + _MARGEN_LARGO:
        r.marca("largo", "info", "mucho más largo que el original")
    if rol == "nombre":
        # El juego escribe los nombres con solo la primera en mayúscula, pero el usuario quiere conservar las
        # mayúsculas de los términos del universo del pack («Anillo Cuántico»): solo se informa.
        capitalizadas = [p for p in _PALABRA.findall(_visible(r.texto))[1:] if p[:1].isupper() and not p.isupper()]
        del_original = set(_PALABRA.findall(_visible(r.fuente)))
        if any(p not in del_original for p in capitalizadas):
            r.marca("mayusculas_titulo", "info", "mayúsculas como en inglés («Espada de Diamante»)")


def revisar(
    original: str, traduccion: str, *, ambito: str = "ui", dialecto: str = "es_mx", rol: str = ""
) -> tuple[str, list[Hallazgo]]:
    """La traducción con los arreglos seguros aplicados y la lista de lo que se encontró."""
    m = enmascarar(traduccion)
    r = _Revision(enmascarar(original).texto, m.texto)
    _espacios(r)
    _signos(r)
    _comillas_y_fechas(r, dialecto)
    _dudas(r)
    _informacion(r, ambito, rol)
    restaurado = desenmascarar(r.texto, m.tokens)
    return (restaurado if restaurado is not None else traduccion), r.hallazgos


def dudas(hallazgos: list[Hallazgo]) -> list[str]:
    """Los códigos de las dudas, sin repetir y en orden."""
    return list(dict.fromkeys(h.codigo for h in hallazgos if h.gravedad == "duda"))


def arreglos(hallazgos: list[Hallazgo]) -> list[str]:
    return [h.codigo for h in hallazgos if h.arreglado]

"""Markdown de guías (GuideME y Lavender): qué partes son texto y cómo reescribirlas sin tocar el resto.

Se traducen párrafos, títulos, elementos de lista, citas y el «title» de la cabecera. Se dejan igual los
bloques de código, las líneas que son solo etiquetas (<GameScene>, <ItemImage .../>) y las tablas. Los
destinos de los enlaces y las etiquetas dentro del texto los protege la máscara del núcleo.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_TITULO_YAML = re.compile(r"^(\s*title\s*:\s*)(.*?)(\s*)$")
_TITULO_JSON = re.compile(r'^(\s*"title"\s*:\s*")((?:[^"\\]|\\.)*)("\s*,?\s*)$')
#: El «/» de las etiquetas que se cierran solas ya entra en [^<>]*: un «/?» aparte hacía que una línea mal formada
#: tardara un tiempo exponencial en descartarse (ReDoS).
_SOLO_ETIQUETA = re.compile(r"^\s*(?:</?[A-Za-z][^<>]*>\s*)+$")
_COMENTARIO = re.compile(r"^\s*<!--.*-->\s*$")
#: Línea que abre un comentario sin cerrarlo: lo que sigue hasta el «-->» tampoco es texto.
_ABRE_COMENTARIO = re.compile(r"^\s*<!--(?!.*-->)")
_ENCABEZADO = re.compile(r"^(\s*#{1,6}\s+)(.+?)(\s*)$")
_LISTA = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)(.+?)(\s*)$")
_CITA = re.compile(r"^(\s*>\s?)(.+?)(\s*)$")
_VALLA = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True, slots=True)
class Segmento:
    inicio: int  #: primera línea
    fin: int  #: línea siguiente a la última
    prefijo: str  #: lo que va delante del texto en cada línea (sangría, «# », «- »)
    texto: str  #: texto a traducir (las líneas de un párrafo se unen con \n)
    sufijo: str = ""
    json: bool = False  #: el texto va escapado como cadena JSON (cabecera de Lavender)


def _comillas(valor: str) -> tuple[str, str, str]:
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[0], valor[1:-1], valor[0]
    return "", valor, ""


def _cabecera(lineas: list[str]) -> tuple[int, list[Segmento]]:
    """Cabecera YAML de GuideME (--- … ---) o JSON de Lavender (```json … ```): su «title» y dónde termina."""
    n = len(lineas)
    segs: list[Segmento] = []
    primera = lineas[0].strip() if n else ""
    if primera == "---":
        j = 1
        while j < n and lineas[j].strip() != "---":
            if m := _TITULO_YAML.match(lineas[j]):
                abre, valor, cierra = _comillas(m.group(2))
                if valor and not valor.startswith(("[", "{", "|", ">")):
                    segs.append(Segmento(j, j + 1, m.group(1) + abre, valor, cierra + m.group(3)))
            j += 1
        return j + 1, segs
    if primera.startswith("```json"):
        j = 1
        while j < n and not lineas[j].strip().startswith("```"):
            if m := _TITULO_JSON.match(lineas[j]):
                segs.append(Segmento(j, j + 1, m.group(1), json.loads(f'"{m.group(2)}"'), m.group(3), json=True))
            j += 1
        return j + 1, segs
    return 0, segs


def _separa_parrafos(linea: str) -> bool:
    """Líneas que no son texto y cortan el párrafo: vacías, solo etiquetas, comentarios y tablas."""
    return (
        not linea.strip()
        or bool(_SOLO_ETIQUETA.match(linea))
        or bool(_COMENTARIO.match(linea))
        or linea.lstrip().startswith("|")
    )


def segmentar(md: str) -> tuple[list[str], list[Segmento]]:
    lineas = md.split("\n")
    n = len(lineas)

    def limpia(k: int) -> str:
        return lineas[k].rstrip("\r")

    i, segs = _cabecera([limpia(k) for k in range(n)])
    parrafo: list[int] = []

    def cerrar_parrafo() -> None:
        if parrafo:
            sangria = limpia(parrafo[0])[: len(limpia(parrafo[0])) - len(limpia(parrafo[0]).lstrip())]
            texto = "\n".join(limpia(k).strip() for k in parrafo)
            segs.append(Segmento(parrafo[0], parrafo[-1] + 1, sangria, texto))
            parrafo.clear()

    en_codigo = en_comentario = False
    while i < n:
        linea = limpia(i)
        if en_comentario:
            en_comentario = "-->" not in linea
        elif _VALLA.match(linea):
            cerrar_parrafo()
            en_codigo = not en_codigo
        elif en_codigo:
            pass
        elif _ABRE_COMENTARIO.match(linea):
            cerrar_parrafo()
            en_comentario = True
        elif _separa_parrafos(linea):
            cerrar_parrafo()
        elif m := (_ENCABEZADO.match(linea) or _LISTA.match(linea) or _CITA.match(linea)):
            cerrar_parrafo()
            segs.append(Segmento(i, i + 1, m.group(1), m.group(2), m.group(3)))
        else:
            if parrafo and (limpia(parrafo[0]).startswith(" ") != linea.startswith(" ")):
                cerrar_parrafo()
            parrafo.append(i)
        i += 1
    cerrar_parrafo()
    return lineas, segs


def reconstruir(lineas: list[str], segs: list[Segmento], traducciones: dict[str, str]) -> str:
    """Reemplaza cada segmento traducido; lo que no tiene traducción queda igual."""
    salida = list(lineas)
    for s in sorted(segs, key=lambda s: s.inicio, reverse=True):
        nuevo = traducciones.get(s.texto)
        if nuevo is None or nuevo == s.texto:
            continue
        cr = "\r" if lineas[s.inicio].endswith("\r") else ""
        if s.json:
            nuevo = json.dumps(nuevo, ensure_ascii=False)[1:-1]
        partes = nuevo.split("\n")
        if len(partes) == s.fin - s.inicio:
            reemplazo = [s.prefijo + p + (s.sufijo if k == len(partes) - 1 else "") + cr for k, p in enumerate(partes)]
        else:  # los \n van protegidos, así que no debería pasar; si pasa, el párrafo queda en una línea
            reemplazo = [s.prefijo + " ".join(p.strip() for p in partes) + s.sufijo + cr]
        salida[s.inicio : s.fin] = reemplazo
    return "\n".join(salida)

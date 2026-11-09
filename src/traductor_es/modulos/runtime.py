"""Texto escrito en el código Java de los mods: se traduce a una tabla que lee el mod de apoyo (ModpackES Runtime).

Un resource pack no puede cambiar un texto que el mod tiene escrito en su código. El mod de apoyo, en el
cliente, cambia un mensaje de chat, de la barra de acción o un tooltip solo si su texto es **exactamente** uno de
la tabla `assets/modpackes_runtime/textos/<variante>.json` que se genera aquí (inglés → español).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ..formatos import lang_json
from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, contar
from .cobertura import frases_por_mod

AMBITO = "ui"
RUTA_TABLA = "assets/modpackes_runtime/textos/{variante}.json"
#: Datos variables de un `String.format`: el mod los trata como una plantilla («Hello %s!» coincide con «Hello Steve!»).
_MARCADORES = re.compile(r"%(?:\d+\$)?[sd%]")


def _marcadores(texto: str) -> list[str]:
    return _MARCADORES.findall(texto)


class TextoDeJava:
    nombre = "Texto del código de los mods"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._frases: list[tuple[Path, list[str]]] = []

    def detectar(self) -> bool:
        return bool(self.ctx.instancia.jars())

    def describir(self) -> str:
        total = sum(len(f) for _, f in self._frases)
        return (
            f"{contar(total, 'frase')} en {contar(len(self._frases), 'mod')}"
            if self._frases
            else "frases del código de los mods"
        )

    def recolectar(self) -> list[Pieza]:
        self._frases = frases_por_mod(self.ctx.instancia)
        return [Pieza(f, self._pista(jar.name, f)) for jar, frases in self._frases for f in frases]

    @staticmethod
    def _pista(mod: str, frase: str) -> str:
        base = f"texto del código de {mod}"
        return f"{base}; los marcadores %s y %d son datos: déjalos en el mismo orden" if _marcadores(frase) else base

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        tabla: dict[str, str] = {}
        for _, frases in self._frases:
            for frase in frases:
                traducida = traducciones.get(frase)
                if traducida is None or traducida == frase or not es_traducible(frase):
                    resumen.pendientes += 1
                elif _marcadores(traducida) != _marcadores(frase):
                    # El mod rellena los datos en orden: si la traducción los cambia de sitio, mostraría un dato
                    # en el lugar de otro. Mejor dejar el inglés.
                    self.ctx.registro(f"No uso «{traducida[:50]}»: cambió el orden de los datos de «{frase[:50]}»")
                    resumen.pendientes += 1
                else:
                    tabla[frase] = traducida
        resumen.traducidos = len(tabla)
        if not tabla:
            return resumen
        pack = self.ctx.pack_listo()
        datos = lang_json.escribir(dict(sorted(tabla.items())))
        for variante in self.ctx.variantes:  # el mod lee la variante que use el jugador
            resumen.archivos.append(pack.escribir(RUTA_TABLA.format(variante=variante), datos))
        return resumen

    def restaurar(self) -> list[Path]:
        return []  # la tabla va en el resource pack: basta con desactivarlo

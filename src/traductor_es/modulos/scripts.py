"""Texto escrito directamente en los scripts de KubeJS (tooltips, mensajes, nombres visibles).

Solo se traducen cadenas en sitios donde son texto para el jugador. Todo lo que es lógica (ids, tags,
recetas, comparaciones) se deja igual. Los archivos se traducen en el sitio, con copia de seguridad.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..formatos import javascript
from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, contar, parece_clave

AMBITO = "script"
CARPETAS = ("kubejs/client_scripts", "kubejs/server_scripts", "kubejs/startup_scripts")

#: Llamadas cuyo argumento de texto es siempre algo que ve el jugador.
LLAMADAS_TEXTO = frozenset({
    "tell", "statusMessage", "setStatusMessage", "displayClientMessage", "sendSystemMessage", "sendMessage",
    "displayName", "setDisplayName", "tooltip", "addTooltip", "title", "setTitle", "subtitle", "setSubtitle",
    "lore", "setLore", "actionbar", "setActionbar",
})  # fmt: skip
#: `Text.of("…")`, `Text.red("…")`, `Component.literal("…")`…
AYUDAS_TEXTO = frozenset({
    "of", "literal", "string", "black", "darkBlue", "darkGreen", "darkAqua", "darkRed", "darkPurple", "gold", "gray",
    "darkGray", "blue", "green", "aqua", "red", "lightPurple", "yellow", "white",
})  # fmt: skip
RECEPTORES_TEXTO = frozenset({"Text", "Component"})
#: Dentro de estos eventos, `add`, `addAll`… reciben líneas de tooltip, textos de idioma o de información.
EVENTOS_TEXTO = (
    "ItemEvents.tooltip", "ClientEvents.lang", "JEIEvents.information", "REIEvents.information",
    "EMIEvents.information", "onEvent:item.tooltip", "onEvent:jei.information", "onEvent:rei.information",
    "onEvent:client.generate_assets",
)  # fmt: skip
LLAMADAS_EN_EVENTO = frozenset({"add", "addAll", "insert", "addAdvanced", "addItem", "addFluid", "addLang", "addLine"})
_EXPRESION = re.compile(r"\$\{[^{}\n]*\}")


def _parece_texto(texto: str) -> bool:
    """Texto para personas y no un identificador: tiene un espacio, una mayúscula o una letra no ASCII."""
    t = texto.strip()
    return es_traducible(t) and not parece_clave(t) and (" " in t or t != t.lower() or not t.isascii())


def _seguro(c: javascript.CadenaJs, traduccion: str) -> bool:
    """En una plantilla, un «${» nuevo sería código vivo: esa traducción no se usa."""
    return c.comilla != "`" or traduccion.count("${") == c.texto.count("${")


def es_texto_visible(c: javascript.CadenaJs) -> bool:
    if c.comparada or not _parece_texto(c.texto):
        return False
    if c.comilla == "`" and c.texto.count("${") != len(_EXPRESION.findall(c.texto)):
        return False  # plantilla con expresiones complejas: no se puede proteger con seguridad
    if c.funcion in LLAMADAS_TEXTO:
        return True
    if c.funcion in AYUDAS_TEXTO and c.receptor in RECEPTORES_TEXTO:
        return True
    return c.funcion in LLAMADAS_EN_EVENTO and any(ctx.startswith(EVENTOS_TEXTO) for ctx in c.contexto)


@dataclass(slots=True)
class _Script:
    ruta: Path
    src: str
    cadenas: list[javascript.CadenaJs]
    elegidas: list[javascript.CadenaJs]


class ScriptsKubeJS:
    nombre = "Scripts de KubeJS"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._scripts: list[_Script] = []

    def _archivos(self) -> list[Path]:
        juego = self.ctx.instancia.juego
        return [p for c in CARPETAS if (juego / c).is_dir() for p in sorted((juego / c).rglob("*.js"))]

    def detectar(self) -> bool:
        return bool(self._archivos())

    def describir(self) -> str:
        return contar(len(self._archivos()), "script")

    def recolectar(self) -> list[Pieza]:
        self._scripts = []
        for ruta in self._archivos():
            original = self.ctx.respaldo.original(ruta)
            if original is None:
                continue
            try:
                src = original.decode("utf-8")
                cadenas = javascript.escanear(src)
            except (ValueError, UnicodeDecodeError):
                self.ctx.registro(f"{ruta.name}: no pude leerlo con seguridad, se deja igual")
                continue
            elegidas = [c for c in cadenas if es_texto_visible(c)]
            if elegidas:
                self._scripts.append(_Script(ruta, src, cadenas, elegidas))
        return [Pieza(c.texto, f"script: {c.funcion}") for s in self._scripts for c in s.elegidas]

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        for s in self._scripts:
            nuevos = {
                c.inicio: traducciones[c.texto]
                for c in s.elegidas
                if c.texto in traducciones and _seguro(c, traducciones[c.texto])
            }
            resumen.traducidos += len(nuevos)
            resumen.pendientes += len(s.elegidas) - len(nuevos)
            datos = javascript.reemplazar(s.src, s.cadenas, nuevos).encode("utf-8")
            actual = s.ruta.read_bytes() if s.ruta.is_file() else None
            if nuevos and actual != datos:
                self.ctx.respaldo.escribir(s.ruta, datos)
                resumen.archivos.append(s.ruta)
        return resumen

    def restaurar(self) -> list[Path]:
        return self.ctx.respaldo.restaurar("kubejs/")

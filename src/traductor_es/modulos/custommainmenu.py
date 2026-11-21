"""Menú principal de CustomMainMenu (lumien, Minecraft 1.12 y anteriores): `config/CustomMainMenu/*.json`.

El texto de los botones pasa por `I18n.format` y el de las etiquetas no (lumien231/Custom-Main-Menu, `GuiCustomButton`,
`GuiCustomLabel`). Por eso se traduce en su lugar el valor literal: `buttons.<id>.text`, `hoverText` y `tooltip`,
`labels.<id>.text` y `hoverText`, y los textos de `other.splash-text.texts`. Un valor que ya es una clave de idioma
(«menu.singleplayer») lo traduce el juego, y los que empiezan con `web:` o `file:` son fuentes, no texto: no se tocan.
El archivo tiene un solo idioma, así que se reescribe en su lugar con copia, y solo cambian esas cadenas.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..formatos import json_cadenas
from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, contar, parece_clave
from .cambios import Lugar

AMBITO = "ui"
CARPETA = "config/CustomMainMenu"
PISTA = "texto de un botón o etiqueta del menú principal: corto"
BOM = b"\xef\xbb\xbf"
_CAMPOS = {"buttons": frozenset({"text", "hoverText", "tooltip"}), "labels": frozenset({"text", "hoverText"})}


def es_visible(cadena: json_cadenas.CadenaJson) -> bool:
    ruta = cadena.ruta
    texto = cadena.texto.strip()
    if not texto or parece_clave(texto) or texto.startswith(("web:", "file:")) or not es_traducible(texto):
        return False
    if len(ruta) == 3 and isinstance(ruta[0], str) and ruta[0] in _CAMPOS:
        return ruta[2] in _CAMPOS[ruta[0]]
    return len(ruta) == 4 and ruta[:3] == ("other", "splash-text", "texts")


#: Marcadores de CustomMainMenu que el mod reemplaza por un dato («#modsloaded#», «#mcversion#»).
_MARCADOR = re.compile(r"#\w+#")


def marcar(texto: str) -> tuple[str, list[str]]:
    """El texto con cada marcador `#…#` cambiado por `{pN}` (la máscara lo protege) y la lista de marcadores."""
    marcadores: list[str] = []

    def cambiar(m: re.Match[str]) -> str:
        marcadores.append(m.group())
        return f"{{p{len(marcadores) - 1}}}"

    return _MARCADOR.sub(cambiar, texto), marcadores


def desmarcar(traducido: str, marcadores: list[str]) -> str | None:
    """Los marcadores de vuelta; None si el motor perdió o inventó alguno."""
    if sorted(re.findall(r"\{p(\d+)\}", traducido)) != sorted(str(i) for i in range(len(marcadores))):
        return None
    return re.sub(r"\{p(\d+)\}", lambda m: marcadores[int(m.group(1))], traducido)


@dataclass(slots=True)
class _Archivo:
    ruta: Path
    src: str
    cadenas: list[json_cadenas.CadenaJson]
    elegidas: list[json_cadenas.CadenaJson]
    bom: bool  #: el archivo empieza con BOM: se conserva


class CustomMainMenu:
    nombre = "Menú de CustomMainMenu"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._archivos: list[_Archivo] = []

    def _rutas(self) -> list[Path]:
        carpeta = self.ctx.instancia.juego / CARPETA
        return sorted(carpeta.glob("*.json")) if carpeta.is_dir() else []

    def detectar(self) -> bool:
        return bool(self._rutas())

    def describir(self) -> str:
        return contar(len(self._rutas()), "menú", "menús")

    def recolectar(self) -> list[Pieza]:
        self._archivos = []
        for ruta in self._rutas():
            original = self.ctx.respaldo.original(ruta)
            if original is None:
                continue
            try:
                src = original.decode("utf-8-sig")
                cadenas = json_cadenas.escanear(src)
            except (ValueError, UnicodeDecodeError):
                self.ctx.registro(f"{ruta.name}: no pude leerlo con seguridad, se deja igual")
                continue
            if elegidas := [c for c in cadenas if es_visible(c)]:
                self._archivos.append(_Archivo(ruta, src, cadenas, elegidas, original.startswith(BOM)))
        return [Pieza(marcar(c.texto)[0], PISTA) for a in self._archivos for c in a.elegidas]

    def lugares(self) -> list[Lugar]:
        juego = self.ctx.instancia.juego
        return [Lugar(a.ruta.relative_to(juego).as_posix(), [c.texto for c in a.elegidas]) for a in self._archivos]

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        for a in self._archivos:
            nuevos: dict[int, str] = {}
            for c in a.elegidas:
                marcado, marcadores = marcar(c.texto)
                traducido = traducciones.get(marcado)
                if traducido is not None and (final := desmarcar(traducido, marcadores)) is not None:
                    nuevos[c.inicio] = final
            resumen.traducidos += len(nuevos)
            resumen.pendientes += len(a.elegidas) - len(nuevos)
            datos = (BOM if a.bom else b"") + json_cadenas.reemplazar(a.src, a.cadenas, nuevos).encode("utf-8")
            actual = a.ruta.read_bytes() if a.ruta.is_file() else None
            if nuevos and actual != datos:
                self.ctx.respaldo.escribir(a.ruta, datos)
                resumen.archivos.append(a.ruta)
        return resumen

    def restaurar(self) -> list[Path]:
        return self.ctx.respaldo.restaurar(f"{CARPETA}/")

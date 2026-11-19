"""Menús de FancyMenu (y Drippy Loading Screen): el texto de los botones y de los textos del menú principal.

Los diseños viven en `config/fancymenu/customization/*.txt` (y en `config/drippyloadingscreen/customization/`), en
bloques `nombre { clave = valor }`. El texto visible depende del bloque (leído en Keksuccino/FancyMenu):

- **v3** (`element { … element_type = … }`): en los botones (`custom_button`, `vanilla_button`) `label`, `hoverlabel`
  y `description` (el tooltip); en los textos y splash (`text_v2`, `splash_text`, `fancymenu_customization_item_text`)
  `source`, **solo** con `source_mode = direct` (con `resource`, `source` es la ruta de un archivo).
- **v2** (`customization { action = … }`): `addbutton` → `label`, `hoverlabel`, `description` (ahí `value` es la acción
  del botón: no se toca); `addtext`, `renamebutton`, `setbuttonlabel` → `value`; `sethoverlabel` → `label`;
  `setbuttondescription` → `description`; `addsplash` → `text`.

Un diseño tiene un solo idioma, así que se reescribe en su lugar (con copia, como los scripts), y solo el valor de esas
líneas: identificadores, acciones, rutas y requisitos quedan igual. Los marcadores de FancyMenu dentro del texto
(`{"placeholder":"loadedmods"}`) y el salto `%n%` se protegen y vuelven exactos. Un valor que ya usa una clave de
idioma (`{"placeholder":"local",…}`) se deja: ya se traduce con el idioma.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, contar
from .cambios import Lugar

AMBITO = "ui"
CARPETAS = ("config/fancymenu/customization", "config/drippyloadingscreen/customization")
PISTA = "texto de un botón o del menú principal (FancyMenu): corto"

_BOTONES_V3 = frozenset({"custom_button", "vanilla_button"})
_TEXTOS_V3 = frozenset({"text_v2", "splash_text", "fancymenu_customization_item_text", "text"})
_CAMPOS_BOTON = frozenset({"label", "hoverlabel", "description"})
_ACCIONES_V2 = {
    "addbutton": frozenset({"label", "hoverlabel", "description"}),
    "addtext": frozenset({"value"}),
    "renamebutton": frozenset({"value"}),
    "setbuttonlabel": frozenset({"value"}),
    "sethoverlabel": frozenset({"label"}),
    "setbuttondescription": frozenset({"description"}),
    "addsplash": frozenset({"text"}),
}
_LINEA = re.compile(r"^(?P<antes>\s*(?P<clave>[\w.\-:\[\]]+)\s*=\s*)(?P<valor>.*?)(?P<despues>\s*)$")
_ABRE = re.compile(r"^\s*([\w\-]+)\s*\{\s*$")
_CIERRA = re.compile(r"^\s*\}\s*$")
_MARCADOR_LOCAL = re.compile(r'"placeholder"\s*:\s*"local"')
_SALTO = "%n%"
#: Colores del texto de FancyMenu: `%#FF5500%` abre un color y `%#%` lo cierra.
_COLOR = re.compile(r"%#(?:[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?)?%")


@dataclass(slots=True)
class _Valor:
    linea: int
    texto: str  #: lo que se manda al motor (con los marcadores cambiados por {p0}, {p1}…)
    marcadores: list[str]


def _marcadores_json(valor: str) -> tuple[str, list[str]] | None:
    """Cambia cada marcador JSON `{…}` (con llaves anidadas) y cada color `%#…%` por `{pN}`, y `%n%` por un salto.

    None si las llaves no cierran."""
    salida: list[str] = []
    marcadores: list[str] = []
    i = 0
    while i < len(valor):
        if valor.startswith(_SALTO, i):
            salida.append("\n")
            i += len(_SALTO)
            continue
        if color := _COLOR.match(valor, i):
            salida.append(f"{{p{len(marcadores)}}}")
            marcadores.append(color.group())
            i = color.end()
            continue
        if valor[i] == "{":
            profundidad, j = 0, i
            while j < len(valor):
                profundidad += {"{": 1, "}": -1}.get(valor[j], 0)
                if profundidad == 0:
                    break
                j += 1
            if profundidad != 0:
                return None
            salida.append(f"{{p{len(marcadores)}}}")
            marcadores.append(valor[i : j + 1])
            i = j + 1
            continue
        salida.append(valor[i])
        i += 1
    return "".join(salida), marcadores


def _devolver(traducido: str, marcadores: list[str]) -> str | None:
    """El texto traducido con los marcadores y `%n%` de vuelta; None si el motor perdió o inventó alguno."""
    if sorted(re.findall(r"\{p(\d+)\}", traducido)) != sorted(str(i) for i in range(len(marcadores))):
        return None
    texto = re.sub(r"\{p(\d+)\}", lambda m: marcadores[int(m.group(1))], traducido)
    return texto.replace("\r\n", "\n").replace("\n", _SALTO)


def valores_visibles(lineas: Sequence[str]) -> list[tuple[int, str]]:
    """(número de línea, valor) de cada texto visible del diseño, según el bloque en que está."""
    salida: list[tuple[int, str]] = []
    bloque: list[tuple[int, str, str]] = []  # (línea, clave, valor) del bloque abierto
    for n, linea in enumerate([*lineas, "}"]):
        if _ABRE.match(linea):
            bloque = []
            continue
        if _CIERRA.match(linea):
            datos = {clave: valor for _, clave, valor in bloque}
            tipo = datos.get("element_type", "")
            accion = datos.get("action", "")
            if tipo in _BOTONES_V3:
                campos = _CAMPOS_BOTON
            elif tipo in _TEXTOS_V3 and datos.get("source_mode") == "direct":
                campos = frozenset({"source"})
            else:
                campos = _ACCIONES_V2.get(accion, frozenset())
            salida += [(ln, v) for ln, clave, v in bloque if clave in campos]
            bloque = []
            continue
        if m := _LINEA.match(linea):
            bloque.append((n, m.group("clave"), m.group("valor")))
    return [(n, v) for n, v in salida if n < len(lineas)]


@dataclass(slots=True)
class _Diseno:
    ruta: Path
    lineas: list[str]
    valores: list[_Valor]


class FancyMenu:
    nombre = "Menús de FancyMenu"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._disenos: list[_Diseno] = []

    def _archivos(self) -> list[Path]:
        juego = self.ctx.instancia.juego
        return sorted(p for c in CARPETAS if (juego / c).is_dir() for p in (juego / c).rglob("*.txt"))

    def detectar(self) -> bool:
        return bool(self._archivos())

    def describir(self) -> str:
        return contar(len(self._archivos()), "diseño de menú", "diseños de menú")

    def recolectar(self) -> list[Pieza]:
        self._disenos = []
        for ruta in self._archivos():
            original = self.ctx.respaldo.original(ruta)
            if original is None:
                continue
            try:
                texto = original.decode("utf-8")
            except UnicodeDecodeError:
                self.ctx.registro(f"{ruta.name}: no pude leerlo con seguridad, se deja igual")
                continue
            lineas = texto.split("\n")
            valores: list[_Valor] = []
            for n, valor in valores_visibles(lineas):
                if _MARCADOR_LOCAL.search(valor):
                    continue  # ya usa una clave de idioma
                partido = _marcadores_json(valor.rstrip("\r"))
                if partido is None or not es_traducible(re.sub(r"\{p\d+\}", " ", partido[0])):
                    continue
                valores.append(_Valor(n, partido[0], partido[1]))
            if valores:
                self._disenos.append(_Diseno(ruta, lineas, valores))
        return [Pieza(v.texto, PISTA) for d in self._disenos for v in d.valores]

    def lugares(self) -> list[Lugar]:
        juego = self.ctx.instancia.juego
        return [Lugar(d.ruta.relative_to(juego).as_posix(), [v.texto for v in d.valores]) for d in self._disenos]

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        for d in self._disenos:
            lineas = list(d.lineas)
            cambiadas = 0
            for v in d.valores:
                traducido = traducciones.get(v.texto)
                nuevo = _devolver(traducido, v.marcadores) if traducido is not None else None
                m = _LINEA.match(lineas[v.linea].rstrip("\r"))
                if nuevo is None or m is None or "\n" in nuevo:
                    resumen.pendientes += 1
                    continue
                fin = "\r" if lineas[v.linea].endswith("\r") else ""
                lineas[v.linea] = f"{m.group('antes')}{nuevo}{m.group('despues')}{fin}"
                cambiadas += 1
            resumen.traducidos += cambiadas
            datos = "\n".join(lineas).encode("utf-8")
            actual = d.ruta.read_bytes() if d.ruta.is_file() else None
            if cambiadas and actual != datos:
                self.ctx.respaldo.escribir(d.ruta, datos)
                resumen.archivos.append(d.ruta)
        return resumen

    def restaurar(self) -> list[Path]:
        restaurados: list[Path] = []
        for carpeta in CARPETAS:
            restaurados += self.ctx.respaldo.restaurar(f"{carpeta}/")
        return restaurados

"""Idioma de los shaderpacks (menú de opciones de Iris y Oculus).

Un shaderpack trae sus textos en `shaders/lang/en_US.lang` (formato `.properties`: `option.X`, `screen.X`,
`value.X.<v>`…). Iris solo usa ese archivo cuando la clave **no** está en el idioma del juego (`MixinClientLanguage`),
así que una clave del resource pack lo pisa. Por eso la traducción va al resource pack, en un espacio propio
(`assets/modpackes_shaders/lang/`), sin tocar el shaderpack ni el idioma de los mods.

Con OptiFine no se sabe si pasa lo mismo: sin Iris ni Oculus en `mods/`, el módulo no hace nada. Las claves son
globales: si dos shaderpacks usan la misma clave con distinto inglés, esa clave no se traduce (se vería la de uno en
el otro). El español que ya trae un shaderpack se copia a las variantes que no lo tienen, sin gastar.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..formatos import propiedades
from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, contar
from .cambios import Lugar

AMBITO = "ui"
ESPACIO = "modpackes_shaders"
_CARGADORES = re.compile(r"^(iris|oculus)[-_+ ]", re.I)
_LANG = re.compile(r"^shaders/lang/([a-z]{2}_[a-z]{2})\.lang$", re.I)
TOPE = 4 * 1024 * 1024


@dataclass(slots=True)
class _Shader:
    nombre: str
    idiomas: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])  #: {es_es: {clave: texto}}


def _leer_shader(ruta: Path) -> _Shader | None:
    """Los idiomas de un shaderpack (zip o carpeta)."""
    shader = _Shader(ruta.name)
    try:
        if ruta.is_dir():
            carpeta = ruta / "shaders" / "lang"
            archivos = sorted(carpeta.glob("*.lang")) if carpeta.is_dir() else []
            for a in archivos:
                if a.stat().st_size <= TOPE:
                    shader.idiomas[a.stem.lower()] = propiedades.leer(a.read_text(encoding="utf-8", errors="replace"))
        elif ruta.suffix.lower() == ".zip":
            with zipfile.ZipFile(ruta) as z:
                for info in z.infolist():
                    if (m := _LANG.match(info.filename)) and info.file_size <= TOPE:
                        texto = z.read(info).decode("utf-8", errors="replace")
                        shader.idiomas[m.group(1).lower()] = propiedades.leer(texto)
    except (OSError, zipfile.BadZipFile):
        return None
    return shader if "en_us" in shader.idiomas else None


class Shaders:
    nombre = "Opciones de los shaders"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._ingles: dict[str, str] = {}  #: clave → inglés, solo las que no chocan entre shaderpacks
        self._espanol: dict[str, dict[str, str]] = {}  #: variante → {clave: español que ya trae el shaderpack}
        self._por_shader: dict[str, list[str]] = {}

    def _con_iris(self) -> bool:
        return any(_CARGADORES.match(j.name) for j in self.ctx.instancia.jars())

    def _shaders(self) -> list[_Shader]:
        carpeta = self.ctx.instancia.juego / "shaderpacks"
        if not carpeta.is_dir():
            return []
        return [s for p in sorted(carpeta.iterdir()) if (s := _leer_shader(p)) is not None]

    def detectar(self) -> bool:
        return self._con_iris() and bool(self._shaders())

    def describir(self) -> str:
        return f"{contar(len(self._por_shader), 'shaderpack')}, {contar(len(self._ingles), 'texto')}"

    def recolectar(self) -> list[Pieza]:
        vistos: dict[str, set[str]] = {}
        self._por_shader = {}
        self._espanol = {}
        shaders = self._shaders() if self._con_iris() else []
        for s in shaders:
            for clave, texto in s.idiomas["en_us"].items():
                vistos.setdefault(clave, set()).add(texto)
        self._ingles = {
            c: next(iter(t)) for c, t in vistos.items() if len(t) == 1 and es_traducible(next(iter(t)))
        }  # fmt: skip
        for s in shaders:
            claves = [c for c in s.idiomas["en_us"] if c in self._ingles]
            self._por_shader[s.nombre] = claves
            for idioma, textos in s.idiomas.items():
                if idioma.startswith("es_"):
                    destino = self._espanol.setdefault(idioma, {})
                    for c in claves:
                        if textos.get(c, "").strip() and textos[c] != self._ingles[c]:
                            destino.setdefault(c, textos[c])
        # Lo que ya trae español en algún dialecto no se manda al motor: se copia
        con_espanol = {c for por in self._espanol.values() for c in por}
        return [
            Pieza(t, self._pista(c)) for c, t in self._ingles.items() if c not in con_espanol
        ]  # fmt: skip

    @staticmethod
    def _pista(clave: str) -> str:
        if clave.endswith(".comment"):
            return "explicación de una opción de un shader (menú de shaders de Iris)"
        if clave.startswith("value."):
            return "valor de una opción de un shader (menú de shaders de Iris): corto"
        return "nombre de una opción o pantalla de un shader (menú de shaders de Iris): corto"

    def lugares(self) -> list[Lugar]:
        """Por shaderpack, sus textos en inglés con clave (tras `recolectar`)."""
        return [
            Lugar(f"shaderpacks/{nombre}", {c: self._ingles[c] for c in claves})
            for nombre, claves in self._por_shader.items()
        ]

    def _existente(self, variante: str, clave: str) -> str | None:
        """El español que ya trae el shaderpack: el de la misma variante, o el de otra."""
        if (t := self._espanol.get(variante, {}).get(clave)) is not None:
            return t
        return next((por[clave] for por in self._espanol.values() if clave in por), None)

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        if not self._ingles:
            return resumen
        pack = self.ctx.pack_listo()
        for variante in self.ctx.variantes:
            tabla: dict[str, str] = {}
            for clave, ingles in self._ingles.items():
                texto = self._existente(variante, clave) or traducciones.get(ingles)
                if texto is not None and texto != ingles:
                    tabla[clave] = texto
            if tabla:
                resumen.archivos.append(pack.escribir_lang(ESPACIO, variante, dict(sorted(tabla.items()))))
        traducidas = {c for c, t in self._ingles.items() if self._existente(self.ctx.dialecto, c) or t in traducciones}
        resumen.traducidos = len(traducidas)
        resumen.pendientes = len(self._ingles) - len(traducidas)
        return resumen

    def restaurar(self) -> list[Path]:
        return []  # va en el resource pack: basta con desactivarlo

"""Descripción de cada mod en la lista de mods del juego, con las claves de idioma que leen esas pantallas.

- **Mod Menu** (Fabric y Quilt) muestra `modmenu.descriptionTranslation.<id>` si existe; si no, la descripción de
  `fabric.mod.json` o `quilt.mod.json` (TerraformersMC/ModMenu, `Mod.java`). Solo si Mod Menu está en `mods/`.
- **NeoForge** desde 20.4.179 (Minecraft 1.20.4) muestra `fml.menu.mods.info.description.<modid>` en vez del
  `description` de `neoforge.mods.toml`; desde la lista de mods nueva, `neoforge.screen.mods.info.description.<modid>`.
  Se escriben las dos.
- **Forge** no tiene clave: la lista muestra el texto del `mods.toml` tal cual. No se puede sin tocar el jar.

Las claves van al resource pack en un espacio propio (`assets/modpackes_mods/lang/`), así que el idioma de los mods no
cambia. Una descripción que el mod ya traduce en su propio idioma se respeta.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from ..fuentes.contenedores import abrir_mod
from ..fuentes.version import Version
from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, contar
from .cambios import Lugar

AMBITO = "ui"
ESPACIO = "modpackes_mods"
PISTA = "descripción de un mod en la lista de mods del juego"
_MOD_MENU = re.compile(r"^modmenu[-_]", re.I)
CLAVE_MOD_MENU = "modmenu.descriptionTranslation.{id}"
CLAVES_NEOFORGE = ("fml.menu.mods.info.description.{id}", "neoforge.screen.mods.info.description.{id}")
NEOFORGE_CON_CLAVES = Version.de("1.20.4")


def _de_fabric(datos: bytes) -> list[tuple[str, str]]:
    try:
        raiz: object = json.loads(datos.decode("utf-8-sig"))
    except ValueError:
        return []
    if not isinstance(raiz, dict):
        return []
    r = cast(dict[str, Any], raiz)
    ident, descripcion = r.get("id"), r.get("description")
    return [(ident, descripcion)] if isinstance(ident, str) and isinstance(descripcion, str) else []


def _de_quilt(datos: bytes) -> list[tuple[str, str]]:
    try:
        raiz: object = json.loads(datos.decode("utf-8-sig"))
    except ValueError:
        return []
    cargador = cast(dict[str, Any], raiz).get("quilt_loader") if isinstance(raiz, dict) else None
    if not isinstance(cargador, dict):
        return []
    q = cast(dict[str, Any], cargador)
    meta = q.get("metadata")
    descripcion = cast(dict[str, Any], meta).get("description") if isinstance(meta, dict) else None
    ident = q.get("id")
    return [(ident, descripcion)] if isinstance(ident, str) and isinstance(descripcion, str) else []


def _de_toml(datos: bytes) -> list[tuple[str, str]]:
    try:
        raiz = tomllib.loads(datos.decode("utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    salida: list[tuple[str, str]] = []
    for m in cast(list[object], raiz.get("mods", [])) if isinstance(raiz.get("mods"), list) else []:
        if isinstance(m, dict):
            d = cast(dict[str, Any], m)
            ident, descripcion = d.get("modId"), d.get("description")
            if isinstance(ident, str) and isinstance(descripcion, str):
                salida.append((ident, descripcion))
    return salida


class Descripciones:
    nombre = "Descripciones de los mods"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._descripciones: dict[str, str] = {}  #: id del mod → descripción en inglés (sin espacios en los bordes)

    def _claves(self) -> tuple[str, ...]:
        """Las claves que lee la lista de mods de este loader y versión ("" si no hay)."""
        inst = self.ctx.instancia
        if inst.loader in ("fabric", "quilt") and any(_MOD_MENU.match(j.name) for j in inst.jars()):
            return (CLAVE_MOD_MENU,)
        if inst.loader == "neoforge" and inst.version >= NEOFORGE_CON_CLAVES:
            return CLAVES_NEOFORGE
        return ()

    def detectar(self) -> bool:
        return bool(self._claves()) and bool(self.ctx.instancia.jars())

    def describir(self) -> str:
        return contar(len(self._descripciones), "mod")

    def _leer(self) -> dict[str, str]:
        lectores = {"fabric.mod.json": _de_fabric, "quilt.mod.json": _de_quilt,
                    "META-INF/neoforge.mods.toml": _de_toml, "META-INF/mods.toml": _de_toml}  # fmt: skip
        salida: dict[str, str] = {}
        for jar in self.ctx.instancia.jars():
            contenedores = list(abrir_mod(jar))  # los anidados se leen del padre: se cierran todos al final
            try:
                for contenedor in contenedores:
                    nombres = set(contenedor.nombres())
                    for archivo, lector in lectores.items():
                        if archivo not in nombres:
                            continue
                        try:
                            datos = contenedor.leer(archivo)
                        except (KeyError, OSError):
                            continue
                        for ident, descripcion in lector(datos):
                            limpia = descripcion.strip()
                            if limpia and es_traducible(limpia):
                                salida.setdefault(ident, limpia)
            finally:
                for contenedor in contenedores:
                    contenedor.cerrar()
        return salida

    def recolectar(self) -> list[Pieza]:
        claves = self._claves()
        self._descripciones = self._leer() if claves else {}
        # El mod que ya trae su descripción en español (en su propio idioma) se respeta
        tabla = self.ctx.instancia.tabla_idiomas()
        buscadas = {c.format(id=ident): ident for ident in self._descripciones for c in claves}
        for ns, por_idioma in tabla.datos.items():
            for variante in self.ctx.variantes:
                for clave in buscadas.keys() & por_idioma.get(variante, {}).keys():
                    if tabla.es_valida(ns, variante, clave):
                        self._descripciones.pop(buscadas[clave], None)
        return [Pieza(d, PISTA) for d in self._descripciones.values()]

    def lugares(self) -> list[Lugar]:
        return [Lugar("lista de mods", dict(sorted(self._descripciones.items())))]

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        claves = self._claves()
        tabla: dict[str, str] = {}
        for ident, descripcion in sorted(self._descripciones.items()):
            traducida = traducciones.get(descripcion)
            if traducida is None or traducida == descripcion:
                resumen.pendientes += 1
                continue
            resumen.traducidos += 1
            for c in claves:
                tabla[c.format(id=ident)] = traducida
        if tabla:
            pack = self.ctx.pack_listo()
            for variante in self.ctx.variantes:
                resumen.archivos.append(pack.escribir_lang(ESPACIO, variante, tabla))
        return resumen

    def restaurar(self) -> list[Path]:
        return []  # va en el resource pack: basta con desactivarlo

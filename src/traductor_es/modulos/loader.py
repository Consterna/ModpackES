"""El idioma del propio loader (NeoForge o Forge): sus menús, comandos y los nombres de las etiquetas comunes (`c`).

Su jar no está en `mods/` sino en `libraries/` del launcher, así que el módulo de mods no lo ve. La sonda del juego
lo mostró: en NeoForge 1.21.1 con es_mx quedaban en inglés unas 280 claves de NeoForge y ~470 del espacio `c`. NeoForge
trae `es_es` pero no `es_mx`, y lo que falta en un idioma cae al inglés, no a otro español.

Aquí se copia el español que ya trae el loader a las variantes que no lo tienen (sin gastar) y se traduce el resto, en
un espacio propio del resource pack (las claves de idioma son globales). El jar se busca en las carpetas `libraries`
de los launchers conocidos, subiendo desde la instancia: Prism y MultiMC (`<raíz>/libraries`), CurseForge
(`Install/libraries`), Modrinth App (`meta/libraries`), ATLauncher y el launcher oficial. Se toma el jar más nuevo
para la versión de Minecraft de la instancia; si no se encuentra, el módulo no hace nada.
"""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen
from .cambios import Lugar

AMBITO = "ui"
ESPACIO = "modpackes_loader"
PISTA = "texto del cargador de mods (NeoForge/Forge): menús, comandos o nombre de una etiqueta de objetos"
_LANG = re.compile(r"^assets/([^/]+)/lang/([a-z]{2}_[a-z]{2})\.json$")
#: FancyModLoader (NeoForge) guarda su idioma en la raíz del jar: `lang/<idioma>.json`.
_LANG_RAIZ = re.compile(r"^lang/([a-z]{2}_[a-z]{2})\.json$")
#: Dónde guarda cada launcher sus librerías, relativo a una carpeta que contiene la instancia.
_CARPETAS_LIBRERIAS = ("libraries", "Install/libraries", "meta/libraries", "data/libraries")


def _numeros(texto: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", texto))


def buscar_librerias(juego: Path) -> list[Path]:
    """Las carpetas `libraries` de un launcher que estén por encima de la instancia (hasta 5 niveles)."""
    salida: list[Path] = []
    for ancestro in [juego, *juego.parents][:6]:
        for relativa in _CARPETAS_LIBRERIAS:
            if (c := ancestro / relativa).is_dir() and c not in salida:
                salida.append(c)
    return salida


def jar_del_loader(librerias: list[Path], loader: str | None, mc: str) -> Path | None:
    """El jar `universal` del loader para esa versión de Minecraft (el de compilación más nueva)."""
    candidatos: list[Path] = []
    partes = mc.split(".")
    for lib in librerias:
        if loader == "neoforge":
            if mc == "1.20.1":  # NeoForge de 1.20.1 todavía se llamaba forge
                candidatos += lib.glob("net/neoforged/forge/1.20.1-*/forge-1.20.1-*-universal.jar")
            elif len(partes) >= 2 and partes[0] == "1":  # 1.21.1 → 21.1.x
                prefijo = f"{partes[1]}.{partes[2] if len(partes) > 2 else '0'}."
                candidatos += [p for p in lib.glob("net/neoforged/neoforge/*/neoforge-*-universal.jar")
                               if p.parent.name.startswith(prefijo)]  # fmt: skip
            else:  # 26.1 → 26.1.x
                candidatos += [p for p in lib.glob("net/neoforged/neoforge/*/neoforge-*-universal.jar")
                               if p.parent.name.startswith(f"{mc}.") or p.parent.name.startswith(f"{mc}-")]  # fmt: skip
        elif loader == "forge":
            candidatos += lib.glob(f"net/minecraftforge/forge/{mc}-*/forge-{mc}-*-universal.jar")
    return max(candidatos, key=lambda p: _numeros(p.parent.name), default=None)


def jar_de_fml(librerias: list[Path], neoforge: Path) -> Path | None:
    """El jar de FancyModLoader que usa esa versión de NeoForge (sus menús y la pantalla de error al cargar).

    Si en `libraries/` hay una sola versión, es esa. Si hay varias, se busca la que nombra la metadata del launcher
    junto a la versión de NeoForge (Prism: `meta/net.neoforged/<versión>.json`; el launcher oficial y CurseForge:
    `versions/**/*.json`). Si no se sabe, no se adivina: None.
    """
    jars = sorted({p for lib in librerias for p in lib.glob("net/neoforged/fancymodloader/loader/*/loader-*.jar")})
    if len(jars) <= 1:
        return jars[0] if jars else None
    version_neoforge = neoforge.parent.name
    for lib in librerias:
        raiz = lib.parent
        metadatas = [raiz / "meta" / "net.neoforged" / f"{version_neoforge}.json", *raiz.glob("versions/*/*.json")]
        for meta in metadatas:
            try:
                texto = meta.read_text(encoding="utf-8", errors="replace") if meta.is_file() else ""
            except OSError:
                continue
            if version_neoforge not in texto:
                continue
            if m := re.search(r"net\.neoforged\.fancymodloader:loader:([\w.+-]+)", texto):
                return next((j for j in jars if j.parent.name == m.group(1)), None)
    return None


def leer_idiomas(jar: Path) -> dict[str, dict[str, dict[str, str]]]:
    """{espacio: {idioma: {clave: texto}}} de los archivos de idioma JSON del jar."""
    salida: dict[str, dict[str, dict[str, str]]] = {}
    try:
        with zipfile.ZipFile(jar) as z:
            for n in z.namelist():
                if m := _LANG.match(n):
                    espacio, idioma = m.group(1), m.group(2)
                elif m := _LANG_RAIZ.match(n):
                    espacio, idioma = "fml", m.group(1)
                else:
                    continue
                try:
                    datos: object = json.loads(z.read(n).decode("utf-8-sig"))
                except ValueError:
                    continue
                if isinstance(datos, dict):
                    textos = {str(k): v for k, v in cast(dict[str, Any], datos).items() if isinstance(v, str)}
                    salida.setdefault(espacio, {})[idioma] = textos
    except (OSError, zipfile.BadZipFile):
        return {}
    return salida


class IdiomaDelLoader:
    nombre = "Textos del loader (NeoForge/Forge)"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._jar: Path | None = None
        self._fml: Path | None = None  #: FancyModLoader de NeoForge, si se sabe cuál es
        self._ingles: dict[str, str] = {}  #: clave → inglés
        self._espanol: dict[str, dict[str, str]] = {}  #: variante → {clave: español que trae el loader}
        self._buscado = False

    def _buscar(self) -> Path | None:
        if not self._buscado:
            inst = self.ctx.instancia
            if inst.loader in ("neoforge", "forge") and not inst.legacy:
                librerias = buscar_librerias(inst.juego)
                self._jar = jar_del_loader(librerias, inst.loader, inst.version.texto)
                if self._jar is not None and self._jar.name.startswith("neoforge-"):
                    self._fml = jar_de_fml(librerias, self._jar)
            self._buscado = True
        return self._jar

    def detectar(self) -> bool:
        return self._buscar() is not None

    def describir(self) -> str:
        jar = self._buscar()
        return jar.name if jar else "loader"

    def recolectar(self) -> list[Pieza]:
        self._ingles, self._espanol = {}, {}
        jar = self._buscar()
        if jar is None:
            return []
        idiomas: list[dict[str, dict[str, str]]] = list(leer_idiomas(jar).values())
        if self._fml is not None:
            idiomas += leer_idiomas(self._fml).values()
        for por_idioma in idiomas:
            ingles = por_idioma.get("en_us", {})
            self._ingles.update({k: v for k, v in ingles.items() if v.strip() and es_traducible(v)})
            for idioma, textos in por_idioma.items():
                if idioma.startswith("es_"):
                    destino = self._espanol.setdefault(idioma, {})
                    # Como en los mods: un «español» idéntico al inglés es un texto que nadie tradujo (el es_es de
                    # NeoForge trae así sus comandos); se manda al motor, que deja igual lo que se escribe igual
                    destino.update({k: v for k, v in textos.items() if k in ingles and v.strip() and v != ingles[k]})
        con_espanol = {c for por in self._espanol.values() for c in por}
        return [Pieza(t, PISTA) for c, t in self._ingles.items() if c not in con_espanol]

    def lugares(self) -> list[Lugar]:
        return [Lugar(self._jar.name if self._jar else "loader", dict(self._ingles))]

    def _existente(self, variante: str, clave: str) -> str | None:
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
                if variante in self._espanol and clave in self._espanol[variante]:
                    continue  # el loader ya lo trae en esta variante: el juego lo usa sin ayuda
                texto = self._existente(variante, clave) or traducciones.get(ingles)
                if texto is not None and texto != ingles:
                    tabla[clave] = texto
            if tabla:
                resumen.archivos.append(pack.escribir_lang(ESPACIO, variante, dict(sorted(tabla.items()))))
        hechas = {c for c, t in self._ingles.items() if self._existente(self.ctx.dialecto, c) or t in traducciones}
        resumen.traducidos = len(hechas)
        resumen.pendientes = len(self._ingles) - len(hechas)
        return resumen

    def restaurar(self) -> list[Path]:
        return []  # va en el resource pack: basta con desactivarlo

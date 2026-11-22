"""Orígenes, poderes y capas de Origins (Apoli): su nombre y su descripción, con claves de idioma en el resource pack.

Cómo usa Origins el `name` y la `description` de `data/<ns>/origins|powers|origin_layers/*.json` depende de la
versión (leído en el código de apace100/origins-fabric, apoli y los ports):

- **Origins hasta 1.10** (Minecraft hasta 1.20.1), el port de Forge/NeoForge y NeoOrigins: una cadena se usa como
  **clave** (`Text.translatable(cadena)`). Basta una entrada `"Chameleon": "Camaleón"` en el idioma.
- **Origins 1.11 y 1.12** (1.20.2 a 1.20.4): los poderes igual; los orígenes y las capas son texto literal, que un
  resource pack no alcanza. Esos no se tocan.
- **Origins 1.13 en adelante** (1.21): el literal es el respaldo de una clave derivada
  (`origin.<ns>.<ruta>.name`, `power.<ns>.<ruta>.description`, `layer.<ns>.<ruta>.name`), que el resource pack pisa.

Nunca se reescribe un archivo de datos: todo va al resource pack, en un espacio propio. Un valor que ya es una clave de
idioma conocida lo traduce el módulo de mods. Solo se leen `name` y `description` de la raíz de cada archivo: las
condiciones, acciones, insignias y subpoderes no se tocan.
"""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from ..fuentes.contenedores import Contenedor, abrir_mod, leer_entrada
from ..nucleo.mascara import es_traducible
from . import datos
from .base import Contexto, Pieza, Resumen, contar
from .cambios import Lugar

AMBITO = "ui"
ESPACIO = "modpackes_origins"
_ARCHIVO = re.compile(r"^data/([^/]+)/(origins|powers|origin_layers)/(.+)\.json$")
_TIPO = {"origins": "origin", "powers": "power", "origin_layers": "layer"}
_PISTA = {
    "origin": "nombre o descripción de un origen (Origins: la raza o clase que elige el jugador)",
    "power": "nombre o descripción de un poder de un origen (Origins)",
    "layer": "nombre de una capa de orígenes (Origins: la pantalla donde se elige)",
}
TOPE = 1024 * 1024

#: Modos según la versión de Origins
CLAVE = "clave"  #: la cadena es la clave
MIXTO = "mixto"  #: poderes como clave; orígenes y capas, literales que no se alcanzan
DERIVADA = "derivada"  #: el literal es el respaldo de una clave derivada del id


@dataclass(frozen=True, slots=True)
class Texto:
    tipo: str  #: origin, power o layer
    ident: str  #: <ns>:<ruta>
    campo: str  #: name o description
    ingles: str


def _version(texto: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", texto.split("+", maxsplit=1)[0].split("-", maxsplit=1)[0])[:3])


def modo_de_origins(contenedores: Iterable[Contenedor]) -> str | None:
    """CLAVE, MIXTO o DERIVADA según la versión de Origins que hay en `mods/`; None si no hay Origins.

    `contenedores`: los de los mods, en el orden de los jars (los que ya abrió la instancia).
    """
    for c in contenedores:
        nombres = set(c.nombres())
        if "fabric.mod.json" in nombres:
            try:
                meta: object = json.loads(c.leer("fabric.mod.json").decode("utf-8-sig"))
            except (KeyError, OSError, ValueError):
                continue
            if isinstance(meta, dict) and cast(dict[str, Any], meta).get("id") == "origins":
                v = _version(str(cast(dict[str, Any], meta).get("version", "")))
                if not v:
                    return None
                return CLAVE if v < (1, 11) else MIXTO if v < (1, 13) else DERIVADA
        for toml in ("META-INF/mods.toml", "META-INF/neoforge.mods.toml"):
            if toml in nombres and re.search(rb'modId\s*=\s*"(origins|neoorigins)"', c.leer(toml)):
                return CLAVE  # port de Forge/NeoForge y NeoOrigins: la cadena es la clave
    return None


def _textos_de(nombre: str, crudo: bytes) -> Iterator[Texto]:
    m = _ARCHIVO.match(nombre)
    if m is None or len(crudo) > TOPE:
        return
    try:
        raiz: object = json.loads(crudo.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return
    if not isinstance(raiz, dict):
        return
    d = cast(dict[str, Any], raiz)
    tipo = _TIPO[m.group(2)]
    ident = f"{m.group(1)}:{m.group(3)}"
    for campo in ("name", "description") if tipo != "layer" else ("name",):
        valor = d.get(campo)
        if isinstance(valor, dict) and isinstance(cast(dict[str, Any], valor).get("text"), str):
            valor = cast(dict[str, Any], valor)["text"]  # componente literal: {"text": "…"}
        if isinstance(valor, str) and valor.strip() and es_traducible(valor):
            yield Texto(tipo, ident, campo, valor)


class Origins:
    nombre = "Orígenes y poderes (Origins)"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._textos: list[Texto] = []
        self._modo: str | None = None
        self.sin_alcance: list[Texto] = []  #: orígenes y capas literales de Origins 1.11–1.12

    def detectar(self) -> bool:
        self._modo = modo_de_origins(self.ctx.instancia.contenedores_mods())
        return self._modo is not None

    def describir(self) -> str:
        return contar(len(self._textos), "texto") if self._textos else "orígenes, poderes y capas"

    def _archivos(self) -> Iterator[tuple[str, bytes]]:
        """(ruta dentro del pack, contenido) de cada origen, poder y capa: en los jars, en datapacks y en zips."""
        for jar in self.ctx.instancia.jars():
            contenedores = list(abrir_mod(jar))
            try:
                for c in contenedores:
                    for n in c.nombres():
                        if _ARCHIVO.match(n):
                            try:
                                yield n, c.leer(n)
                            except (KeyError, OSError):
                                continue
            finally:
                for c in contenedores:
                    c.cerrar()
        juego = self.ctx.instancia.juego
        for ruta in datos.recorrer(juego):
            relativa = ruta.relative_to(juego).as_posix()
            if ruta.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(ruta) as z:
                        for n in z.namelist():
                            if _ARCHIVO.match(n):
                                yield n, leer_entrada(z, n)
                except (zipfile.BadZipFile, OSError):
                    continue
            elif (i := relativa.find("data/")) >= 0 and _ARCHIVO.match(relativa[i:]):
                try:
                    yield relativa[i:], ruta.read_bytes()
                except OSError:
                    continue

    def recolectar(self) -> list[Pieza]:
        if self._modo is None:
            self.detectar()
        self._textos, self.sin_alcance = [], []
        if self._modo is None:
            return []
        conocidas = {k for por in self.ctx.instancia.tabla_idiomas().datos.values() for k in por.get("en_us", {})}
        vistos: set[tuple[str, str, str]] = set()
        for nombre, crudo in self._archivos():
            for t in _textos_de(nombre, crudo):
                if (t.tipo, t.ident, t.campo) in vistos or t.ingles in conocidas or self.clave(t) in conocidas:
                    continue  # el primero que se ve gana; una clave que ya está en un idioma la traduce el de mods
                vistos.add((t.tipo, t.ident, t.campo))
                if self._modo == MIXTO and t.tipo != "power":
                    self.sin_alcance.append(t)
                else:
                    self._textos.append(t)
        return [Pieza(t.ingles, _PISTA[t.tipo]) for t in self._textos]

    def clave(self, t: Texto) -> str:
        if self._modo == DERIVADA:
            ns, _, ruta = t.ident.partition(":")
            return f"{t.tipo}.{ns}.{PurePosixPath(ruta).as_posix().replace('/', '.')}.{t.campo}"
        return t.ingles

    def lugares(self) -> list[Lugar]:
        return [Lugar("Origins", {self.clave(t): t.ingles for t in self._textos})]

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        tabla: dict[str, str] = {}
        for t in self._textos:
            traducida = traducciones.get(t.ingles)
            if traducida is None or traducida == t.ingles:
                resumen.pendientes += 1
                continue
            tabla[self.clave(t)] = _como_valor_de_idioma(traducida)
            resumen.traducidos += 1
        if tabla:
            pack = self.ctx.pack_listo()
            for variante in self.ctx.variantes:
                resumen.archivos.append(pack.escribir_lang(ESPACIO, variante, dict(sorted(tabla.items()))))
        return resumen

    def restaurar(self) -> list[Path]:
        return []  # va en el resource pack: basta con desactivarlo


def _como_valor_de_idioma(texto: str) -> str:
    """Un valor de idioma es un formato: un «%» suelto se escribe «%%» para que se vea igual que en el original."""
    return re.sub(r"%(?!(?:\d+\$)?[sd%])", "%%", texto)

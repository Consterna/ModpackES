"""Contenedores de archivos: jars (incluidos los anidados), zips y carpetas, con la misma interfaz."""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol, cast

_PROFUNDIDAD_MAXIMA = 3
_CARPETAS_ANIDADAS = ("META-INF/jars/", "META-INF/jarjar/", "META-INF/jarinjar/")
#: Tope de lo que se descomprime de una sola entrada de un jar o zip. Ningún archivo de idioma, libro o script real
#: se acerca; lo que lo pasa (un archivo dañado o una «bomba» de compresión) se salta y se avisa.
MAXIMO_ENTRADA = 64 * 2**20
#: Entradas saltadas por pasar el tope («jar!/ruta (N MiB)»), para el aviso del informe.
DESCARTADAS: set[str] = set()


class EntradaDemasiadoGrande(zipfile.BadZipFile):
    """Una entrada que pasa `MAXIMO_ENTRADA`: se trata como un archivo dañado (se salta, no se lee)."""


def _demasiado_grande(origen: str, info: zipfile.ZipInfo) -> bool:
    if info.file_size <= MAXIMO_ENTRADA:
        return False
    DESCARTADAS.add(f"{origen}!/{info.filename} ({info.file_size // 2**20} MiB)")
    return True


def leer_entrada(z: zipfile.ZipFile, entrada: str | zipfile.ZipInfo) -> bytes:
    """`z.read(entrada)` con el tope de tamaño. Lanza `EntradaDemasiadoGrande` (un `BadZipFile`) si lo pasa.

    El tamaño declarado limita lo que entrega `zipfile` (si miente, falla la comprobación CRC): basta con mirarlo.
    """
    info = entrada if isinstance(entrada, zipfile.ZipInfo) else z.getinfo(entrada)
    if _demasiado_grande(str(z.filename or "zip"), info):
        raise EntradaDemasiadoGrande(f"{info.filename} ocupa {info.file_size // 2**20} MiB: no se lee")
    return z.read(info)


class Contenedor(Protocol):
    @property
    def nombre(self) -> str: ...

    def nombres(self) -> list[str]:
        """Rutas internas con barras normales, sin barra inicial."""
        ...

    def leer(self, ruta: str) -> bytes: ...

    def cerrar(self) -> None: ...


class Zip:
    def __init__(self, nombre: str, zf: zipfile.ZipFile) -> None:
        self._nombre = nombre
        self._zf = zf
        # Lo que pasa el tope ni se ofrece: así ningún módulo intenta leerlo
        self._nombres = [i.filename for i in zf.infolist() if not i.is_dir() and not _demasiado_grande(nombre, i)]

    @classmethod
    def abrir(cls, ruta: Path) -> Zip:
        return cls(ruta.name, zipfile.ZipFile(ruta))

    @property
    def nombre(self) -> str:
        return self._nombre

    def nombres(self) -> list[str]:
        return self._nombres

    def leer(self, ruta: str) -> bytes:
        return leer_entrada(self._zf, ruta)

    def cerrar(self) -> None:
        self._zf.close()


class Carpeta:
    def __init__(self, raiz: Path, nombre: str | None = None, prefijo: str = "") -> None:
        """`prefijo` se antepone a las rutas (p. ej. kubejs/assets se expone como assets/...)."""
        self.raiz = raiz
        self._nombre = nombre or raiz.name
        self._prefijo = prefijo
        self._nombres: list[str] | None = None

    @property
    def nombre(self) -> str:
        return self._nombre

    def nombres(self) -> list[str]:
        if self._nombres is None:
            en_raiz = self._prefijo == "assets/"
            self._nombres = (
                sorted(self._prefijo + r for r in _recorrer(self.raiz, en_raiz)) if self.raiz.is_dir() else []
            )
        return self._nombres

    def leer(self, ruta: str) -> bytes:
        if not ruta.startswith(self._prefijo):
            raise KeyError(ruta)
        destino = (self.raiz / ruta[len(self._prefijo) :]).resolve()
        if not destino.is_relative_to(self.raiz.resolve()):  # «../» o una ruta absoluta: nunca se sale de la carpeta
            raise KeyError(ruta)
        return destino.read_bytes()

    def cerrar(self) -> None:
        return None


#: Carpetas de assets que nunca tienen texto: no se recorren (en packs grandes son miles de archivos).
_SIN_TEXTO = frozenset({"textures", "sounds", "models", "blockstates", "shaders", "particles", "font", "optifine",
                        "atlases", "equipment", "items", "post_effect"})  # fmt: skip


def _recorrer(raiz: Path, assets_en_raiz: bool) -> Iterator[str]:
    """Archivos de la carpeta, sin entrar en assets/<mod>/textures y similares.

    `assets_en_raiz`: la carpeta ya es «assets» (como kubejs/assets), así que <mod> está en el primer nivel.
    """
    for carpeta, subcarpetas, archivos in os.walk(raiz):
        partes = Path(carpeta).relative_to(raiz).parts
        en_mod = len(partes) == 1 if assets_en_raiz else (len(partes) == 2 and partes[0] == "assets")
        if en_mod:
            subcarpetas[:] = [d for d in subcarpetas if d not in _SIN_TEXTO]
        for a in archivos:
            yield Path(*partes, a).as_posix()


def abrir_mod(ruta: Path) -> Iterator[Zip]:
    """Un jar de mod y todos sus jars anidados (Fabric META-INF/jars, Forge/NeoForge META-INF/jarjar)."""
    try:
        principal = Zip.abrir(ruta)
    except (zipfile.BadZipFile, OSError):
        return
    yield principal
    yield from _anidados(principal, principal.nombre, 1)


def _declarados(padre: Zip) -> set[str]:
    """Los jars que el mod declara en `fabric.mod.json` (`jars[].file`) o `quilt.mod.json` (`quilt_loader.jars`).

    Fabric y Quilt los cargan estén donde estén dentro del jar (Simple Pipes los deja en la raíz), no solo en
    `META-INF/jars/`.
    """
    salida: set[str] = set()
    nombres = set(padre.nombres())
    for archivo in ("fabric.mod.json", "quilt.mod.json"):
        if archivo not in nombres:
            continue
        try:
            datos: object = json.loads(padre.leer(archivo).decode("utf-8-sig"))
        except (KeyError, OSError, ValueError):
            continue
        if not isinstance(datos, dict):
            continue
        raiz = cast(dict[str, Any], datos)
        if archivo == "quilt.mod.json":
            cargador = raiz.get("quilt_loader")
            raiz = cast(dict[str, Any], cargador) if isinstance(cargador, dict) else {}
        for jar in cast(list[object], raiz.get("jars")) if isinstance(raiz.get("jars"), list) else []:
            ruta = cast(dict[str, Any], jar).get("file") if isinstance(jar, dict) else jar
            if isinstance(ruta, str) and ruta.endswith(".jar") and ruta in nombres:
                salida.add(ruta)
    return salida


def _anidados(padre: Zip, ruta_padre: str, nivel: int) -> Iterator[Zip]:
    if nivel > _PROFUNDIDAD_MAXIMA:
        return
    declarados = _declarados(padre)
    for n in padre.nombres():
        if n.endswith(".jar") and (n.startswith(_CARPETAS_ANIDADAS) or n in declarados):
            try:
                hijo = Zip(f"{ruta_padre}!/{n.rsplit('/', 1)[-1]}", zipfile.ZipFile(io.BytesIO(padre.leer(n))))
            except (zipfile.BadZipFile, OSError, KeyError):
                continue
            yield hijo
            yield from _anidados(hijo, hijo.nombre, nivel + 1)

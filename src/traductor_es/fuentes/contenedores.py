"""Contenedores de archivos: jars (incluidos los anidados), zips y carpetas, con la misma interfaz."""

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

_PROFUNDIDAD_MAXIMA = 3
_CARPETAS_ANIDADAS = ("META-INF/jars/", "META-INF/jarjar/", "META-INF/jarinjar/")


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
        self._nombres = [n for n in zf.namelist() if not n.endswith("/")]

    @classmethod
    def abrir(cls, ruta: Path) -> Zip:
        return cls(ruta.name, zipfile.ZipFile(ruta))

    @property
    def nombre(self) -> str:
        return self._nombre

    def nombres(self) -> list[str]:
        return self._nombres

    def leer(self, ruta: str) -> bytes:
        return self._zf.read(ruta)

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


def _anidados(padre: Zip, ruta_padre: str, nivel: int) -> Iterator[Zip]:
    if nivel > _PROFUNDIDAD_MAXIMA:
        return
    for n in padre.nombres():
        if n.endswith(".jar") and n.startswith(_CARPETAS_ANIDADAS):
            try:
                hijo = Zip(f"{ruta_padre}!/{n.rsplit('/', 1)[-1]}", zipfile.ZipFile(io.BytesIO(padre.leer(n))))
            except (zipfile.BadZipFile, OSError, KeyError):
                continue
            yield hijo
            yield from _anidados(hijo, hijo.nombre, nivel + 1)

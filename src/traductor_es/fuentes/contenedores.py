"""Contenedores de archivos: jars (incluidos los anidados), zips y carpetas, con la misma interfaz."""

from __future__ import annotations

import io
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
            self._nombres = (
                sorted(self._prefijo + p.relative_to(self.raiz).as_posix() for p in self.raiz.rglob("*") if p.is_file())
                if self.raiz.is_dir()
                else []
            )
        return self._nombres

    def leer(self, ruta: str) -> bytes:
        if not ruta.startswith(self._prefijo):
            raise KeyError(ruta)
        return (self.raiz / ruta[len(self._prefijo) :]).read_bytes()

    def cerrar(self) -> None:
        return None


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

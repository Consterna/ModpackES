"""Una instancia de Minecraft: carpeta del juego, versión, loader, mods y recursos."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from types import TracebackType
from typing import Self

from ..nucleo.dialectos import VARIANTES
from . import opciones as opciones_mod
from . import vanilla as vanilla_mod
from .contenedores import Contenedor, abrir_mod
from .deteccion import Deteccion, detectar
from .recursos import PRIORIDAD_VANILLA, Fuente, TablaIdiomas, fuentes_de_recursos, leer_idiomas
from .version import Version, formato_datos, formato_recursos


def resolver_carpeta_juego(carpeta: Path) -> Path | None:
    """Acepta la carpeta de la instancia o la del juego y devuelve la que tiene mods o config."""
    for c in (carpeta, carpeta / "minecraft", carpeta / ".minecraft"):
        if (c / "mods").is_dir() or (c / "config").is_dir():
            return c
    return None


class Instancia:
    def __init__(self, carpeta: Path | str, version: Version | None = None) -> None:
        juego = resolver_carpeta_juego(Path(carpeta))
        if juego is None:
            raise ValueError(f"No encuentro una instancia de Minecraft (carpeta mods o config) en: {carpeta}")
        self.juego = juego
        self.carpeta_mods = juego / "mods"
        self.deteccion: Deteccion = detectar(juego, self._jars_sin_version())
        v = version or self.deteccion.version
        if v is None:
            raise ValueError(
                "No pude saber la versión de Minecraft de esta instancia. Abre el juego una vez (para que haya un "
                "logs/latest.log) o indícala a mano."
            )
        self.version: Version = v
        self.loader = self.deteccion.loader
        self.legacy = self.version < Version.de("1.13")
        self.opciones = opciones_mod.leer(juego)
        self._contenedores: list[Contenedor] | None = None
        self._fuentes: list[Fuente] | None = None
        self._vanilla: vanilla_mod.Vanilla | None = None

    # ------------------------------------------------------------------ mods
    def _jars_sin_version(self) -> list[Path]:
        if not self.carpeta_mods.is_dir():
            return []
        return sorted(p for p in self.carpeta_mods.iterdir() if p.is_file() and p.suffix.lower() in (".jar", ".zip"))

    def jars(self) -> list[Path]:
        """Jars activos: mods/ y, en Forge antiguo, mods/<versión>/. Los .disabled no cuentan."""
        jars = self._jars_sin_version()
        por_version = self.carpeta_mods / self.version.texto
        if por_version.is_dir():
            jars += sorted(p for p in por_version.iterdir() if p.is_file() and p.suffix.lower() in (".jar", ".zip"))
        return jars

    def contenedores_mods(self) -> list[Contenedor]:
        if self._contenedores is None:
            self._contenedores = [c for jar in self.jars() for c in abrir_mod(jar)]
        return self._contenedores

    def fuentes(self) -> list[Fuente]:
        if self._fuentes is None:
            self._fuentes = fuentes_de_recursos(self.juego, self.contenedores_mods(), self.opciones.packs)
        return self._fuentes

    # ------------------------------------------------------------------ idiomas
    def vanilla(self) -> vanilla_mod.Vanilla:
        if self._vanilla is None:
            self._vanilla = vanilla_mod.cargar(self.version, ("en_us", *VARIANTES))
        return self._vanilla

    def tabla_idiomas(self, idiomas: Iterable[str] = ("en_us", *VARIANTES)) -> TablaIdiomas:
        lista = list(idiomas)
        tabla = leer_idiomas(self.fuentes(), lista, self.legacy)
        oficiales = self.vanilla().textos
        for idioma, textos in oficiales.items():
            if idioma in lista:
                tabla.agregar("minecraft", idioma, textos, PRIORIDAD_VANILLA, "minecraft (vanilla)")
        tabla.vanilla_sin_espanol = not any(v in oficiales for v in VARIANTES)
        return tabla

    # ------------------------------------------------------------------ formatos de salida
    def formato_recursos(self) -> tuple[int, int]:
        return self.vanilla().formato_recursos or formato_recursos(self.version)

    def formato_datos(self) -> tuple[int, int] | None:
        return self.vanilla().formato_datos or formato_datos(self.version)

    # ------------------------------------------------------------------ ciclo de vida
    def cerrar(self) -> None:
        vistos: set[int] = set()
        for c in [*(self._contenedores or []), *(f.contenedor for f in self._fuentes or [])]:
            if id(c) not in vistos:
                vistos.add(id(c))
                c.cerrar()
        self._contenedores = None
        self._fuentes = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, tipo: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.cerrar()

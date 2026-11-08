"""El mod de apoyo (ModpackES Runtime): qué versión le toca a una instancia y cómo ponerlo o quitarlo de `mods/`.

El jar se construye aparte (`mod-runtime/`) y viaja dentro de la aplicación, en `traductor_es/recursos/mods/`.
La app solo lo copia cuando el jugador lo pide y solo lo quita si es uno de los suyos.
"""

from __future__ import annotations

import re
import shutil
from importlib import resources
from pathlib import Path

from ..fuentes.instancia import Instancia

PREFIJO = "modpackes_runtime-"
#: (loader, versión de Minecraft) para los que hay mod de apoyo. Cada entrada es un proyecto en `mod-runtime/`.
SOPORTADOS: dict[tuple[str, tuple[int, ...]], str] = {("forge", (1, 20, 1)): "forge-1.20.1"}
_NOMBRE = re.compile(rf"{re.escape(PREFIJO)}(?P<destino>[a-z]+-[\d.]+)-(?P<version>[\w.+-]+)\.jar")


def _carpeta_de_jars() -> Path:
    return Path(str(resources.files("traductor_es") / "recursos" / "mods"))


def destino_de(instancia: Instancia) -> str | None:
    """«forge-1.20.1» si hay mod de apoyo para esta instancia; None si no."""
    return SOPORTADOS.get((instancia.loader or "", instancia.version.partes))


def jar_empaquetado(instancia: Instancia, carpeta: Path | None = None) -> Path | None:
    """El jar más nuevo del mod de apoyo para esta instancia, si viene con la aplicación."""
    destino = destino_de(instancia)
    carpeta = carpeta or _carpeta_de_jars()
    if destino is None or not carpeta.is_dir():
        return None
    candidatos = [p for p in carpeta.glob(f"{PREFIJO}{destino}-*.jar") if p.is_file()]
    return max(candidatos, key=lambda p: p.name, default=None)


def instalados(instancia: Instancia) -> list[Path]:
    """Los jars de ModpackES Runtime que ya están en `mods/` (de cualquier versión)."""
    carpeta = instancia.carpeta_mods
    return sorted(p for p in carpeta.glob(f"{PREFIJO}*.jar") if _NOMBRE.fullmatch(p.name)) if carpeta.is_dir() else []


def estado(instancia: Instancia, carpeta_jars: Path | None = None) -> list[str]:
    """Lo que hay que saber del mod de apoyo en esta instancia, en frases (no abre el juego)."""
    destino = destino_de(instancia)
    if destino is None:
        loader = instancia.loader or "sin loader"
        return [
            f"No hay mod de apoyo para Minecraft {instancia.version} con {loader}: "
            "el texto del código Java seguirá en inglés."
        ]
    lineas = [f"Hay mod de apoyo para esta instancia ({destino})."]
    lineas.append(
        "Esta copia de la aplicación lo trae."
        if jar_empaquetado(instancia, carpeta_jars)
        else "Esta copia de la aplicación NO lo trae."
    )
    puestos = instalados(instancia)
    lineas.append(f"En mods/: {', '.join(p.name for p in puestos)}." if puestos else "No está instalado en mods/.")
    tablas = sorted(
        (instancia.juego / "resourcepacks" / "Traduccion_ES" / "assets" / "modpackes_runtime" / "textos").glob("*.json")
    )
    lineas.append(
        f"Tabla de textos en el resource pack: {len(tablas)} variantes."
        if tablas
        else "Todavía no hay tabla de textos: traduce con la opción activada."
    )
    if puestos and tablas:
        lineas.append("Todo listo: abre el juego en español.")
    return lineas


def instalar(instancia: Instancia, carpeta_jars: Path | None = None) -> Path:
    """Copia el mod de apoyo a `mods/` y quita sus versiones anteriores. ValueError si no hay uno."""
    destino = destino_de(instancia)
    if destino is None:
        loader = instancia.loader or "sin loader"
        raise ValueError(
            f"Todavía no hay mod de apoyo para Minecraft {instancia.version} con {loader}. "
            "El texto escrito en el código de los mods seguirá en inglés."
        )
    origen = jar_empaquetado(instancia, carpeta_jars)
    if origen is None:
        raise ValueError(
            f"Esta copia de la aplicación no trae el mod de apoyo ({destino}). Descarga la versión completa."
        )
    instancia.carpeta_mods.mkdir(parents=True, exist_ok=True)
    final = instancia.carpeta_mods / origen.name
    for viejo in instalados(instancia):
        if viejo != final:
            viejo.unlink()
    shutil.copyfile(origen, final)
    return final


def quitar(instancia: Instancia) -> list[Path]:
    """Quita de `mods/` los jars del mod de apoyo. No toca ningún otro mod."""
    quitados = instalados(instancia)
    for ruta in quitados:
        ruta.unlink()
    return quitados

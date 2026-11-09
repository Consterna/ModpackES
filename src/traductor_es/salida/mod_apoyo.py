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
SOPORTADOS: dict[tuple[str, tuple[int, ...]], str] = {
    ("forge", (1, 16, 5)): "forge-1.16.5",
    ("forge", (1, 18, 2)): "forge-1.18.2",
    ("forge", (1, 19, 2)): "forge-1.19.2",
    ("forge", (1, 20, 1)): "forge-1.20.1",
    ("neoforge", (1, 20, 1)): "forge-1.20.1",  # NeoForge 1.20.1 es un fork de Forge y carga sus mods
    # NeoForge solo publicó 1.21, 1.21.1, 1.21.3, 1.21.4, 1.21.5, 1.21.8, 1.21.10 y 1.21.11 en esa serie
    ("neoforge", (1, 21, 0)): "neoforge-1.21.1",
    ("neoforge", (1, 21, 1)): "neoforge-1.21.1",
    ("neoforge", (1, 21, 3)): "neoforge-1.21.1",
    ("neoforge", (1, 21, 4)): "neoforge-1.21.4",
    ("neoforge", (1, 21, 5)): "neoforge-1.21.5",
    ("neoforge", (1, 21, 8)): "neoforge-1.21.5",
    ("neoforge", (1, 21, 10)): "neoforge-1.21.5",
    ("neoforge", (1, 21, 11)): "neoforge-1.21.11",
    ("fabric", (1, 19, 4)): "fabric-1.19.4",
    # Un jar sirve para varias versiones cuando el mismo código compila y pasa las pruebas contra cada una de ellas
    ("fabric", (1, 20, 0)): "fabric-1.20.1",
    ("fabric", (1, 20, 1)): "fabric-1.20.1",
    ("fabric", (1, 20, 2)): "fabric-1.20.1",
    ("fabric", (1, 20, 3)): "fabric-1.20.4",
    ("fabric", (1, 20, 4)): "fabric-1.20.4",
    ("fabric", (1, 20, 5)): "fabric-1.20.6",
    ("fabric", (1, 20, 6)): "fabric-1.20.6",
    ("fabric", (1, 21, 0)): "fabric-1.21.1",
    ("fabric", (1, 21, 1)): "fabric-1.21.1",
    ("fabric", (1, 21, 2)): "fabric-1.21.4",
    ("fabric", (1, 21, 3)): "fabric-1.21.4",
    ("fabric", (1, 21, 4)): "fabric-1.21.4",
    ("fabric", (1, 21, 5)): "fabric-1.21.5",
    ("fabric", (1, 21, 6)): "fabric-1.21.5",
    ("fabric", (1, 21, 7)): "fabric-1.21.5",
    ("fabric", (1, 21, 8)): "fabric-1.21.5",
    ("fabric", (1, 21, 9)): "fabric-1.21.5",
    ("fabric", (1, 21, 10)): "fabric-1.21.5",
    ("fabric", (1, 21, 11)): "fabric-1.21.11",
    ("fabric", (26, 1, 0)): "fabric-26.1",
    ("fabric", (26, 1, 1)): "fabric-26.1",
    ("fabric", (26, 1, 2)): "fabric-26.1",
    ("fabric", (26, 2, 0)): "fabric-26.1",
    ("fabric", (26, 3, 0)): "fabric-26.1",
}
#: Quilt carga los mods de Fabric con Quilted Fabric API, que existe para estas versiones (no para 1.20.3 ni 1.20.5).
_VERSIONES_DE_QUILT: tuple[tuple[int, ...], ...] = (
    (1, 19, 4), (1, 20, 0), (1, 20, 1), (1, 20, 2), (1, 20, 4), (1, 20, 6), (1, 21, 0), (1, 21, 1),
)  # fmt: skip
SOPORTADOS.update({("quilt", v): SOPORTADOS[("fabric", v)] for v in _VERSIONES_DE_QUILT})
#: Combinaciones que no tendrán mod de apoyo y por qué (para decírselo al jugador en vez de «todavía no»).
_SIN_EVENTO_DE_CHAT = (
    "Fabric API no tiene en esa versión un evento para los mensajes que recibe el cliente, "
    "y sin él el mod de apoyo no podría cambiar el chat. Con Fabric 1.19.4 en adelante sí."
)
IMPOSIBLES: dict[tuple[str, tuple[int, ...]], str] = {
    ("fabric", (1, 16, 5)): _SIN_EVENTO_DE_CHAT,
    ("fabric", (1, 18, 2)): _SIN_EVENTO_DE_CHAT,
    ("fabric", (1, 19, 2)): _SIN_EVENTO_DE_CHAT,
}
_NOMBRE = re.compile(rf"{re.escape(PREFIJO)}(?P<destino>[a-z]+-[\d.]+)-(?P<version>[\w.+-]+)\.jar")


def _carpeta_de_jars() -> Path:
    return Path(str(resources.files("traductor_es") / "recursos" / "mods"))


def destino_de(instancia: Instancia) -> str | None:
    """«forge-1.20.1» si hay mod de apoyo para esta instancia; None si no."""
    return SOPORTADOS.get((instancia.loader or "", instancia.version.partes))


def _sin_mod(instancia: Instancia) -> str:
    """Por qué no hay mod de apoyo para esta instancia, en una frase."""
    razon = IMPOSIBLES.get((instancia.loader or "", instancia.version.partes))
    if razon is not None:
        return f"No hay mod de apoyo para Minecraft {instancia.version} con {instancia.loader}: {razon}"
    loader = instancia.loader or "sin loader"
    return f"Todavía no hay mod de apoyo para Minecraft {instancia.version} con {loader}."


def _nota_de_compatibilidad(instancia: Instancia) -> str | None:
    """Cuando el jar es de otro loader que el de la instancia (y no se ha probado en él), se dice."""
    if instancia.loader == "quilt":
        return (
            "Es el mod de Fabric: Quilt lo carga con Quilted Fabric API (necesita que esté instalada) y no se ha "
            "probado en Quilt."
        )
    if instancia.loader == "neoforge" and instancia.version.partes == (1, 20, 1):
        return "Es el mod de Forge 1.20.1: NeoForge 1.20.1 es un fork de Forge y debería cargarlo; no se ha probado."
    return None


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
        return [f"{_sin_mod(instancia)} El texto del código Java seguirá en inglés."]
    lineas = [f"Hay mod de apoyo para esta instancia ({destino})."]
    nota = _nota_de_compatibilidad(instancia)
    if nota:
        lineas.append(nota)
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
        raise ValueError(f"{_sin_mod(instancia)} El texto escrito en el código de los mods seguirá en inglés.")
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

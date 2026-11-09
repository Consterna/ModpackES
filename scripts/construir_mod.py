"""Compila el mod de apoyo (ModpackES Runtime) y deja el jar donde la aplicación lo busca.

Uso:  uv run python scripts/construir_mod.py [<proyecto de mod-runtime/> | todos] [--sin-pruebas]

Sin nombre compila todos. Cada uno necesita su JDK (Forge: 17; NeoForge y Fabric: 21, y Fabric 26.x: 25) y su
Gradle, que se toman de JAVA_HOME (o JAVA_HOME_<versión>_X64) y de `.herramientas/` si existen, y acceso a
internet la primera vez, para bajar el loader y Minecraft. El resultado queda en
`src/traductor_es/recursos/mods/`, que Git ignora. En GitHub Actions el jar lo construye el mismo comando
(`.github/workflows/ci.yml`).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "src" / "traductor_es" / "recursos" / "mods"
#: proyecto → (versión de Java, versión de Gradle) que pide su compilación
PROYECTOS = {
    "forge-1.19.2": (17, "8.8"),
    "forge-1.20.1": (17, "8.8"),
    "neoforge-1.21.1": (21, "9.2.1"),
    "neoforge-1.21.4": (21, "9.2.1"),
    "neoforge-1.21.5": (21, "9.2.1"),
    "neoforge-1.21.11": (21, "9.2.1"),
    "fabric-1.19.4": (21, "9.8.2"),
    "fabric-1.20.1": (21, "9.8.2"),
    "fabric-1.20.4": (21, "9.8.2"),
    "fabric-1.20.6": (21, "9.8.2"),
    "fabric-1.21.1": (21, "9.8.2"),
    "fabric-1.21.4": (21, "9.8.2"),
    "fabric-1.21.5": (21, "9.8.2"),
    "fabric-1.21.11": (21, "9.8.2"),
    "fabric-26.1": (25, "9.8.2"),
}


def _herramientas() -> Path:
    """`.herramientas` de este repositorio o, si se trabaja en un worktree, la del repositorio principal."""
    for carpeta in (RAIZ, *RAIZ.parents):
        if (carpeta / ".herramientas").is_dir():
            return carpeta / ".herramientas"
    return RAIZ / ".herramientas"


HERRAMIENTAS = _herramientas()


def _jdk(version: int) -> Path:
    ejecutable = "java.exe" if os.name == "nt" else "java"
    candidatos = [Path(os.environ[v]) for v in ("JAVA_HOME", f"JAVA_HOME_{version}_X64") if os.environ.get(v)]
    candidatos += sorted(HERRAMIENTAS.glob(f"jdk-{version}*"))
    for c in candidatos:
        if (c / "bin" / ejecutable).is_file() and f'"{version}.' in _version_de_java(c / "bin" / ejecutable):
            return c
    raise SystemExit(f"No encuentro un JDK {version}: define JAVA_HOME o ponlo en .herramientas/jdk-{version}*.")


def _version_de_java(java: Path) -> str:
    return subprocess.run([str(java), "-version"], capture_output=True, text=True, check=False).stderr


def _gradle(proyecto: Path) -> list[str]:
    envoltorio = proyecto / ("gradlew.bat" if os.name == "nt" else "gradlew")
    local = (
        HERRAMIENTAS / f"gradle-{PROYECTOS[proyecto.name][1]}" / "bin" / ("gradle.bat" if os.name == "nt" else "gradle")
    )
    return [str(local)] if local.is_file() else [str(envoltorio)]  # el de .herramientas si está; si no, el del proyecto


def construir(nombre: str, sin_pruebas: bool, propiedades: list[str] | None = None) -> int:
    proyecto = RAIZ / "mod-runtime" / nombre
    jdk = _jdk(PROYECTOS[nombre][0])
    entorno = {**os.environ, "JAVA_HOME": str(jdk), "PATH": str(jdk / "bin") + os.pathsep + os.environ["PATH"]}
    hosts = HERRAMIENTAS / "hosts-java.txt"
    if hosts.is_file():
        # Solo para Java y solo en esta compilación: ayuda si el DNS del equipo falla con algunos servidores. Va en
        # JAVA_TOOL_OPTIONS porque así llega a todos los Java que se lanzan (cliente de Gradle, su proceso y ayudantes).
        entorno["JAVA_TOOL_OPTIONS"] = f"{entorno.get('JAVA_TOOL_OPTIONS', '')} -Djdk.net.hosts.file={hosts}".strip()
    if HERRAMIENTAS.is_dir():  # la caché de Gradle y del loader queda junto al proyecto y no en la carpeta del usuario
        entorno.setdefault("GRADLE_USER_HOME", str(HERRAMIENTAS / "gradle-home"))
    # Con propiedades (`-P`) solo se comprueba que el mismo código compila y pasa sus pruebas con otra versión
    # de Minecraft: no se toca ningún jar.
    orden = [*_gradle(proyecto), "test" if propiedades else "build", "--no-daemon", "--console=plain"]
    orden += [f"-P{p}" for p in propiedades or []]
    if sin_pruebas:
        orden += ["-x", "test"]
    codigo = subprocess.run(orden, cwd=proyecto, env=entorno, check=False).returncode
    if codigo or propiedades:
        return codigo
    jars = sorted(
        j
        for j in (proyecto / "build" / "libs").glob("modpackes_runtime-*.jar")
        if not j.stem.endswith(("-sources", "-dev"))
    )
    if not jars:
        print(f"{nombre}: la compilación terminó pero no hay jar en build/libs.", file=sys.stderr)
        return 1
    DESTINO.mkdir(parents=True, exist_ok=True)
    for viejo in DESTINO.glob(f"modpackes_runtime-{nombre}-*.jar"):
        viejo.unlink()
    final = DESTINO / jars[-1].name
    shutil.copyfile(jars[-1], final)
    print(f"Mod de apoyo listo: {final}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proyecto", nargs="?", default="todos", choices=[*PROYECTOS, "todos"])
    ap.add_argument("--sin-pruebas", action="store_true", help="compila sin correr las pruebas de Java")
    ap.add_argument(
        "--propiedad", action="append", metavar="CLAVE=VALOR", default=[],
        help="prueba el mismo código con otra versión (p. ej. minecraft_version=1.21.8); no genera jar",
    )  # fmt: skip
    args = ap.parse_args()
    elegidos = list(PROYECTOS) if args.proyecto == "todos" else [args.proyecto]
    for nombre in elegidos:
        if (codigo := construir(nombre, args.sin_pruebas, args.propiedad)) != 0:
            return codigo
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compila el mod de apoyo (ModpackES Runtime) y deja el jar donde la aplicación lo busca.

Uso:  uv run python scripts/construir_mod.py [--sin-pruebas]

Necesita un JDK 17 (la variable JAVA_HOME, o la carpeta `.herramientas/jdk-17*` si existe) y acceso a internet la
primera vez, para bajar Gradle, Forge y Minecraft. El resultado queda en `src/traductor_es/recursos/mods/`, que Git
ignora.
En GitHub Actions el jar lo construye el mismo comando (`.github/workflows/release.yml`).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROYECTO = RAIZ / "mod-runtime" / "forge-1.20.1"
DESTINO = RAIZ / "src" / "traductor_es" / "recursos" / "mods"


def _herramientas() -> Path:
    """`.herramientas` de este repositorio o, si se trabaja en un worktree, la del repositorio principal."""
    for carpeta in (RAIZ, *RAIZ.parents):
        if (carpeta / ".herramientas").is_dir():
            return carpeta / ".herramientas"
    return RAIZ / ".herramientas"


HERRAMIENTAS = _herramientas()


def _jdk17() -> Path:
    candidatos = [Path(os.environ["JAVA_HOME"])] if os.environ.get("JAVA_HOME") else []
    candidatos += sorted(HERRAMIENTAS.glob("jdk-17*"))
    for c in candidatos:
        if (c / "bin" / ("java.exe" if os.name == "nt" else "java")).is_file():
            return c
    raise SystemExit("No encuentro un JDK 17: define JAVA_HOME o ponlo en .herramientas/jdk-17*.")


def _gradle() -> list[str]:
    envoltorio = PROYECTO / ("gradlew.bat" if os.name == "nt" else "gradlew")
    local = sorted(HERRAMIENTAS.glob("gradle-*/bin/gradle" + (".bat" if os.name == "nt" else "")))
    return [str(local[-1])] if local else [str(envoltorio)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-pruebas", action="store_true", help="compila sin correr las pruebas de Java")
    args = ap.parse_args()
    jdk = _jdk17()
    entorno = {**os.environ, "JAVA_HOME": str(jdk), "PATH": str(jdk / "bin") + os.pathsep + os.environ["PATH"]}
    if HERRAMIENTAS.is_dir():  # la caché de Gradle y de Forge queda junto al proyecto y no en la carpeta del usuario
        entorno.setdefault("GRADLE_USER_HOME", str(HERRAMIENTAS / "gradle-home"))
    orden = [*_gradle(), "build", "--no-daemon", "--console=plain"]
    if args.sin_pruebas:
        orden += ["-x", "test"]
    codigo = subprocess.run(orden, cwd=PROYECTO, env=entorno, check=False).returncode
    if codigo:
        return codigo
    jars = sorted((PROYECTO / "build" / "libs").glob("modpackes_runtime-*.jar"))
    if not jars:
        print("La compilación terminó pero no hay jar en build/libs.", file=sys.stderr)
        return 1
    DESTINO.mkdir(parents=True, exist_ok=True)
    for viejo in DESTINO.glob("modpackes_runtime-*.jar"):
        viejo.unlink()
    final = DESTINO / jars[-1].name
    shutil.copyfile(jars[-1], final)
    print(f"Mod de apoyo listo: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validador con los parsers reales del juego (Gson y el SNBT de FTB Library), ejecutados con Java."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

Modo = Literal["json", "snbt"]
_FUENTE = "ValidadorTraductor.java"


@dataclass(frozen=True, slots=True)
class ResultadoJava:
    ruta: Path
    ok: bool
    detalle: str  #: forma canónica si ok, motivo del error si no


def _ejecutable(carpeta: Path, nombre: str) -> Path | None:
    for candidato in (carpeta / "bin" / f"{nombre}.exe", carpeta / "bin" / nombre):
        if candidato.is_file():
            return candidato
    return None


def carpetas_de_runtimes() -> list[Path]:
    """Runtimes de Java que traen los lanzadores de Minecraft más comunes (un nivel de profundidad)."""
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    bases = [
        appdata / "PrismLauncher" / "java",
        appdata / "ModrinthApp" / "meta" / "java_versions",
        appdata / ".minecraft" / "runtime",
        Path.home() / "curseforge" / "minecraft" / "Install" / "runtime",
    ]
    carpetas: list[Path] = []
    for base in bases:
        if base.is_dir():
            carpetas.extend(p for p in base.iterdir() if p.is_dir())
    return carpetas


def version_java(carpeta: Path) -> int:
    """Versión mayor del JDK según su archivo `release` (0 si no se sabe). Java 8 se reporta como 1.8 → 8."""
    try:
        texto = (carpeta / "release").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    m = re.search(r'JAVA_VERSION="(\d+)(?:\.(\d+))?', texto)
    if not m:
        return 0
    mayor = int(m.group(1))
    return int(m.group(2) or 0) if mayor == 1 else mayor


VERSION_MINIMA = 17  #: el validador usa sintaxis de Java 16+, y FTB Library 1.20 necesita 17


def buscar_jdk(extra: Iterable[Path] = ()) -> Path | None:
    """El JDK más nuevo (17 o superior) entre JAVA_HOME, lo que pase el usuario, PATH y los lanzadores."""
    candidatos: list[Path] = []
    if os.environ.get("JAVA_HOME"):
        candidatos.append(Path(os.environ["JAVA_HOME"]))
    candidatos.extend(extra)
    javac = shutil.which("javac")
    if javac:
        candidatos.append(Path(javac).resolve().parent.parent)
    candidatos.extend(carpetas_de_runtimes())
    validos = [
        (version_java(c), c)
        for c in candidatos
        if _ejecutable(c, "java") and _ejecutable(c, "javac") and version_java(c) >= VERSION_MINIMA
    ]
    return max(validos, key=lambda par: par[0])[1] if validos else None


def biblioteca_mas_nueva(raiz: Path, patron: str) -> Path | None:
    """El jar de mayor versión cuyo nombre cumple el patrón, dentro de una carpeta `libraries`."""
    regex = re.compile(patron)
    encontrados = [p for p in raiz.rglob("*.jar") if regex.fullmatch(p.name)] if raiz.is_dir() else []

    def version(p: Path) -> tuple[int, ...]:
        return tuple(int(x) for x in re.findall(r"\d+", p.stem))

    return max(encontrados, key=version, default=None)


class ValidadorJava:
    def __init__(self, jdk: Path, carpeta_clases: Path) -> None:
        java, javac = _ejecutable(jdk, "java"), _ejecutable(jdk, "javac")
        if java is None or javac is None:
            raise FileNotFoundError(f"No hay java/javac en {jdk}")
        self.java, self.javac = java, javac
        self.clases = carpeta_clases

    def compilar(self) -> None:
        """Compila el validador si no está compilado o si la fuente cambió."""
        fuente = resources.files("traductor_es.validacion").joinpath(_FUENTE)
        codigo = fuente.read_text(encoding="utf-8")
        self.clases.mkdir(parents=True, exist_ok=True)
        copia = self.clases / _FUENTE
        clase = self.clases / "ValidadorTraductor.class"
        if clase.exists() and copia.exists() and copia.read_text(encoding="utf-8") == codigo:
            return
        copia.write_text(codigo, encoding="utf-8")
        proc = subprocess.run(
            [str(self.javac), "-encoding", "UTF-8", "-d", str(self.clases), str(copia)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"No se pudo compilar el validador Java:\n{proc.stderr}")

    def validar(self, modo: Modo, archivos: Sequence[Path], classpath: Sequence[Path]) -> list[ResultadoJava]:
        self.compilar()
        cp = os.pathsep.join([str(self.clases), *map(str, classpath)])
        if not archivos:
            return []
        # Las rutas van por la entrada estándar en UTF-8 (sin límite de largo ni problemas de página de códigos).
        proc = subprocess.run(
            [str(self.java), "-Dfile.encoding=UTF-8", "-Dlog4j2.level=OFF", "-cp", cp, "ValidadorTraductor", modo],
            input="\n".join(map(str, archivos)) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # la JVM escribe sus propios errores en la página de códigos de la consola
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"El validador Java falló:\n{proc.stderr[-2000:]}")
        return _interpretar(proc.stdout)


def _des_escapar(s: str) -> str:
    return re.sub(r"\\([\\tnr])", lambda m: {"\\": "\\", "t": "\t", "n": "\n", "r": "\r"}[m.group(1)], s)


def _interpretar(salida: str) -> list[ResultadoJava]:
    resultados: list[ResultadoJava] = []
    for linea in salida.splitlines():
        partes = linea.split("\t", 2)
        if len(partes) == 3 and partes[0] in ("OK", "ERROR"):
            resultados.append(ResultadoJava(Path(partes[1]), partes[0] == "OK", _des_escapar(partes[2])))
    return resultados

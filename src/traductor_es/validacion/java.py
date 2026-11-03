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
_LOTE = 150  # archivos por llamada, para no pasar el límite de la línea de comandos de Windows


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
    """Runtimes de Java que traen los lanzadores de Minecraft más comunes."""
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    bases = [
        appdata / "PrismLauncher" / "java",
        appdata / "ModrinthApp" / "meta" / "java_versions",
        Path.home() / "curseforge" / "minecraft" / "Install" / "runtime",
        local / "Packages",  # launcher oficial de la tienda (rara vez trae javac)
    ]
    carpetas: list[Path] = []
    for base in bases:
        if base.is_dir():
            carpetas.extend(sorted((p for p in base.iterdir() if p.is_dir()), reverse=True))
    return carpetas


def buscar_jdk(extra: Iterable[Path] = ()) -> Path | None:
    """Primera carpeta con java y javac: JAVA_HOME, lo que pase el usuario, PATH y los runtimes de los lanzadores."""
    candidatos: list[Path] = []
    if os.environ.get("JAVA_HOME"):
        candidatos.append(Path(os.environ["JAVA_HOME"]))
    candidatos.extend(extra)
    javac = shutil.which("javac")
    if javac:
        candidatos.append(Path(javac).resolve().parent.parent)
    candidatos.extend(carpetas_de_runtimes())
    for c in candidatos:
        if _ejecutable(c, "java") and _ejecutable(c, "javac"):
            return c
    return None


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
        resultados: list[ResultadoJava] = []
        for i in range(0, len(archivos), _LOTE):
            grupo = archivos[i : i + _LOTE]
            proc = subprocess.run(
                [
                    str(self.java),
                    "-Dstdout.encoding=UTF-8",  # Java 18+
                    "-Dsun.stdout.encoding=UTF-8",  # Java 17
                    "-Dfile.encoding=UTF-8",
                    "-Dlog4j2.level=OFF",
                    "-cp",
                    cp,
                    "ValidadorTraductor",
                    modo,
                    *map(str, grupo),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"El validador Java falló:\n{proc.stderr[-2000:]}")
            resultados.extend(_interpretar(proc.stdout))
        return resultados


def _des_escapar(s: str) -> str:
    return re.sub(r"\\([\\tnr])", lambda m: {"\\": "\\", "t": "\t", "n": "\n", "r": "\r"}[m.group(1)], s)


def _interpretar(salida: str) -> list[ResultadoJava]:
    resultados: list[ResultadoJava] = []
    for linea in salida.splitlines():
        partes = linea.split("\t", 2)
        if len(partes) == 3 and partes[0] in ("OK", "ERROR"):
            resultados.append(ResultadoJava(Path(partes[1]), partes[0] == "OK", _des_escapar(partes[2])))
    return resultados

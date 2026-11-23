"""Construye ModpackES con PyInstaller.

Uso:  uv run python scripts/construir_exe.py               → dist/ModpackES-portable.zip (carpeta ModpackES/)
      uv run python scripts/construir_exe.py --instalador  → dist/ModpackES-instalador.exe (Inno Setup)
      --reusar: usa la carpeta ya construida en build/onedir (el CI arma así los dos con el mismo programa)

Los dos salen de la versión en carpeta («onedir»), que arranca más rápido porque no se descomprime en cada inicio.
No hay un .exe suelto: un .exe que se abre desde Descargas carga las DLL que alguien deje en esa carpeta (H-016).
El instalador lo pone en su carpeta de programas, y el zip en la carpeta donde se extrae.
El instalador necesita Inno Setup 6.7 o superior (ISCC.exe); la variable ISCC puede indicar dónde está.
Hace falta Python 3.13.16 o superior: las anteriores tienen una bomba de memoria en `zipfile` (CVE-2026-15310).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PySide6.QtGui import QImage

from traductor_es import AUTOR, NOMBRE, REPOSITORIO, __version__

RAIZ = Path(__file__).resolve().parent.parent
BUILD = RAIZ / "build"
DIST = RAIZ / "dist"
ISS = RAIZ / "instalador" / "ModpackES.iss"
ONEDIR = BUILD / "onedir"
PORTABLE = DIST / f"{NOMBRE}-portable.zip"
_ISCC_HABITUALES = (
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
)

#: Propiedades del archivo que muestra Windows (clic derecho → Propiedades → Detalles).
VERSION_WINDOWS = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={tupla}, prodvers={tupla}),
  kids=[
    StringFileInfo([StringTable('040a04b0', [
      StringStruct('CompanyName', '{autor}'),
      StringStruct('FileDescription', '{nombre}: traductor de modpacks de Minecraft al español'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{nombre}'),
      StringStruct('LegalCopyright', '© 2026 {autor}. Licencia GPL-3.0-or-later'),
      StringStruct('OriginalFilename', '{nombre}.exe'),
      StringStruct('ProductName', '{nombre}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('Comments', '{repositorio}')])]),
    VarFileInfo([VarStruct('Translation', [0x040a, 1200])])
  ]
)
"""


def _preparar() -> tuple[Path, Path]:
    """El ícono .ico y el archivo de versión de Windows, en build/."""
    BUILD.mkdir(exist_ok=True)
    icono = BUILD / "icono.ico"
    if not QImage(str(RAIZ / "src" / "traductor_es" / "ui" / "icono.png")).save(str(icono)):
        raise SystemExit("No pude convertir el ícono a .ico")
    numeros = (*(int(n) for n in __version__.split(".")), 0)
    version = BUILD / "version_windows.txt"
    version.write_text(
        VERSION_WINDOWS.format(tupla=numeros, autor=AUTOR, nombre=NOMBRE, version=__version__, repositorio=REPOSITORIO),
        encoding="utf-8",
    )
    return icono, version


def _pyinstaller(modo: str, destino: Path, trabajo: Path, icono: Path, version: Path) -> int:
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", modo, "--windowed",
        "--name", NOMBRE,
        "--icon", str(icono),
        "--version-file", str(version),
        "--collect-data", "traductor_es",  # el validador Java (ValidadorTraductor.java) y el ícono
        "--hidden-import", "keyring.backends.Windows",
        "--exclude-module", "tkinter",
        "--distpath", str(destino), "--workpath", str(trabajo), "--specpath", str(trabajo),
        str(RAIZ / "scripts" / "lanzador_ventana.py"),
    ]  # fmt: skip
    return subprocess.run(comando, cwd=RAIZ, check=False).returncode


def buscar_iscc() -> Path | None:
    propio = os.environ.get("ISCC")
    candidatos = [Path(propio)] if propio else []
    en_path = shutil.which("iscc")
    if en_path:
        candidatos.append(Path(en_path))
    return next((c for c in [*candidatos, *_ISCC_HABITUALES] if c.is_file()), None)


def onedir(icono: Path, version: Path, reusar: bool = False) -> int:
    """La carpeta del programa en build/onedir/ModpackES (la que llevan el zip y el instalador)."""
    if reusar and (ONEDIR / NOMBRE / f"{NOMBRE}.exe").is_file():
        return 0
    shutil.rmtree(ONEDIR, ignore_errors=True)
    return _pyinstaller("--onedir", ONEDIR, BUILD / "onedir_trabajo", icono, version)


def comprimir(carpeta: Path, destino: Path) -> Path:
    """El zip del portátil: una sola carpeta `ModpackES/` dentro, con las entradas en orden."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".tmp")
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for ruta in sorted(p for p in carpeta.rglob("*") if p.is_file()):
            z.write(ruta, f"{NOMBRE}/{ruta.relative_to(carpeta).as_posix()}")
    temporal.replace(destino)
    return destino


def portable(icono: Path, version: Path, reusar: bool = False) -> int:
    codigo = onedir(icono, version, reusar)
    if codigo:
        return codigo
    print(f"Portable: {comprimir(ONEDIR / NOMBRE, PORTABLE)}")
    return 0


def instalador(icono: Path, version: Path, reusar: bool = False) -> int:
    iscc = buscar_iscc()
    if iscc is None:
        print("No encuentro Inno Setup (ISCC.exe). Instálalo o indica su ruta en la variable ISCC.")
        return 2
    codigo = onedir(icono, version, reusar)
    if codigo:
        return codigo
    comando = [
        str(iscc), "/Qp",
        f"/DVersion={__version__}", f"/DOrigen={ONEDIR / NOMBRE}", f"/DSalida={DIST}",
        f"/DIcono={icono}", f"/DLicencia={RAIZ / 'LICENSE'}",
        str(ISS),
    ]  # fmt: skip
    return subprocess.run(comando, cwd=RAIZ, check=False).returncode


#: La primera 3.13 sin CVE-2026-15310 (bomba de memoria en `zipfile` con miembros bzip2, LZMA o Zstandard)
PYTHON_MINIMO = (3, 13, 16)


def main(argv: list[str] | None = None) -> int:
    if sys.version_info[:3] < PYTHON_MINIMO:
        minimo = ".".join(map(str, PYTHON_MINIMO))
        print(f"Hace falta Python {minimo} o superior para construir el programa (este es {sys.version.split()[0]}).")
        return 2
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instalador", action="store_true", help="construir el instalador en vez del portable")
    ap.add_argument("--reusar", action="store_true", help="usar la carpeta ya construida en build/onedir")
    args = ap.parse_args(argv)
    icono, version = _preparar()
    if args.instalador:
        return instalador(icono, version, args.reusar)
    return portable(icono, version, args.reusar)


if __name__ == "__main__":
    raise SystemExit(main())

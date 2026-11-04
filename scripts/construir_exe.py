"""Construye ModpackES con PyInstaller.

Uso:  uv run python scripts/construir_exe.py               → dist/ModpackES.exe (portable, un solo archivo)
      uv run python scripts/construir_exe.py --instalador  → dist/ModpackES-instalador.exe (Inno Setup)

El instalador usa la versión en carpeta («onedir»), que arranca más rápido porque no se descomprime en cada
inicio. Necesita Inno Setup 6.3 o superior (ISCC.exe); la variable ISCC puede indicar dónde está.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtGui import QImage

from traductor_es import AUTOR, NOMBRE, REPOSITORIO, __version__

RAIZ = Path(__file__).resolve().parent.parent
BUILD = RAIZ / "build"
DIST = RAIZ / "dist"
ISS = RAIZ / "instalador" / "ModpackES.iss"
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


def instalador(icono: Path, version: Path) -> int:
    iscc = buscar_iscc()
    if iscc is None:
        print("No encuentro Inno Setup (ISCC.exe). Instálalo o indica su ruta en la variable ISCC.")
        return 2
    carpeta = BUILD / "onedir"
    shutil.rmtree(carpeta, ignore_errors=True)
    codigo = _pyinstaller("--onedir", carpeta, BUILD / "onedir_trabajo", icono, version)
    if codigo:
        return codigo
    comando = [
        str(iscc), "/Qp",
        f"/DVersion={__version__}", f"/DOrigen={carpeta / NOMBRE}", f"/DSalida={DIST}",
        f"/DIcono={icono}", f"/DLicencia={RAIZ / 'LICENSE'}",
        str(ISS),
    ]  # fmt: skip
    return subprocess.run(comando, cwd=RAIZ, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instalador", action="store_true", help="construir el instalador en vez del portable")
    args = ap.parse_args(argv)
    icono, version = _preparar()
    if args.instalador:
        return instalador(icono, version)
    return _pyinstaller("--onefile", DIST, BUILD, icono, version)


if __name__ == "__main__":
    raise SystemExit(main())

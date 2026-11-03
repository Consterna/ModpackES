"""Construye dist/ModpackES.exe (un solo archivo, sin consola) con PyInstaller.

Uso:  uv run python scripts/construir_exe.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtGui import QImage

from traductor_es import AUTOR, NOMBRE, REPOSITORIO, __version__

RAIZ = Path(__file__).resolve().parent.parent
BUILD = RAIZ / "build"

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


def main() -> int:
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
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NOMBRE,
        "--icon", str(icono),
        "--version-file", str(version),
        "--collect-data", "traductor_es",  # el validador Java (ValidadorTraductor.java) y el ícono
        "--hidden-import", "keyring.backends.Windows",
        "--exclude-module", "tkinter",
        "--distpath", str(RAIZ / "dist"), "--workpath", str(BUILD), "--specpath", str(BUILD),
        str(RAIZ / "scripts" / "lanzador_ventana.py"),
    ]  # fmt: skip
    return subprocess.run(comando, cwd=RAIZ, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

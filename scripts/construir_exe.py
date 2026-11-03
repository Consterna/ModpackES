"""Construye dist/TraductorModpacks.exe (un solo archivo, sin consola) con PyInstaller.

Uso:  uv run python scripts/construir_exe.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "TraductorModpacks",
        "--collect-data", "traductor_es",  # el validador Java (ValidadorTraductor.java)
        "--hidden-import", "keyring.backends.Windows",
        "--exclude-module", "tkinter",
        "--distpath", str(RAIZ / "dist"), "--workpath", str(RAIZ / "build"), "--specpath", str(RAIZ / "build"),
        str(RAIZ / "scripts" / "lanzador_ventana.py"),
    ]  # fmt: skip
    return subprocess.run(comando, cwd=RAIZ, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

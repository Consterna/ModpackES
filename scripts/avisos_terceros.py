"""Genera THIRD-PARTY-NOTICES.md con las bibliotecas que van dentro del .exe y sus licencias.

Uso:  uv run python scripts/avisos_terceros.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "THIRD-PARTY-NOTICES.md"

ENCABEZADO = """# Avisos de terceros

ModpackES se distribuye bajo la licencia GPL-3.0-or-later (ver `LICENSE`). El ejecutable incluye las
bibliotecas de abajo, cada una con su propia licencia. Sus textos completos vienen en el paquete de cada
proyecto y en su página.

Qt for Python (PySide6 y Shiboken6) se ofrece bajo LGPL-3.0, GPL-2.0 o GPL-3.0; ModpackES la usa bajo la
GPL-3.0, compatible con su propia licencia, y todo su código fuente está publicado. Como Qt se usa bajo la
GPL-3.0 (no «o posterior»), el programa completo se distribuye en la práctica bajo la GPL-3.0. Qt es © The Qt
Company Ltd. y otros colaboradores.

## Código fuente

El código de ModpackES está en https://github.com/Consterna/ModpackES (la etiqueta `v<versión>` de cada versión).
El de las bibliotecas que van dentro del programa, sin modificar:

- PySide6 y Shiboken6 {pyside}: https://download.qt.io/official_releases/QtForPython/pyside6/ (y el sdist en
  https://pypi.org/project/PySide6/{pyside}/).
- Qt {qt}: https://download.qt.io/official_releases/qt/
- Python {python}: https://www.python.org/downloads/source/
- El cargador de PyInstaller (GPL-2.0 con «Bootloader Exception»): https://github.com/pyinstaller/pyinstaller
- Las demás, en la página de cada proyecto de la tabla.

Los íconos de la interfaz son de [Lucide](https://lucide.dev) 1.60.0 (licencia ISC; los derivados de Feather,
con licencia MIT). El texto completo de ambas licencias va en `src/traductor_es/ui/iconos/LICENSE.txt`.

ModpackES no está afiliado a Mojang Studios, Microsoft ni Google. Minecraft es una marca de Mojang
Studios. Gemini es una marca de Google LLC.

## Bibliotecas

| Biblioteca | Versión | Licencia | Proyecto |
|---|---|---|---|
"""


def _paquetes() -> list[tuple[str, str]]:
    salida = subprocess.run(
        ["uv", "export", "--no-dev", "--no-hashes", "--no-emit-project", "--format", "requirements-txt"],
        cwd=RAIZ, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    paquetes: list[tuple[str, str]] = []
    for linea in salida.splitlines():
        m = re.match(r"([A-Za-z0-9_.-]+)==([^\s;]+)", linea.strip())
        if m:
            paquetes.append((m[1], m[2]))
    return paquetes


def _licencia(datos: metadata.PackageMetadata) -> str:
    expresion = datos.get("License-Expression")
    if expresion:
        return expresion
    clasificadores = [c.split("::")[-1].strip() for c in datos.get_all("Classifier") or [] if c.startswith("License")]
    if clasificadores:
        return ", ".join(clasificadores)
    texto = (datos.get("License") or "").strip()
    return texto.splitlines()[0][:60] if texto else "ver el proyecto"


def _pagina(datos: metadata.PackageMetadata, nombre: str) -> str:
    for url in datos.get_all("Project-URL") or []:
        etiqueta, _, enlace = url.partition(",")
        if etiqueta.strip().lower() in {"homepage", "source", "source code", "repository", "github"}:
            return enlace.strip()
    return datos.get("Home-page") or f"https://pypi.org/project/{nombre}/"


def main() -> int:
    python = ".".join(str(n) for n in sys.version_info[:3])
    filas = [f"| Python (intérprete) | {python} | PSF-2.0 | https://www.python.org/ |"]
    for nombre, version in _paquetes():
        try:
            datos = metadata.metadata(nombre)
        except metadata.PackageNotFoundError:
            continue  # solo se instala en otros sistemas (p. ej. secretstorage en Linux): no va en el .exe
        filas.append(f"| {nombre} | {version} | {_licencia(datos)} | {_pagina(datos, nombre)} |")
    pyside = metadata.version("pyside6-essentials")
    encabezado = ENCABEZADO.format(pyside=pyside, qt=".".join(pyside.split(".")[:3]), python=python)
    DESTINO.write_text(encabezado + "\n".join(filas) + "\n", encoding="utf-8", newline="\n")
    print(f"{DESTINO} ({len(filas)} bibliotecas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""El control de versión de Python al construir el programa, por rama (CVE-2026-15310 se corrigió en 3.13.16,
3.14.8 y 3.15.0)."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest


def _construir() -> types.ModuleType:
    ruta = Path(__file__).resolve().parent.parent / "scripts" / "construir_exe.py"
    spec = importlib.util.spec_from_file_location("construir_exe", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize(
    ("version", "falta"),
    [
        ((3, 13, 15), "3.13.16"),
        ((3, 13, 16), None),
        ((3, 14, 0), "3.14.8"),
        ((3, 14, 7), "3.14.8"),
        ((3, 14, 8), None),
        ((3, 15, 0), None),
        ((3, 12, 30), "3.13.16"),
    ],
)
def test_python_seguro_por_rama(version: tuple[int, int, int], falta: str | None) -> None:
    assert _construir().python_seguro(version) == falta

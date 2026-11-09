"""Archivos de idioma reales de mods de licencia libre (scripts/descargar_lang.py), de 1.7.10 a 1.21."""

from __future__ import annotations

from pathlib import Path

import pytest

from traductor_es.formatos import lang_json, lang_legacy

from .conftest import DESCARGAS

pytestmark = pytest.mark.corpus

INGLES = sorted(DESCARGAS.glob("*/langs/*/assets/*/lang/en_[uU][sS].*")) if DESCARGAS.is_dir() else []


def _leer(ruta: Path) -> dict[str, str]:
    modulo = lang_json if ruta.suffix == ".json" else lang_legacy
    return modulo.leer(ruta.read_bytes())


@pytest.mark.skipif(not INGLES, reason="Falta el corpus de idiomas (uv run python scripts/descargar_lang.py)")
@pytest.mark.parametrize("ruta", INGLES, ids=lambda r: f"{r.parts[-6]}/{r.parts[-5][:30]}/{r.parts[-3]}")
def test_el_ingles_real_se_lee_y_se_reescribe_igual(ruta: Path) -> None:
    textos = _leer(ruta)
    modulo = lang_json if ruta.suffix == ".json" else lang_legacy
    assert textos
    assert modulo.leer(modulo.escribir(textos)) == textos


@pytest.mark.skipif(not INGLES, reason="Falta el corpus de idiomas")
def test_hay_ejemplos_de_los_dos_formatos() -> None:
    assert {r.suffix for r in INGLES} >= {".json", ".lang"}

"""El análisis completo sobre cada instancia real del PC: funciona y no escribe nada en ella."""

from __future__ import annotations

from pathlib import Path

import pytest

from traductor_es.fuentes.lanzadores import InstanciaEncontrada, buscar
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

pytestmark = pytest.mark.corpus


def _fechas(juego: Path) -> dict[Path, int]:
    carpetas = [juego / d for d in ("mods", "config", "resourcepacks", "kubejs", "global_packs", "patchouli_books")]
    fechas = {p: p.stat().st_mtime_ns for c in carpetas if c.is_dir() for p in c.rglob("*") if p.is_file()}
    for extra in (juego / "options.txt", juego / "traductor_es"):
        if extra.exists():
            fechas[extra] = extra.stat().st_mtime_ns
    return fechas


@pytest.mark.parametrize("encontrada", buscar(), ids=lambda e: f"{e.lanzador}:{e.nombre}")
def test_analisis_real_sin_escribir(encontrada: InstanciaEncontrada) -> None:
    antes = _fechas(encontrada.juego)
    with Memoria(":memory:") as memoria, Proceso(encontrada.juego, Simulador(), memoria=memoria) as p:
        informe = p.analizar()
    assert informe.costo("gemini-3.8-flash", True) is not None
    assert all(m.a_traducir <= m.textos for m in informe.modulos)
    assert _fechas(encontrada.juego) == antes

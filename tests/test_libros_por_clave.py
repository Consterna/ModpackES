"""Libros guía que viven en los archivos de idioma (Patchouli con `i18n`, Modonomicon): se traducen como libro."""

from __future__ import annotations

from pathlib import Path

import pytest

from traductor_es.fuentes import vanilla
from traductor_es.modulos.mods import AMBITO_LIBRO, es_clave_de_libro
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

from . import fabrica

_TEXTOS = {
    "item.m.wrench": "Wrench",
    "gui.m.mode": "Mode",
    "m.book.entry.basics.name": "The Basics",
    "m.book.entry.basics.page1": "Right-click a block with the Wrench to rotate it.",
    "m.book.entry.basics.page2": "Sneak while doing it to pick the block up.",
}


def test_que_es_una_clave_de_libro() -> None:
    assert es_clave_de_libro("occultism.book.entries.ritual.page1")
    assert es_clave_de_libro("mysticalagriculture.guide.entry.tiers")
    assert not es_clave_de_libro("item.m.guide_book")  # el nombre del objeto es interfaz
    assert not es_clave_de_libro("gui.m.book_title")
    assert not es_clave_de_libro("config.m.manual_mode")


def test_el_proceso_manda_los_libros_como_libro_y_con_vecindad(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", _TEXTOS))
    motor = Simulador()
    with Memoria(":memory:") as mem, Proceso(juego, motor, grupos=["mods"], memoria=mem) as p:
        informe = p.analizar()
        p.ejecutar(activar=False)
        assert mem.obtener("Sneak while doing it to pick the block up.", "es_mx", AMBITO_LIBRO, p.pack)
        assert mem.obtener("Wrench", "es_mx", "ui", p.pack)
    por_ambito = {e.texto: (lote.ambito, e.pista) for lote in motor.lotes_recibidos for e in lote.entradas}
    assert por_ambito["Wrench"][0] == "ui" and por_ambito["Mode"][0] == "ui"
    ambito, pista = por_ambito["Sneak while doing it to pick the block up."]
    assert ambito == AMBITO_LIBRO
    assert "dentro de «The Basics»" in pista and "viene después de «Right-click a block" in pista
    assert informe.a_traducir == len(_TEXTOS)  # el análisis cuenta los dos ámbitos

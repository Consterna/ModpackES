"""FTB Quests: lo que está dentro del objeto que pide una tarea no es texto de la misión (H-039, de la investigación
`dominio_mods.md`, D7).

Una tarea de objeto con `match_nbt` compara el NBT del objeto que entrega el jugador: si la app traduce el `title` de
un libro escrito que hay dentro, la misión ya no reconoce el libro y no se puede completar.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes import vanilla
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

from . import fabrica

CAPITULO = """{
\ttitle: "Chapter One"
\tquests: [{
\t\tid: "0A1B2C3D4E5F6071"
\t\ttitle: "Deliver the orders"
\t\tdescription: ["Bring the sealed book to the captain."]
\t\ttasks: [{
\t\t\tid: "1A1B2C3D4E5F6071"
\t\t\ttype: "item"
\t\t\ttitle: "Sealed orders"
\t\t\tmatch_nbt: true
\t\t\titem: { id: "minecraft:written_book", Count: 1b, tag: { title: "Secret Orders", author: "Captain", pages: ['{"text":"Meet at dawn"}'] } }
\t\t}]
\t\trewards: [{
\t\t\tid: "2A1B2C3D4E5F6071"
\t\t\ttype: "item"
\t\t\titem: { id: "minecraft:diamond", Count: 1b, tag: { display: { Name: '{"text":"Shiny Reward"}' } } }
\t\t}]
\t}]
}
"""


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def test_no_se_traduce_lo_que_esta_dentro_del_objeto_de_una_tarea(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "uno.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text(CAPITULO, encoding="utf-8")
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar()
    texto = capitulo.read_text(encoding="utf-8")
    assert 'title: "Secret Orders"' in texto  # el NBT que compara la tarea, intacto
    assert "author: \"Captain\"" in texto
    assert "«ES» Deliver the orders" in texto  # lo de la misión, traducido
    assert "«ES» Sealed orders" in texto  # el título propio de la tarea sí es texto de la misión
    assert "«ES» Bring the sealed book" in texto

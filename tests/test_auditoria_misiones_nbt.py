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
    assert 'author: "Captain"' in texto
    assert "«ES» Deliver the orders" in texto  # lo de la misión, traducido
    assert "«ES» Sealed orders" in texto  # el título propio de la tarea sí es texto de la misión
    assert "«ES» Bring the sealed book" in texto


LIBRO = (
    'item: { id: "minecraft:written_book", Count: 1b, tag: { title: "Secret Orders", author: "Captain", '
    'display: { Name: \'{"text":"Orders Book"}\' } } }'
)
DOS_MISIONES = f"""{{
\ttitle: "Chapter One"
\tquests: [
\t\t{{
\t\t\tid: "0A1B2C3D4E5F6071"
\t\t\ttitle: "Get the orders"
\t\t\ttasks: [{{ id: "1A1B2C3D4E5F6071", type: "checkmark" }}]
\t\t\trewards: [
\t\t\t\t{{ id: "2A1B2C3D4E5F6071", type: "item", {LIBRO} }}
\t\t\t\t{{ id: "3A1B2C3D4E5F6071", type: "item", item: {{ id: "minecraft:cake", Count: 1b, tag: {{ display: {{ Name: '{{"text":"Party Cake"}}' }} }} }} }}
\t\t\t]
\t\t}}
\t]
}}
"""
OTRO_CAPITULO = f"""{{
\ttitle: "Chapter Two"
\tquests: [{{
\t\tid: "0A1B2C3D4E5F6072"
\t\ttitle: "Deliver the orders"
\t\ttasks: [{{ id: "1A1B2C3D4E5F6072", type: "item", match_nbt: true, {LIBRO} }}]
\t}}]
}}
"""


def test_una_recompensa_que_otra_mision_pide_no_se_traduce(tmp_path: Path, memoria: Memoria) -> None:
    """Una misión da el libro y otra, en otro capítulo, lo pide con match_nbt (H-048, verificación independiente 3):
    si se traduce el de la recompensa, el libro entregado ya no coincide con el que pide la tarea."""
    juego = fabrica.prism(tmp_path, "1.20.1")
    capitulos = juego / "config" / "ftbquests" / "quests" / "chapters"
    capitulos.mkdir(parents=True)
    (capitulos / "uno.snbt").write_text(DOS_MISIONES, encoding="utf-8")
    (capitulos / "dos.snbt").write_text(OTRO_CAPITULO, encoding="utf-8")
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar()
    uno = (capitulos / "uno.snbt").read_text(encoding="utf-8")
    assert LIBRO in uno  # el libro de la recompensa, igual al que pide la tarea
    assert LIBRO in (capitulos / "dos.snbt").read_text(encoding="utf-8")
    assert "«ES» Party Cake" in uno  # una recompensa que nadie pide sí se traduce
    assert "«ES» Get the orders" in uno

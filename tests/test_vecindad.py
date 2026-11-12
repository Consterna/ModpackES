"""Contexto de vecindad: título bajo el que está cada texto y línea anterior; comparación pareada."""

from __future__ import annotations

import json
from pathlib import Path

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, Pieza, con_vecindad, quitar_vecindad, reunir_pistas
from traductor_es.modulos.misiones import FTBQuests
from traductor_es.motores.base import Entrada, Lote
from traductor_es.motores.instrucciones import sistema, usuario
from traductor_es.salida.copias import Respaldo

from . import fabrica


def _titulo(p: Pieza) -> bool:
    return p.pista.endswith("title")


def test_cada_texto_sabe_bajo_que_titulo_esta_y_que_viene_antes() -> None:
    piezas = [
        Pieza("Mining Basics", "misión: title"),
        Pieza("Dig down to find iron.", "misión: description"),
        Pieza("Then smelt it in a furnace.", "misión: description"),
        Pieza("Smelting", "misión: title"),
        Pieza("Use coal as fuel.", "misión: description"),
    ]
    r = con_vecindad(piezas, _titulo)
    assert r[0].pista == "misión: title"  # los títulos no llevan contexto
    assert r[1].pista == "misión: description · dentro de «Mining Basics»"
    assert r[2].pista == ("misión: description · dentro de «Mining Basics» · viene después de «Dig down to find iron.»")
    assert r[4].pista == "misión: description · dentro de «Smelting»"  # un título nuevo reinicia el contexto


def test_el_contexto_se_recorta() -> None:
    larga = "palabra " * 60
    r = con_vecindad([Pieza("Título", "x: title"), Pieza(larga, "x: text"), Pieza("Final", "x: text")], _titulo)
    antes = r[2].pista.split("viene después de «")[1]
    assert len(antes) <= 105 and antes.rstrip("»").endswith("…")


def test_quitar_la_vecindad_deja_la_pista_original() -> None:
    piezas = [Pieza("T", "misión: title"), Pieza("a", "misión: text"), Pieza("b", "misión: text")]
    con = con_vecindad(piezas, _titulo)
    assert quitar_vecindad(con[2].pista) == "misión: text"


def test_las_pistas_de_un_mismo_texto_se_juntan_con_su_vecindad() -> None:
    piezas = con_vecindad(
        [Pieza("A", "q: title"), Pieza("Hi", "q: text"), Pieza("B", "q: title"), Pieza("Hi", "q: text")], _titulo
    )
    pistas = reunir_pistas(piezas)
    assert "dentro de «A»" in pistas["Hi"] and "dentro de «B»" in pistas["Hi"]


def test_las_misiones_reales_llevan_la_vecindad(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "forge")
    capitulos = juego / "config" / "ftbquests" / "quests" / "chapters"
    capitulos.mkdir(parents=True)
    (capitulos / "uno.snbt").write_text(
        '{\n\ttitle: "Chapter One"\n\tquests: [{\n\t\ttitle: "First Quest"\n'
        '\t\tdescription: ["Collect ten logs from any tree.", "Then craft a table."]\n\t}]\n}\n',
        encoding="utf-8",
    )
    with Instancia(juego) as inst:
        modulo = FTBQuests(Contexto(inst, Respaldo(juego)))
        assert modulo.detectar()
        piezas = {p.texto: p.pista for p in modulo.recolectar()}
    assert "dentro de «First Quest»" in piezas["Collect ten logs from any tree."]
    assert "viene después de «Collect ten logs from any tree.»" in piezas["Then craft a table."]


def test_la_comparacion_pide_elegir_a_b_o_igual() -> None:
    lote = Lote(
        (Entrada("0", "Open the chest", "misión: text", traduccion="Abre el cofre", alternativa="Abre el baúl"),),
        "mision",
        "español",
        tarea="comparar",
    )
    assert "«A», «B» o «igual»" in sistema(lote)
    datos = json.loads(usuario(lote))
    assert datos["pares"]["0"] == {
        "original": "Open the chest",
        "a": "Abre el cofre",
        "b": "Abre el baúl",
        "contexto": "misión: text",
    }

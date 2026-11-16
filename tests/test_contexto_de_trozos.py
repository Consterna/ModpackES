"""Trozos de un componente JSON con su frase entera, y líneas que siguen en la siguiente con su continuación."""

from __future__ import annotations

from traductor_es.modulos.base import Pieza, con_vecindad, piezas_de, quitar_vecindad

_COMPONENTE = '["", {"text": "Use the "}, {"text": "Wrench", "color": "gold"}, {"text": " to rotate blocks."}]'


def test_cada_trozo_lleva_la_frase_entera() -> None:
    piezas = piezas_de(_COMPONENTE, "misión: description")
    assert [p.texto for p in piezas] == ["Use the ", "Wrench", " to rotate blocks."]
    assert all(p.pista == "misión: description · trozo de la frase «Use the Wrench to rotate blocks.»" for p in piezas)


def test_un_texto_normal_o_un_componente_de_un_trozo_no_cambia() -> None:
    assert piezas_de("Craft a Wrench", "misión: title") == [Pieza("Craft a Wrench", "misión: title")]
    assert piezas_de('{"text": "Hola"}', "x") == [Pieza("Hola", "x")]


def test_una_linea_que_no_cierra_su_frase_lleva_la_siguiente() -> None:
    piezas = [
        Pieza("The Basics", "misión: title"),
        Pieza("Right-click the block with", "misión: description"),
        Pieza("the &6Wrench&r to rotate it.", "misión: description"),
        Pieza("Then sneak.", "misión: description"),
    ]
    salida = con_vecindad(piezas, lambda p: p.pista.endswith("title"))
    assert "sigue con «the &6Wrench&r to rotate it.»" in salida[1].pista
    assert "sigue con" not in salida[2].pista  # termina en punto: la frase cierra ahí
    assert "sigue con" not in salida[3].pista  # es la última
    assert quitar_vecindad(salida[1].pista) == "misión: description"

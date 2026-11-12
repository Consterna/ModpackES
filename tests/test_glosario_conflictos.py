"""El glosario no deja que un mod imponga su traducción rara a todo el modpack."""

from __future__ import annotations

from traductor_es.nucleo.glosario import Glosario

EN = {"entity.cow": "Cow", "item.iron": "Iron Ingot"}


def test_lo_oficial_gana_a_lo_que_dice_un_mod() -> None:
    g = Glosario()
    g.agregar_pares({"entity.cow": "Cow"}, {"entity.cow": "Acechador de medianoche"}, fuente="mod_raro")
    g.agregar_pares({"entity.cow": "Cow"}, {"entity.cow": "Vaca"}, fuente="minecraft", oficial=True)
    assert g.todos()["Cow"] == "Vaca"


def test_lo_oficial_se_agrega_primero_y_nadie_lo_pisa() -> None:
    g = Glosario()
    g.agregar_pares({"entity.cow": "Cow"}, {"entity.cow": "Vaca"}, fuente="minecraft", oficial=True)
    g.agregar_pares({"entity.cow": "Cow"}, {"entity.cow": "Acechador de medianoche"}, fuente="mod_raro")
    assert g.todos()["Cow"] == "Vaca"


def test_dos_mods_que_se_contradicen_no_dejan_ningun_termino() -> None:
    g = Glosario()
    g.agregar_pares(EN, {"entity.cow": "Res", "item.iron": "Lingote de hierro"}, fuente="mod_a")
    g.agregar_pares(EN, {"entity.cow": "Bovino", "item.iron": "Lingote de hierro"}, fuente="mod_b")
    assert "Cow" not in g.todos() and "Cow" in g.en_conflicto
    assert g.todos()["Iron Ingot"] == "Lingote de hierro"  # lo que coincide se queda


def test_un_tercer_mod_no_revive_un_termino_en_conflicto() -> None:
    g = Glosario()
    g.agregar_pares(EN, {"entity.cow": "Res"}, fuente="mod_a")
    g.agregar_pares(EN, {"entity.cow": "Bovino"}, fuente="mod_b")
    g.agregar_pares(EN, {"entity.cow": "Vacuno"}, fuente="mod_c")
    assert "Cow" not in g.todos()


def test_las_variantes_de_una_misma_fuente_mandan_por_orden() -> None:
    g = Glosario()  # es_mx va antes que es_es: dentro del mismo origen no es un conflicto
    g.agregar_pares({"b.glass": "Glass"}, {"b.glass": "Vidrio"}, fuente="minecraft", oficial=True)
    g.agregar_pares({"b.glass": "Glass"}, {"b.glass": "Cristal"}, fuente="minecraft", oficial=True)
    assert g.todos()["Glass"] == "Vidrio" and not g.en_conflicto


def test_sin_fuente_sigue_mandando_lo_primero() -> None:
    g = Glosario()
    g.agregar_pares({"a": "Chest"}, {"a": "Cofre"})
    g.agregar_pares({"a": "Chest"}, {"a": "Baúl"})
    assert g.todos()["Chest"] == "Cofre"


def test_lo_que_fija_el_usuario_manda_sobre_todo() -> None:
    g = Glosario()
    g.agregar_pares({"a": "Chest"}, {"a": "Cofre"}, fuente="minecraft", oficial=True)
    g.fijar({"Chest": "Arcón"})
    assert g.todos()["Chest"] == "Arcón"

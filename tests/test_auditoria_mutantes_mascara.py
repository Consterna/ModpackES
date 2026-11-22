"""Pruebas escritas para matar los mutantes que sobrevivían en `nucleo/mascara.py` (puntaje de mutación 79,5 %)."""

from __future__ import annotations

from traductor_es.nucleo.mascara import enmascarar, pares_en_orden, posicionar_argumentos


def test_argumentos_en_el_mismo_orden_no_se_renumeran() -> None:
    m = enmascarar("%s killed %s")
    assert posicionar_argumentos("⟦0⟧ mató a ⟦1⟧", m.tokens) == (m.tokens, False)


def test_argumentos_ya_numerados_pueden_cambiar_de_orden_sin_tocarlos() -> None:
    m = enmascarar("%1$s killed %2$s")
    assert posicionar_argumentos("⟦1⟧ fue asesinado por ⟦0⟧", m.tokens) == (m.tokens, False)


def test_argumentos_sin_numero_que_cambian_de_orden_se_numeran() -> None:
    m = enmascarar("%s was slain by %s")
    assert posicionar_argumentos("⟦1⟧ fue asesinado por ⟦0⟧", m.tokens) == (("%1$s", "%2$s"), True)


def test_mezcla_de_argumentos_con_y_sin_numero_no_se_arregla() -> None:
    m = enmascarar("%1$s and %s")
    assert posicionar_argumentos("⟦1⟧ y ⟦0⟧", m.tokens) is None


def test_un_argumento_no_abre_formato_aunque_quede_despues_de_un_cierre() -> None:
    m = enmascarar("%s won§r")
    assert m.tokens == ("%s", "§r")
    assert pares_en_orden("Ganó⟦1⟧ ⟦0⟧", m.tokens) is True


def test_un_salto_de_patchouli_no_abre_formato() -> None:
    m = enmascarar("Line$(br)end$()")
    assert m.tokens == ("$(br)", "$()")
    assert pares_en_orden("Fin⟦1⟧ línea⟦0⟧", m.tokens) is True


def test_cierre_antes_de_su_apertura_se_rechaza() -> None:
    m = enmascarar("§aIron§r Sword")
    assert pares_en_orden("⟦1⟧Espada de ⟦0⟧hierro", m.tokens) is False
    assert pares_en_orden("Espada de ⟦0⟧hierro⟦1⟧", m.tokens) is True

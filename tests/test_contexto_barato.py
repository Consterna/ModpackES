"""Contexto barato: orden del archivo, pistas de interfaz con su objeto y sus vecinas, y nombres con su frase."""

from __future__ import annotations

from traductor_es.modulos.mods import pista_con_contexto, textos_del_juego
from traductor_es.motores.base import Lote
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor, con_apariciones, por_nucleo

_TEXTOS = {
    "item.m.wrench": "Wrench",
    "item.m.wrench.tooltip": "Rotates blocks",
    "tooltip.m.wrench.shift": "Sneak to dismantle",
    "gui.m.mode.left": "Left",
    "gui.m.mode.right": "Right",
    "gui.m.mode.up": "Up",
    "gui.m.title": "Wrench Settings",
}


def test_un_tooltip_lleva_el_nombre_de_su_objeto() -> None:
    assert "habla de «Wrench»" in pista_con_contexto("m", "item.m.wrench.tooltip", _TEXTOS)
    assert "habla de «Wrench»" in pista_con_contexto("m", "tooltip.m.wrench.shift", _TEXTOS)
    assert "habla de" not in pista_con_contexto("m", "item.m.wrench", _TEXTOS)  # el nombre mismo, no


def test_un_texto_corto_de_menu_lleva_sus_vecinas_del_archivo() -> None:
    pista = pista_con_contexto("m", "gui.m.mode.right", _TEXTOS)
    assert "junto a «Left», «Up»" in pista
    assert "junto a" not in pista_con_contexto("m", "gui.m.title", _TEXTOS)  # su vecina es de otro padre


def test_lo_que_ya_dice_el_juego_va_en_la_pista() -> None:
    juego = textos_del_juego(
        {"gui.done": "Done", "gui.left": "Left", "options.left": "Left", "item.minecraft.stick": "Stick"},
        {"gui.done": "Listo", "gui.left": "Izquierda", "options.left": "Izq.", "item.minecraft.stick": "Palo"},
    )
    assert juego == {"Done": "Listo"}  # «Left» tiene dos traducciones y «Stick» es un nombre: no
    assert "en el juego: «Listo»" in pista_con_contexto("m", "gui.m.done", {"gui.m.done": "Done"}, juego)


def test_las_pistas_de_textos_que_solo_difieren_en_espacios_se_juntan() -> None:
    assert por_nucleo({"Done": "gui.a", " Done ": "gui.b", "Back": ""}) == {"Done": "gui.a | gui.b"}


def test_un_nombre_se_decide_con_las_frases_donde_aparece() -> None:
    pista = con_apariciones(
        "Aviso.", "Arachnarch", ["Defeat the &4Arachnarch in its lair. Then rest.", "Arachnarch", "Nothing here"]
    )
    assert pista == "Aviso. Aparece en: «Defeat the Arachnarch in its lair.»"
    assert con_apariciones("Aviso.", "Zorp", ["Nothing"]) == "Aviso."


class _Anotador:
    nombre = "anotador"

    def __init__(self) -> None:
        self.lotes: list[Lote] = []

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.lotes.append(lote)
        return Simulador().traducir_lote(lote)


def test_los_lotes_siguen_el_orden_del_archivo() -> None:
    motor = _Anotador()
    textos = ["Zebra Saddle", "Apple Pie", "Mango Juice"]
    with Memoria(":memory:") as mem:
        Traductor(motor, mem, Glosario()).traducir(textos, "ui")
    assert [e.texto for e in motor.lotes[0].entradas] == textos

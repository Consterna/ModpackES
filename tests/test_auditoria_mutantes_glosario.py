"""Bordes del glosario (`nucleo/glosario.py`): cada prueba detecta una mutación que antes sobrevivía
(`logs/fase-03/mutacion_glosario.log`, 70,5 %)."""

from __future__ import annotations

import pytest

from traductor_es.nucleo.glosario import Glosario, parece_nombre_propio


@pytest.mark.parametrize(
    ("texto", "es_nombre"),
    [
        ("Arachnarch", True),
        ("Bronze Dungeons", True),
        ("Pie of Moon", True),  # palabras cortas en minúscula en medio: vale
        ("Big Bronze Dungeon Keys", False),  # cuatro palabras
        ("of Moon", False),  # la primera tiene que ir con mayúscula
        ("Moon dungeons", False),  # una palabra larga en minúscula
        ("123", False),
        ("", False),
    ],
)
def test_parece_nombre_propio(texto: str, es_nombre: bool) -> None:
    assert parece_nombre_propio(texto) is es_nombre


def test_que_entra_al_glosario_por_largo_y_formato() -> None:
    g = Glosario()
    largo_48, largo_49 = "Gear " + "x" * 43, "Gear " + "x" * 44
    ingles = {"a": "Axe", "b": "Ax", "c": largo_48, "d": largo_49, "e": "Boost %s", "f": "Wrench"}
    traducido = {"a": "Hacha", "b": "Ha", "c": "Engranaje x", "d": "Engranaje y", "e": "Mejora %s", "f": ""}
    g.agregar_pares(ingles, traducido)
    todos = g.todos()
    assert todos.get("Axe") == "Hacha"  # tres letras: entra
    assert "Ax" not in todos  # dos letras: no
    assert todos.get(largo_48) == "Engranaje x" and largo_49 not in todos
    assert "Boost %s" not in todos  # con argumentos no es un término
    assert "Wrench" not in todos  # sin traducción


def test_fijar_quita_espacios_e_ignora_lo_vacio() -> None:
    g = Glosario()
    g.fijar({"  Gear ": " Engranaje ", "Rod": "  ", " ": "Nada"})
    assert g.todos() == {"Gear": "Engranaje"} and g.fijo("Gear") == "Engranaje"


def _con_usos(veces_con_termino: int, veces_sin: int) -> Glosario:
    g = Glosario()
    g.agregar_pares({"k": "Lead"}, {"k": "Rienda"}, fuente="minecraft", oficial=True)
    ingles = {f"c{i}": f"Follow the lead now {i}" for i in range(veces_con_termino + veces_sin)}
    total = veces_con_termino + veces_sin
    es = {f"c{i}": (f"Sigue la rienda {i}" if i < veces_con_termino else f"Sigue la pista {i}") for i in range(total)}
    g.aprender_usos(ingles, es)
    return g


def test_un_termino_es_ambiguo_si_menos_de_la_mitad_de_sus_usos_lo_traducen_asi() -> None:
    assert _con_usos(1, 3).ambiguo("Lead")  # 1 de 4
    assert not _con_usos(2, 2).ambiguo("Lead")  # justo la mitad: no
    assert not _con_usos(0, 1).ambiguo("Lead")  # un solo uso no alcanza para decidir
    g = _con_usos(0, 4)
    g.fijar({"Lead": "Correa"})
    assert not g.ambiguo("Lead")  # lo del usuario nunca es ambiguo


def test_un_termino_ambiguo_solo_cuenta_si_se_usa_como_nombre() -> None:
    g = _con_usos(0, 4)
    assert "Lead" not in g.terminos_en("Follow the lead to the cave")
    assert g.terminos_en("Put a Lead on the horse") == {"Lead": "Rienda"}


def test_del_juego_y_oficial_ceden_ante_el_usuario() -> None:
    g = Glosario()
    g.agregar_pares({"k": "Iron Ingot"}, {"k": "Lingote de hierro"}, fuente="minecraft", oficial=True)
    assert g.del_juego("Iron Ingot") and g.oficial("Iron Ingot") == "Lingote de hierro"
    g.fijar({"Iron Ingot": "Barra de hierro"})
    assert not g.del_juego("Iron Ingot") and g.oficial("Iron Ingot") is None
    assert g.exacto("Iron Ingot") == "Barra de hierro"


def test_el_termino_mas_largo_tapa_al_corto_y_hay_tope() -> None:
    g = Glosario()
    g.agregar_pares(
        {"a": "Wither", "b": "Wither Skeleton"}, {"a": "Wither", "b": "Esqueleto del Wither"}, "minecraft", True
    )
    g.agregar_pares(
        {f"k{i}": f"Zorbium{chr(97 + i)}" for i in range(10)}, {f"k{i}": f"Zorbio{chr(97 + i)}" for i in range(10)}
    )
    assert g.terminos_en("A Wither Skeleton appears") == {"Wither Skeleton": "Esqueleto del Wither"}
    assert g.relevantes(["A Wither Skeleton appears"]) == {"Wither Skeleton": "Esqueleto del Wither"}
    texto = " ".join(f"Zorbium{chr(97 + i)}" for i in range(10))
    assert len(g.terminos_en(texto)) == 10 and len(g.terminos_en(texto, maximo=3)) == 3
    assert len(g.relevantes([texto], maximo=4)) == 4


def test_sustituir_respeta_la_mayuscula() -> None:
    g = Glosario()
    g.sustituir({"inframundita": "netherita"})
    assert g.corregir("Espada de Inframundita") == "Espada de Netherita"
    assert g.corregir("lingote de inframundita") == "lingote de netherita"

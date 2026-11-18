"""Lo que encontró la revisión de 150 textos con un juez más fuerte y el diccionario, y que era del proceso."""

from __future__ import annotations

from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.vocabulario import nucleos_de_objetos, preparar_sustituciones
from traductor_es.validacion.calidad import terminos_faltantes

_EN = {
    "item.minecraft.iron_chestplate": "Iron Chestplate",
    "item.minecraft.gold_chestplate": "Golden Chestplate",
    "item.minecraft.diamond_chestplate": "Diamond Chestplate",
    "item.minecraft.netherite_chestplate": "Netherite Chestplate",
    "item.minecraft.flow_banner_pattern": "Flow Banner Pattern",
    "item.minecraft.creeper_banner_pattern": "Creeper Banner Pattern",
}
_MX = {
    "item.minecraft.iron_chestplate": "Pechera de hierro",
    "item.minecraft.gold_chestplate": "Pechera de oro",
    "item.minecraft.diamond_chestplate": "Pechera de diamante",
    "item.minecraft.netherite_chestplate": "Pechera de netherita",
    "item.minecraft.flow_banner_pattern": "Estampado de estandarte",
    "item.minecraft.creeper_banner_pattern": "Estampado de estandarte",
}


def test_la_palabra_suelta_sale_de_la_familia_de_objetos_del_juego() -> None:
    assert nucleos_de_objetos(_EN, _MX) == {"Chestplate": "Pechera"}  # los estandartes no forman familia
    con_tres = {k: v for k, v in list(_EN.items())[:3]}
    assert nucleos_de_objetos(con_tres, _MX) == {}  # hacen falta al menos 4


def _glosario() -> Glosario:
    g = Glosario()
    g.agregar_pares(
        {"a": "Wither Skeleton", "b": "Wither"},
        {"a": "Esqueleto del Wither", "b": "Descomposición"},
        fuente="minecraft",
        oficial=True,
    )
    return g


def test_un_termino_en_plural_cuenta_y_cubre_al_corto() -> None:
    texto = "The Wild Hunt takes the form of wither skeletons."
    assert _glosario().relevantes([texto]) == {"Wither Skeleton": "Esqueleto del Wither"}
    assert _glosario().terminos_en(texto) == {"Wither Skeleton": "Esqueleto del Wither"}
    glosario = _glosario().todos()
    faltan = terminos_faltantes(texto, "toma la forma de esqueletos de la Descomposición.", glosario)
    assert faltan == {"Wither Skeleton": "Esqueleto del Wither"}  # y no se exige «Descomposición»


def test_el_corto_sigue_contando_fuera_del_largo() -> None:
    assert _glosario().relevantes(["Wither Skeletons cause Wither"]) == {
        "Wither Skeleton": "Esqueleto del Wither",
        "Wither": "Descomposición",
    }


def test_crafteo_pasa_a_fabricacion() -> None:
    g = Glosario()
    preparar_sustituciones(g)
    assert g.corregir("Recetas de crafteo. Crafteo rápido.") == "Recetas de fabricación. Fabricación rápido."

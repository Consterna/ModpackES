"""KubeJS 7 (Minecraft 1.21 y 26.x): los eventos de texto cambiaron de nombre (H-041, `dominio_mods.md`, D3 y D5).

Según el código de KubeJS (ramas 2101 y 2601): `ItemEvents.tooltip` pasó a `ItemEvents.modifyTooltips` y
`ItemEvents.dynamicTooltips`; la información y los grupos de JEI/REI/EMI, a `RecipeViewerEvents`.
"""

from __future__ import annotations

import pytest

from traductor_es.formatos import javascript
from traductor_es.modulos.scripts import es_nombre_de_grupo_rei, es_texto_visible


def _elegidos(src: str) -> list[str]:
    return [c.texto for c in javascript.escanear(src) if es_texto_visible(c)]


@pytest.mark.parametrize(
    ("src", "esperado"),
    [
        ("ItemEvents.modifyTooltips(e => { e.add('minecraft:stone', 'Shiny rock') })", ["Shiny rock"]),
        (
            "ItemEvents.modifyTooltips(e => { e.modify('minecraft:stone', t => { t.insert(1, 'Second line');"
            " t.add(['Third line']) }) })",
            ["Second line", "Third line"],
        ),
        ("ItemEvents.dynamicTooltips('mine', e => { e.add('Hold shift') })", ["Hold shift"]),
        (
            "RecipeViewerEvents.addInformation('item', e => { e.add('minecraft:stone', ['Found underground']) })",
            ["Found underground"],
        ),
        ("ItemEvents.tooltip(e => { e.addToAll('Made in the pack') })", ["Made in the pack"]),
    ],
)
def test_textos_de_kubejs7(src: str, esperado: list[str]) -> None:
    assert _elegidos(src) == esperado


@pytest.mark.parametrize(
    "src",
    [
        # lo que hay que igualar para quitar una línea: si se traduce, la línea deja de quitarse
        "ItemEvents.modifyTooltips(e => { e.modify('minecraft:stone', t => { t.removeText('Vanilla line') }) })",
        "ItemEvents.modifyTooltips(e => { e.modify('minecraft:stone', t => { t.removeExactText('Vanilla line') }) })",
        # un id de texto dinámico
        "ItemEvents.modifyTooltips(e => { e.modify('minecraft:stone', t => { t.dynamic('Shift Info') }) })",
    ],
)
def test_lo_que_se_compara_o_es_un_id_no_se_traduce(src: str) -> None:
    assert _elegidos(src) == []


def test_nombre_de_grupo_del_visor_de_recetas() -> None:
    src = "RecipeViewerEvents.groupEntries('item', e => { e.group('#c:ingots', 'kubejs:ingots', 'All Ingots') })"
    grupos = [c.texto for c in javascript.escanear(src) if es_nombre_de_grupo_rei(c)]
    assert grupos == ["All Ingots"]

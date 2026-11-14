"""Scripts de CraftTweaker: solo el texto que se ve, sin tocar ids, claves ni lógica."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.crafttweaker import ScriptsCraftTweaker, tapar_comentarios_almohadilla
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo

from . import fabrica

SCRIPT = """#priority 10
# Don't touch the recipes below: they're balanced
import crafttweaker.api.item.IItemStack;

<item:minecraft:diamond>.addTooltip("Shiny and very rare");
<item:mymod:wrench>.addShiftTooltip('Hold to rotate blocks');
<item:mymod:core>.displayName = "Reactor Core";
mods.jei.JEI.addDescription(<minecraft:stone>, "A plain old rock.");
mods.jei.JEI.addInfo(<item:mymod:core>, ["Generates power when heated."]);
game.setLocalization("item.mymod.core.name", "Reactor Core");
var color = "#ff0000"; // un color, no un comentario
if (name == "Reactor Core") { print("debug only"); }
recipes.addShaped("mymod:core_recipe", <item:mymod:core>, [[<item:minecraft:iron_ingot>]]);
"""


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def test_tapar_comentarios_conserva_el_largo_y_las_cadenas() -> None:
    src = '# it\'s a note\nvar c = "#fff"; # trailing\n'
    tapado = tapar_comentarios_almohadilla(src)
    assert len(tapado) == len(src)
    assert "it's" not in tapado and '"#fff"' in tapado and "trailing" not in tapado


def test_traduce_solo_lo_que_se_ve(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = juego / "scripts" / "items.zs"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(SCRIPT, encoding="utf-8", newline="")
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        modulo = ScriptsCraftTweaker(ctx)
        assert modulo.detectar() and modulo.describir() == "1 script de CraftTweaker"
        resumen = traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        assert resumen.pendientes == 0
        nuevo = ruta.read_text("utf-8")
        for texto in (
            "Shiny and very rare",
            "Hold to rotate blocks",
            "A plain old rock.",
            "Generates power when heated.",
        ):
            assert f"«ES» {texto}" in nuevo
        assert '.displayName = "«ES» Reactor Core"' in nuevo
        assert 'setLocalization("item.mymod.core.name", "«ES» Reactor Core")' in nuevo
        # Lo que no se ve queda igual: ids, claves, colores, comparaciones, depuración y comentarios
        for igual in ('"#ff0000"', 'name == "Reactor Core"', 'print("debug only")', '"mymod:core_recipe"',
                      "# Don't touch the recipes below: they're balanced", "#priority 10"):  # fmt: skip
            assert igual in nuevo
        # Restaurar devuelve el original byte a byte
        assert ScriptsCraftTweaker(ctx).restaurar()
    assert ruta.read_text("utf-8") == SCRIPT

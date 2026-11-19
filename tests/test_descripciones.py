"""Descripciones de los mods en la lista de mods: claves de Mod Menu y de NeoForge en el resource pack."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.descripciones import ESPACIO, Descripciones
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica

TOML = """modLoader="javafml"
loaderVersion="[1,)"
[[mods]]
modId="create"
displayName="Create"
description=\'\'\'Technology that empowers the player.
Line two.\'\'\'
[[mods]]
modId="vacio"
description="   "
"""


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _traducir(juego: Path, memoria: Memoria) -> tuple[Descripciones, Path, bool]:
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        modulo = Descripciones(ctx)
        detectado = modulo.detectar()
        if detectado:
            traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        return modulo, ctx.pack_listo().raiz if detectado else juego, detectado


def _tabla(pack: Path, variante: str = "es_mx") -> dict[str, str]:
    return json.loads((pack / "assets" / ESPACIO / "lang" / f"{variante}.json").read_text(encoding="utf-8"))


def test_neoforge_escribe_las_dos_claves_de_la_lista_de_mods(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.21.1", "neoforge")
    fabrica.jar(juego / "mods" / "create.jar", {"META-INF/neoforge.mods.toml": TOML})
    _, pack, detectado = _traducir(juego, memoria)
    assert detectado
    for variante in VARIANTES:
        tabla = _tabla(pack, variante)
        esperado = "«ES» Technology that empowers the player.\nLine two."
        assert tabla == {
            "fml.menu.mods.info.description.create": esperado,
            "neoforge.screen.mods.info.description.create": esperado,
        }


def test_fabric_con_mod_menu_incluye_los_mods_anidados(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "fabric")
    fabrica.jar(juego / "mods" / "modmenu-7.2.2.jar", {"fabric.mod.json": json.dumps({"id": "modmenu"})})
    fabrica.jar(
        juego / "mods" / "pipes.jar",
        {"fabric.mod.json": json.dumps({"id": "pipes", "description": "Simple item pipes"})},
        {"META-INF/jars/lib.jar": {"fabric.mod.json": json.dumps({"id": "lib", "description": "A library mod"})}},
    )
    fabrica.jar(
        juego / "mods" / "q.jar",
        {"quilt.mod.json": json.dumps({"quilt_loader": {"id": "q", "metadata": {"description": "Quilt mod here"}}})},
    )
    _, pack, detectado = _traducir(juego, memoria)
    assert detectado
    assert _tabla(pack) == {
        "modmenu.descriptionTranslation.pipes": "«ES» Simple item pipes",
        "modmenu.descriptionTranslation.lib": "«ES» A library mod",
        "modmenu.descriptionTranslation.q": "«ES» Quilt mod here",
    }


@pytest.mark.parametrize(
    ("version", "loader", "con_mod_menu"),
    [("1.20.1", "forge", False), ("1.20.1", "neoforge", False), ("1.20.1", "fabric", False)],
)
def test_sin_pantalla_que_lea_la_clave_no_hace_nada(
    tmp_path: Path, memoria: Memoria, version: str, loader: str, con_mod_menu: bool
) -> None:
    """Forge no tiene clave, NeoForge la tiene desde 1.20.4 y en Fabric hace falta Mod Menu."""
    juego = fabrica.prism(tmp_path, version, loader)
    fabrica.jar(juego / "mods" / "create.jar", {"META-INF/mods.toml": TOML, "fabric.mod.json": "{}"})
    if con_mod_menu:
        fabrica.jar(juego / "mods" / "modmenu-1.jar", {})
    _, _, detectado = _traducir(juego, memoria)
    assert not detectado


def test_respeta_la_descripcion_que_el_mod_ya_traduce(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.21.1", "neoforge")
    archivos = {
        "META-INF/neoforge.mods.toml": TOML,
        **fabrica.lang("create", "es_mx", {"fml.menu.mods.info.description.create": "Tecnología que empodera."}),
    }
    fabrica.jar(juego / "mods" / "create.jar", archivos)
    with Instancia(juego) as inst:
        modulo = Descripciones(Contexto(inst, Respaldo(juego), pack=PackSalida(inst)))
        assert modulo.recolectar() == []

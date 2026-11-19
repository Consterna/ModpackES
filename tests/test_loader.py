"""El idioma del loader (NeoForge/Forge) vive en libraries/ del launcher: se copia su español y se traduce el resto."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.loader import ESPACIO, IdiomaDelLoader
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _neoforge(libs: Path, version: str, ingles: dict[str, str], espanol: dict[str, str]) -> None:
    fabrica.jar(
        libs / "net" / "neoforged" / "neoforge" / version / f"neoforge-{version}-universal.jar",
        {
            **fabrica.lang("neoforge", "en_us", ingles),
            **fabrica.lang("neoforge", "es_es", espanol),
            **fabrica.lang("c", "en_us", {"tag.item.c.ingots": "Ingots"}),
        },
    )


def _prism(tmp_path: Path, mc: str = "1.21.1", loader: str = "neoforge") -> tuple[Path, Path]:
    raiz = tmp_path / "PrismLauncher"
    juego = fabrica.prism(raiz / "instances", mc, loader)
    return juego, raiz / "libraries"


def _traducir(juego: Path, memoria: Memoria) -> tuple[IdiomaDelLoader, Path]:
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        modulo = IdiomaDelLoader(ctx)
        assert modulo.detectar()
        traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        return modulo, ctx.pack_listo().raiz / "assets" / ESPACIO / "lang"


def test_copia_el_espanol_del_loader_y_traduce_lo_que_falta(tmp_path: Path, memoria: Memoria) -> None:
    juego, libs = _prism(tmp_path)
    ingles = {"fml.menu.mods": "Mods", "commands.neoforge.tps": "Mean tick time: %s ms"}
    _neoforge(libs, "21.1.250", ingles, {"fml.menu.mods": "Mods", "commands.neoforge.tps": "Tick medio: %s ms"})
    _neoforge(libs, "21.1.77", {"vieja.clave": "Old build only"}, {})  # una compilación más vieja: no se usa
    _neoforge(libs, "21.4.10", {"otra.version": "Other Minecraft"}, {})  # otro Minecraft (1.21.4): tampoco
    modulo, carpeta = _traducir(juego, memoria)
    assert modulo.describir() == "neoforge-21.1.250-universal.jar"
    es_mx = json.loads((carpeta / "es_mx.json").read_text(encoding="utf-8"))
    assert es_mx == {
        "commands.neoforge.tps": "Tick medio: %s ms",  # el es_es del loader, copiado sin gastar
        "tag.item.c.ingots": "«ES» Ingots",  # el espacio `c` solo trae inglés: se traduce
    }  # «Mods» es igual en español: no hace falta
    # es_es ya lo trae el loader: solo va lo que le falta
    es_es = json.loads((carpeta / "es_es.json").read_text(encoding="utf-8"))
    assert es_es == {"tag.item.c.ingots": "«ES» Ingots"}
    assert {p.name for p in carpeta.iterdir()} == {f"{v}.json" for v in VARIANTES}


def test_forge_universal_de_la_misma_version(tmp_path: Path, memoria: Memoria) -> None:
    juego, libs = _prism(tmp_path, "1.20.1", "forge")
    fabrica.jar(
        libs / "net" / "minecraftforge" / "forge" / "1.20.1-47.2.0" / "forge-1.20.1-47.2.0-universal.jar",
        fabrica.lang("forge", "en_us", {"forge.configgui.title": "Forge configuration"}),
    )
    _, carpeta = _traducir(juego, memoria)
    assert json.loads((carpeta / "es_mx.json").read_text(encoding="utf-8")) == {
        "forge.configgui.title": "«ES» Forge configuration"
    }


@pytest.mark.parametrize(("mc", "loader"), [("1.21.1", "fabric"), ("1.12.2", "forge"), ("1.21.1", "neoforge")])
def test_sin_jar_del_loader_no_hace_nada(tmp_path: Path, mc: str, loader: str) -> None:
    juego, _ = _prism(tmp_path, mc, loader)  # sin carpeta libraries
    with Instancia(juego) as inst:
        modulo = IdiomaDelLoader(Contexto(inst, Respaldo(juego), pack=PackSalida(inst)))
        assert not modulo.detectar()
        assert modulo.recolectar() == []

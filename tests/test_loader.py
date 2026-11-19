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
        "fml.menu.mods": "«ES» Mods",  # el es_es lo trae igual al inglés (sin traducir): va al motor
    }
    # es_es ya trae lo traducido: solo va lo que le falta o quedó en inglés
    es_es = json.loads((carpeta / "es_es.json").read_text(encoding="utf-8"))
    assert es_es == {"tag.item.c.ingots": "«ES» Ingots", "fml.menu.mods": "«ES» Mods"}
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


def _fml(libs: Path, version: str, texto: str) -> None:
    fabrica.jar(
        libs / "net" / "neoforged" / "fancymodloader" / "loader" / version / f"loader-{version}.jar",
        {"lang/en_us.json": json.dumps({"fml.menu.loadingmods": texto}), "lang/es_es.json": "{}"},
    )


def test_fancymodloader_suma_su_idioma_de_la_raiz_del_jar(tmp_path: Path, memoria: Memoria) -> None:
    juego, libs = _prism(tmp_path)
    _neoforge(libs, "21.1.250", {"fml.menu.mods": "Mods"}, {})
    _fml(libs, "4.0.44", "Loading mods")
    modulo, carpeta = _traducir(juego, memoria)
    assert modulo._fml is not None  # pyright: ignore[reportPrivateUsage]
    assert (
        json.loads((carpeta / "es_mx.json").read_text(encoding="utf-8"))["fml.menu.loadingmods"] == "«ES» Loading mods"
    )


def test_con_varias_versiones_de_fml_usa_la_que_nombra_la_metadata(tmp_path: Path, memoria: Memoria) -> None:
    juego, libs = _prism(tmp_path)
    _neoforge(libs, "21.1.250", {"fml.menu.mods": "Mods"}, {})
    _fml(libs, "4.0.44", "Loading mods (4.0.44)")
    _fml(libs, "7.0.2", "Loading mods (7.0.2)")
    meta = libs.parent / "meta" / "net.neoforged" / "21.1.250.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"libraries": [{"name": "net.neoforged.fancymodloader:loader:4.0.44"}],
                                "version": "21.1.250"}), encoding="utf-8")  # fmt: skip
    modulo, carpeta = _traducir(juego, memoria)
    assert modulo._fml is not None and modulo._fml.parent.name == "4.0.44"  # pyright: ignore[reportPrivateUsage]
    es_mx = json.loads((carpeta / "es_mx.json").read_text(encoding="utf-8"))
    assert es_mx["fml.menu.loadingmods"] == "«ES» Loading mods (4.0.44)"


def test_con_varias_versiones_de_fml_y_sin_metadata_no_adivina(tmp_path: Path, memoria: Memoria) -> None:
    juego, libs = _prism(tmp_path)
    _neoforge(libs, "21.1.250", {"fml.menu.mods": "Mods"}, {})
    _fml(libs, "4.0.44", "A")
    _fml(libs, "7.0.2", "B")
    modulo, _ = _traducir(juego, memoria)
    assert modulo._fml is None  # pyright: ignore[reportPrivateUsage]

"""Origins: nombre y descripción de orígenes, poderes y capas, con la clave que usa cada versión."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.origins import CLAVE, DERIVADA, ESPACIO, MIXTO, Origins
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica

ADDON = {
    "data/animal/origins/chameleon.json": json.dumps(
        {
            "name": "Chameleon",
            "description": "Masters of camouflage, 50% harder to spot.",
            "powers": ["animal:x"],
            "icon": "minecraft:lime_dye",
            "impact": 1,
        }  # fmt: skip
    ),
    "data/animal/powers/sub/climb.json": json.dumps(
        {
            "type": "apoli:climbing",
            "name": "Wall Climber",
            "description": "You can climb walls.",
            "condition": {"type": "apoli:sneaking", "name": "fall"},
        }  # fmt: skip
    ),
    "data/animal/origin_layers/main.json": json.dumps({"name": {"text": "Animal Layer"}, "origins": []}),
    # ya es una clave de idioma conocida: la traduce el módulo de mods
    "data/animal/powers/known.json": json.dumps({"name": "power.animal.known.name"}),
    **fabrica.lang("animal", "en_us", {"power.animal.known.name": "Known Power"}),
}


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _instancia(tmp_path: Path, version_origins: str, loader: str = "fabric", datapack: bool = False) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1", loader)
    if loader == "fabric":
        meta = {"fabric.mod.json": json.dumps({"id": "origins", "version": version_origins})}
    else:
        meta = {"META-INF/mods.toml": f'[[mods]]\nmodId="origins"\nversion="{version_origins}"\n'}
    fabrica.jar(juego / "mods" / "origins.jar", meta)
    if datapack:
        fabrica.jar(juego / "datapacks" / "animal.zip", {"pack.mcmeta": "{}", **ADDON})
    else:
        fabrica.jar(juego / "mods" / "animal.jar", ADDON)
    return juego


def _traducir(juego: Path, memoria: Memoria) -> tuple[Origins, dict[str, str]]:
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        modulo = Origins(ctx)
        assert modulo.detectar()
        traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        ruta = ctx.pack_listo().raiz / "assets" / ESPACIO / "lang" / "es_mx.json"
        return modulo, json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else {}


def test_origins_hasta_1_10_usa_el_texto_como_clave(tmp_path: Path, memoria: Memoria) -> None:
    modulo, tabla = _traducir(_instancia(tmp_path, "1.10.0"), memoria)
    assert modulo._modo == CLAVE  # pyright: ignore[reportPrivateUsage]
    assert tabla == {
        "Chameleon": "«ES» Chameleon",
        "Masters of camouflage, 50% harder to spot.": "«ES» Masters of camouflage, 50%% harder to spot.",
        "Wall Climber": "«ES» Wall Climber",
        "You can climb walls.": "«ES» You can climb walls.",
        "Animal Layer": "«ES» Animal Layer",
    }
    assert "Known Power" not in json.dumps(tabla) and "fall" not in tabla  # ni claves conocidas ni condiciones


def test_origins_1_13_usa_la_clave_derivada_del_id(tmp_path: Path, memoria: Memoria) -> None:
    modulo, tabla = _traducir(_instancia(tmp_path, "1.13.0-pre.3+mc.1.21.1", datapack=True), memoria)
    assert modulo._modo == DERIVADA  # pyright: ignore[reportPrivateUsage]
    assert tabla["origin.animal.chameleon.name"] == "«ES» Chameleon"
    assert tabla["power.animal.sub.climb.description"] == "«ES» You can climb walls."
    assert tabla["layer.animal.main.name"] == "«ES» Animal Layer"
    assert "Chameleon" not in tabla


def test_origins_1_12_no_toca_origenes_ni_capas_literales(tmp_path: Path, memoria: Memoria) -> None:
    modulo, tabla = _traducir(_instancia(tmp_path, "1.12.5"), memoria)
    assert modulo._modo == MIXTO  # pyright: ignore[reportPrivateUsage]
    assert set(tabla) == {"Wall Climber", "You can climb walls."}  # solo los poderes
    assert {t.ingles for t in modulo.sin_alcance} == {
        "Chameleon", "Masters of camouflage, 50% harder to spot.", "Animal Layer",
    }  # fmt: skip


def test_port_de_forge_usa_el_texto_como_clave(tmp_path: Path, memoria: Memoria) -> None:
    modulo, tabla = _traducir(_instancia(tmp_path, "1.10.0.4", loader="forge"), memoria)
    assert modulo._modo == CLAVE  # pyright: ignore[reportPrivateUsage]
    assert tabla["Chameleon"] == "«ES» Chameleon"


def test_sin_origins_no_hace_nada(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "fabric")
    fabrica.jar(juego / "mods" / "animal.jar", ADDON)
    with Instancia(juego) as inst:
        assert not Origins(Contexto(inst, Respaldo(juego), pack=PackSalida(inst))).detectar()

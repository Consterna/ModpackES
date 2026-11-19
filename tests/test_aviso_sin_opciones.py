"""Una instancia que nunca se abrió no tiene options.txt: el pack no se puede activar y hay que avisarlo."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import AVISO_SIN_OPCIONES, Proceso

from . import fabrica


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _instancia(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1", "forge")
    fabrica.jar(juego / "mods" / "mod.jar", fabrica.lang("mod", "en_us", {"item.mod.gear": "Copper Gear"}))
    return juego


def test_sin_options_txt_avisa_que_hay_que_activar_el_pack(tmp_path: Path, memoria: Memoria) -> None:
    juego = _instancia(tmp_path)
    with Proceso(juego, Simulador(), memoria=memoria) as proceso:
        informe = proceso.ejecutar()
    assert AVISO_SIN_OPCIONES in informe.avisos
    assert not (juego / "options.txt").exists()  # no se inventa uno: lo crea el juego


def test_con_options_txt_no_avisa(tmp_path: Path, memoria: Memoria) -> None:
    juego = _instancia(tmp_path)
    fabrica.opciones(juego, ["vanilla"], idioma="en_us")
    with Proceso(juego, Simulador(), memoria=memoria) as proceso:
        informe = proceso.ejecutar()
    assert AVISO_SIN_OPCIONES not in informe.avisos
    assert informe.pack_activado

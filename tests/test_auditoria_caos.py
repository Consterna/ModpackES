"""Errores reales del sistema durante una traducción: archivo abierto por otro programa, solo lectura.

En Windows, un archivo abierto por otro proceso (Minecraft con el juego abierto) no se puede reemplazar. La app debe
fallar con un mensaje que se entienda, sin dejar archivos a medias, y restaurar debe seguir funcionando después.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.__main__ import main
from traductor_es.fuentes import vanilla
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

from . import fabrica

pytestmark = pytest.mark.skipif(os.name != "nt", reason="los bloqueos de archivos que se prueban son de Windows")


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _modpack(tmp_path: Path) -> tuple[Path, Path]:
    juego = fabrica.prism(tmp_path, "1.20.1")
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text('{ title: "First steps" description: ["Craft your first tool."] }', encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego, capitulo


def test_archivo_abierto_por_otro_programa_da_error_claro_y_no_corrompe(tmp_path: Path, memoria: Memoria) -> None:
    juego, capitulo = _modpack(tmp_path)
    original = capitulo.read_bytes()
    with capitulo.open("rb"):  # CPython abre sin FILE_SHARE_DELETE: el archivo no se puede reemplazar
        with pytest.raises(OSError) as error, Proceso(juego, Simulador(), memoria=memoria) as p:
            p.ejecutar()
    assert capitulo.read_bytes() == original
    assert not list(capitulo.parent.glob("*.tmp"))  # el temporal no se queda… o, si queda, restaurar lo limpia
    assert isinstance(error.value, PermissionError) or getattr(error.value, "winerror", None) in (5, 32)
    # Con el archivo ya libre, traducir y restaurar funcionan y devuelven el original
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar()
        assert capitulo.read_bytes() != original
        p.restaurar()
    assert capitulo.read_bytes() == original


def test_linea_de_comandos_con_el_archivo_abierto_sale_con_1_y_mensaje(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    juego, capitulo = _modpack(tmp_path)
    with capitulo.open("rb"):
        assert main(["traducir", str(juego), "--simular"]) == 1
    salida = capsys.readouterr().out
    assert "✖" in salida and "Traceback" not in salida


def test_archivo_de_solo_lectura(tmp_path: Path, memoria: Memoria) -> None:
    juego, capitulo = _modpack(tmp_path)
    original = capitulo.read_bytes()
    capitulo.chmod(stat.S_IREAD)
    try:
        with pytest.raises(OSError), Proceso(juego, Simulador(), memoria=memoria) as p:
            p.ejecutar()
        assert capitulo.read_bytes() == original
    finally:
        capitulo.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_options_de_solo_lectura_no_impide_traducir_lo_demas(tmp_path: Path, memoria: Memoria) -> None:
    juego, capitulo = _modpack(tmp_path)
    opciones = juego / "options.txt"
    antes = opciones.read_bytes()
    opciones.chmod(stat.S_IREAD)
    try:
        with Proceso(juego, Simulador(), memoria=memoria) as p:
            informe = p.ejecutar()
        assert "«ES»" in capitulo.read_text(encoding="utf-8")
        assert opciones.read_bytes() == antes
        assert informe.avisos, "debería avisar que no pudo activar el pack"
    finally:
        opciones.chmod(stat.S_IREAD | stat.S_IWRITE)

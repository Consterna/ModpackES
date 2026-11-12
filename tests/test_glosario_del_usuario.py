"""El glosario del usuario se edita desde la línea de comandos: `modpackes glosario …`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from traductor_es import __main__ as cli
from traductor_es import configuracion


@pytest.fixture(autouse=True)
def datos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TRADUCTOR_ES_DATOS", str(tmp_path / "datos"))
    return tmp_path / "datos"


def test_agregar_y_listar(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["glosario", "agregar", "Death Knights", "Caballeros de la Muerte"]) == 0
    assert configuracion.leer_glosario_usuario() == {"Death Knights": "Caballeros de la Muerte"}
    cli.main(["glosario", "listar"])
    salida = capsys.readouterr().out
    assert "Death Knights = Caballeros de la Muerte" in salida and "1 términos" in salida


def test_agregar_reemplaza_el_valor_de_un_termino() -> None:
    cli.main(["glosario", "agregar", "Chest", "Baúl"])
    cli.main(["glosario", "agregar", "Chest", "Cofre"])
    assert configuracion.leer_glosario_usuario() == {"Chest": "Cofre"}


def test_quitar_un_termino() -> None:
    cli.main(["glosario", "agregar", "Chest", "Cofre"])
    assert cli.main(["glosario", "quitar", "Chest"]) == 0
    assert configuracion.leer_glosario_usuario() == {}


def test_quitar_un_termino_que_no_esta_da_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["glosario", "quitar", "Nada"]) != 0
    salida = capsys.readouterr()
    assert "Uso: glosario quitar" in salida.out + salida.err


def test_importar_mezcla_con_lo_que_ya_hay(tmp_path: Path) -> None:
    cli.main(["glosario", "agregar", "Chest", "Cofre"])
    archivo = tmp_path / "terminos.json"
    archivo.write_text(json.dumps({"Fluix": "Fluix", "Chest": "Arcón", "x": 3}, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["glosario", "importar", str(archivo)]) == 0
    assert configuracion.leer_glosario_usuario() == {"Chest": "Arcón", "Fluix": "Fluix"}  # lo que no es texto se ignora


def test_importar_un_archivo_roto_no_toca_el_glosario(tmp_path: Path) -> None:
    cli.main(["glosario", "agregar", "Chest", "Cofre"])
    archivo = tmp_path / "malo.json"
    archivo.write_text("[1, 2]", encoding="utf-8")
    assert cli.main(["glosario", "importar", str(archivo)]) != 0
    assert cli.main(["glosario", "importar", str(tmp_path / "no_existe.json")]) != 0
    assert configuracion.leer_glosario_usuario() == {"Chest": "Cofre"}


def test_no_guarda_terminos_vacios() -> None:
    configuracion.guardar_glosario_usuario({"a": " ", " ": "b", " Chest ": " Cofre "})
    assert configuracion.leer_glosario_usuario() == {"Chest": "Cofre"}

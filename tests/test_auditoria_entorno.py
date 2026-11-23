"""Entornos raros: la carpeta de datos no se puede usar (H-023)."""

from __future__ import annotations

from pathlib import Path

import pytest

from traductor_es.__main__ import main


def test_carpeta_de_datos_que_es_un_archivo_da_un_mensaje_y_no_una_traza(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    archivo = tmp_path / "no_es_carpeta"
    archivo.write_text("x", encoding="utf-8")
    monkeypatch.setenv("TRADUCTOR_ES_DATOS", str(archivo))
    assert main(["instancias"]) == 1
    salida = capsys.readouterr().out
    assert "No puedo usar la carpeta de datos" in salida and "TRADUCTOR_ES_DATOS" in salida

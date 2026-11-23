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


def test_la_fecha_de_la_ultima_traduccion_va_en_la_hora_del_pc() -> None:
    """H-024: la marca guarda la fecha en UTC; de noche en América (UTC-5) el día UTC ya es el siguiente."""
    from datetime import datetime

    from traductor_es.modulos.cambios import Cambios, fecha_local

    iso = "2026-11-22T01:30:00+00:00"
    local = datetime.fromisoformat(iso).astimezone().date().isoformat()
    assert fecha_local(iso) == local
    assert f"Desde la última traducción ({local})" in Cambios([], "indice", iso).resumen()
    desfase = datetime.fromisoformat(iso).astimezone().utcoffset()
    if desfase is not None and desfase.total_seconds() <= -2 * 3600:  # este PC (Colombia, UTC-5)
        assert local == "2026-11-21"
    assert fecha_local("no es fecha") == "no es fech"  # lo raro se corta como antes, sin fallar

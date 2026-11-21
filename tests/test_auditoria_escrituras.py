"""Escrituras de datos del usuario (glosario, preferencias) que no deben quedar a medias."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from traductor_es import configuracion


class Corte(Exception):
    pass


def _cortar_a_medias(monkeypatch: pytest.MonkeyPatch) -> None:
    """La próxima escritura de texto deja la mitad del archivo y falla (corte de luz, disco lleno)."""
    original: Callable[..., Any] = Path.write_text

    def a_medias(self: Path, datos: str, *args: Any, **kwargs: Any) -> int:
        original(self, datos[: len(datos) // 2], *args, **kwargs)
        raise Corte(self.name)

    monkeypatch.setattr(Path, "write_text", a_medias)


def test_corte_al_guardar_el_glosario_no_pierde_los_terminos_anteriores(monkeypatch: pytest.MonkeyPatch) -> None:
    configuracion.guardar_glosario_usuario({"Wrench": "Llave inglesa", "Gear": "Engranaje"})
    with monkeypatch.context() as m:
        _cortar_a_medias(m)
        with pytest.raises(Corte):
            configuracion.guardar_glosario_usuario({"Wrench": "Llave", "Gear": "Engranaje", "Nuevo": "Nuevo"})
    assert configuracion.leer_glosario_usuario() == {"Wrench": "Llave inglesa", "Gear": "Engranaje"}


def test_corte_al_guardar_preferencias_no_las_borra(monkeypatch: pytest.MonkeyPatch) -> None:
    configuracion.guardar_preferencias({"motor": "gemini", "dialecto": "es_ar"})
    with monkeypatch.context() as m:
        _cortar_a_medias(m)
        with pytest.raises(Corte):
            configuracion.guardar_preferencias({"motor": "openrouter", "dialecto": "es_ar"})
    assert configuracion.leer_preferencias() == {"motor": "gemini", "dialecto": "es_ar"}


def test_las_preferencias_nunca_guardan_la_clave() -> None:
    configuracion.guardar_preferencias({"motor": "gemini", "clave": "AIza" + "x" * 35})
    assert "clave" not in configuracion.leer_preferencias()
    assert "AIza" not in (configuracion.carpeta_datos() / "preferencias.json").read_text(encoding="utf-8")

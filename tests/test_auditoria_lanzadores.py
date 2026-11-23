"""Lanzadores contrastados con su código actual (`.auditoria/investigacion/dominio_mods.md`).

GDLauncher (Carbon) guarda `instance.json` en la carpeta de la instancia y el juego en `<instancia>/instance/`
(`crates/carbon_app/src/managers/instance/mod.rs`): antes, ninguna de sus instancias salía en la lista (H-040).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from traductor_es.fuentes import lanzadores
from traductor_es.fuentes.instancia import resolver_carpeta_juego


def test_gdlauncher_carbon_aparece_en_la_lista(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    appdata = tmp_path / "appdata"
    instancia = appdata / "gdlauncher_carbon" / "data" / "instances" / "Pack Uno"
    (instancia / "instance" / "mods").mkdir(parents=True)
    (instancia / "instance.json").write_text('{"name": "Pack Uno"}', encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    encontradas = [e for e in lanzadores.buscar() if e.lanzador == "GDLauncher"]
    assert [e.juego for e in encontradas] == [instancia / "instance"]


def test_soltar_la_carpeta_de_una_instancia_de_gdlauncher(tmp_path: Path) -> None:
    (tmp_path / "instance" / "config").mkdir(parents=True)
    assert resolver_carpeta_juego(tmp_path) == tmp_path / "instance"


def test_la_carpeta_de_la_instancia_sigue_teniendo_prioridad(tmp_path: Path) -> None:
    (tmp_path / "mods").mkdir()
    (tmp_path / "instance" / "mods").mkdir(parents=True)
    assert resolver_carpeta_juego(tmp_path) == tmp_path

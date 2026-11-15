"""Banco de libros: pares inglés/español de libros de Patchouli, campo por campo y sin referencias a medias."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def armar_banco_libros() -> ModuleType:
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    try:
        import armar_banco_libros as modulo  # pyright: ignore[reportMissingImports]
    finally:
        sys.path.pop(0)
    return modulo  # pyright: ignore[reportUnknownVariableType]


def _libro(raiz: Path, jar: str, idioma: str, datos: dict[str, object], archivo: str = "entries/a.json") -> None:
    ruta = raiz / "pack" / "langs" / jar / "assets" / "m" / "patchouli_books" / "guia" / idioma / archivo
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding="utf-8")


def test_arma_el_banco_con_los_libros_traducidos(tmp_path: Path, armar_banco_libros: ModuleType) -> None:
    _libro(
        tmp_path,
        "m.jar",
        "en_us",
        {"name": "Getting Started", "pages": [{"text": "Welcome to this guide about machines."}]},
    )
    _libro(
        tmp_path,
        "m.jar",
        "es_es",
        {"name": "Primeros pasos", "pages": [{"text": "Te damos la bienvenida a esta guía sobre máquinas."}]},
    )
    # Una «traducción» a medias (mezcla inglés y español) no sirve de referencia
    _libro(tmp_path, "m.jar", "en_us", {"name": "Power the Grinder now"}, "entries/b.json")
    _libro(tmp_path, "m.jar", "es_es", {"name": "Power the Grinder ahora"}, "entries/b.json")
    # Un libro sin español no aporta nada
    _libro(tmp_path, "otro.jar", "en_us", {"name": "Lonely"})
    banco = armar_banco_libros.armar(tmp_path, textos=10, pares_lang=[])  # pyright: ignore[reportUnknownMemberType]
    pares = {t["original"]: t["referencia"] for t in banco["textos"]}
    assert pares == {
        "Getting Started": "Primeros pasos",
        "Welcome to this guide about machines.": "Te damos la bienvenida a esta guía sobre máquinas.",
    }
    assert {t["ambito"] for t in banco["textos"]} == {"libro"} and banco["dialecto"] == "es_mx"


def test_prefiere_es_mx_como_referencia(tmp_path: Path, armar_banco_libros: ModuleType) -> None:
    _libro(tmp_path, "m.jar", "en_us", {"name": "Getting Started"})
    _libro(tmp_path, "m.jar", "es_es", {"name": "Primeros pasos"})
    _libro(tmp_path, "m.jar", "es_mx", {"name": "Para empezar"})
    banco = armar_banco_libros.armar(tmp_path, textos=10, pares_lang=[])  # pyright: ignore[reportUnknownMemberType]
    assert [t["referencia"] for t in banco["textos"]] == ["Para empezar"]


def test_suma_los_libros_que_vienen_en_lang(tmp_path: Path, armar_banco_libros: ModuleType) -> None:
    par = armar_banco_libros.abl.Par  # pyright: ignore[reportUnknownMemberType]
    largo = "Place the main ingredient on the central pedestal and the catalysts around it."
    traduccion = "Coloca el ingrediente principal sobre el pedestal central y los catalizadores alrededor."
    lang = [
        par("ma.jar", "ma", "ma.guide.entry.infusion.page.1", largo, traduccion),
        par("ma.jar", "ma", "ma.guide.title", "Guide", "Guía"),  # corto: ya lo mide el banco de interfaz
        par("x.jar", "x", "options.book.render", largo, traduccion),  # una opción, no un libro
    ]
    banco = armar_banco_libros.armar(tmp_path, textos=10, pares_lang=lang)  # pyright: ignore[reportUnknownMemberType]
    assert [t["original"] for t in banco["textos"]] == [largo]

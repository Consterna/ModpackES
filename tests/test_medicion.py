"""Métricas del banco de referencia y el script que las calcula."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import codigos_iguales
from traductor_es.validacion import medicion

BANCO = Path(__file__).parent / "datos" / "referencia_es.json"


def test_chrf_extremos_y_orden() -> None:
    assert medicion.chrf("Lingote de hierro", "Lingote de hierro") == pytest.approx(100.0)
    assert medicion.chrf("xyz", "Lingote de hierro") < 5
    cercana = medicion.chrf("Lingote de fierro", "Lingote de hierro")
    lejana = medicion.chrf("Barra metálica", "Lingote de hierro")
    assert 60 < cercana < 100 and lejana < cercana
    assert medicion.chrf("Hola mundo", "Holamundo") == pytest.approx(100.0)  # los espacios no cuentan


def test_terminos_sin_distinguir_tildes_ni_mayusculas() -> None:
    glosario = {"Crafting Table": "Mesa de trabajo", "Furnace": "Horno"}
    casos = [("Build a Crafting Table", "Construye una mesa de trabajo"), ("Use a Furnace", "Usa una fragua")]
    assert medicion.terminos(casos, glosario) == (2, 1)


def test_el_banco_es_coherente() -> None:
    banco = medicion.Banco.leer(BANCO)
    assert len(banco.casos) >= 140 and {c.ambito for c in banco.casos} == {"ui", "mision", "libro", "script"}
    assert len({c.original for c in banco.casos}) == len(banco.casos)
    assert all(codigos_iguales(c.original, c.referencia) for c in banco.casos)
    presentes, respetados = medicion.terminos(((c.original, c.referencia) for c in banco.casos), banco.glosario)
    assert presentes >= 20 and respetados == presentes  # las referencias respetan su propio glosario


def test_medir_con_el_simulador_y_con_revision() -> None:
    banco = medicion.Banco.leer(BANCO)
    marcado = "«ES» Getting Started"
    [antes, despues] = medicion.medir(
        Simulador(marcar=frozenset({marcado})), banco, "sim", "gemini-3.8-flash", revisar=True
    )
    # El simulador devuelve «ES» + el inglés: las reglas rechazan las frases largas (inglés residual)
    # y lo que pasa queda lejos de la referencia. Justo lo que la medición tiene que mostrar.
    assert 100 < antes.traducidos < len(banco.casos) and 0 < antes.chrf < 40
    assert antes.costo_estimado is not None and despues.costo_estimado is not None
    assert despues.costo_estimado > antes.costo_estimado
    assert "1 quedaron corregidos" in despues.revision
    assert "chrF promedio" in antes.tabla() and set(antes.por_ambito) == {"ui", "mision", "libro", "script"}


def test_script_simulado(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    try:
        import medir_calidad  # pyright: ignore[reportMissingImports]
    finally:
        sys.path.pop(0)
    salida = tmp_path / "m.json"
    assert medir_calidad.main(["--simular", "--salida", str(salida)]) == 0  # pyright: ignore[reportUnknownMemberType]
    assert "Textos traducidos" in capsys.readouterr().out
    assert json.loads(salida.read_text("utf-8"))[0]["motor"] == "simulador"

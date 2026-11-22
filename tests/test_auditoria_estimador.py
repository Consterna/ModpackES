"""El estimador de costo, calibrado con lo que cobró Google de verdad (H-020), y los precios con fecha (H-008).

Medido el 2026-11-21 con gemini-3.8-flash sobre `tests/datos/referencia_es.json` (148 textos): sin revisión,
US$ 0,0138-0,0145 en 5 corridas (entrada 4457 tokens, salida 2799-2895); con revisión, US$ 0,0214. Antes de
recalibrar, la estimación daba 0,011 y 0,018 (25-31 % y 19 % cortas).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from traductor_es import proceso
from traductor_es.motores.gemini import precio
from traductor_es.proceso import Informe, InformeModulo
from traductor_es.validacion import medicion

BANCO = Path(__file__).parent / "datos" / "referencia_es.json"
_GRUPO = {"ui": "mods", "mision": "misiones", "libro": "libros", "script": "scripts"}


def _informe_del_banco() -> Informe:
    """El mismo informe que arma `medicion.medir` para estimar el costo del banco."""
    por_ambito: dict[str, list[str]] = {}
    for caso in medicion.Banco.leer(BANCO).casos:
        por_ambito.setdefault(caso.ambito, []).append(caso.original)
    return Informe(
        [InformeModulo(_GRUPO.get(a, a), a, "", len(t), len(t), sum(len(x) for x in t)) for a, t in por_ambito.items()]
    )


def _precio_noviembre(modelo: str) -> tuple[float, float] | None:
    return precio(modelo, date(2026, 11, 21))


@pytest.fixture
def noviembre_2026(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los precios del día en que se midió, para que la prueba no cambie con el calendario."""
    monkeypatch.setattr(proceso, "precio_de", _precio_noviembre)


def test_la_estimacion_sin_revision_coincide_con_lo_cobrado(noviembre_2026: None) -> None:
    estimado = _informe_del_banco().costo("gemini-3.8-flash", False)
    assert estimado is not None
    assert 0.0138 * 0.95 <= estimado <= 0.0145 * 1.05, estimado


def test_la_estimacion_con_revision_no_se_queda_corta(noviembre_2026: None) -> None:
    estimado = _informe_del_banco().costo("gemini-3.8-flash", False, revisar=True)
    assert estimado is not None
    assert 0.0214 * 0.9 <= estimado <= 0.0214 * 1.25, estimado


def test_los_lotes_se_cuentan_por_modulo_como_el_traductor(noviembre_2026: None) -> None:
    """Dos módulos de 20 textos son dos pedidos, no uno: cada uno repite las instrucciones."""
    juntos = Informe([InformeModulo("mods", "a", "", 40, 40, 800)]).costo("gemini-3.8-flash", False)
    separados = Informe(
        [InformeModulo("mods", "a", "", 20, 20, 400), InformeModulo("libros", "b", "", 20, 20, 400)]
    ).costo("gemini-3.8-flash", False)
    assert juntos is not None and separados is not None and separados > juntos


def test_precios_con_fecha() -> None:
    assert precio("gemini-3.8-flash", date(2026, 12, 31)) == (0.75, 3.75)
    assert precio("gemini-3.8-flash", date(2027, 1, 1)) == (1.50, 7.50)
    assert precio("gemini-3.6-flash", date(2027, 3, 1)) == (1.50, 7.50)
    assert precio("gemini-2.5-flash-lite", date(2026, 11, 30)) == (0.10, 0.40)
    assert precio("gemini-2.5-flash-lite", date(2026, 12, 1)) == (0.30, 2.50)  # se atiende con 3.5 Flash-Lite
    assert precio("gemini-3.5-flash-lite", date(2027, 6, 1)) == (0.30, 2.50)
    assert precio("modelo-inventado") is None


def test_el_estimado_del_ano_que_viene_es_el_doble() -> None:
    informe = _informe_del_banco()
    ahora = proceso.precio_de
    try:
        proceso.precio_de = lambda modelo: precio(modelo, date(2026, 11, 21))  # type: ignore[assignment]
        hoy = informe.costo("gemini-3.8-flash", False)
        proceso.precio_de = lambda modelo: precio(modelo, date(2027, 1, 2))  # type: ignore[assignment]
        enero = informe.costo("gemini-3.8-flash", False)
    finally:
        proceso.precio_de = ahora
    assert hoy is not None and enero == pytest.approx(2 * hoy)


def test_el_costo_se_muestra_como_rango(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from traductor_es.__main__ import main
    from traductor_es.fuentes import vanilla

    from . import fabrica

    assert proceso.rango_de_costo(1.0) == (0.85, 1.25)
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.x": "Iron Plate"}))
    original = vanilla.raices_de_lanzadores
    vanilla.raices_de_lanzadores = list  # type: ignore[assignment]
    try:
        assert main(["analizar", str(juego)]) == 0
    finally:
        vanilla.raices_de_lanzadores = original
    salida = capsys.readouterr().out
    assert "Costo estimado con gemini-3.8-flash: ≈ US$" in salida and "(entre " in salida

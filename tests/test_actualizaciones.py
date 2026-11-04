"""Aviso de versión nueva: compara versiones, tolera fallos de red y se muestra en la ventana."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest
from pytestqt.qtbot import QtBot

from traductor_es import actualizaciones, configuracion
from traductor_es.actualizaciones import Novedad
from traductor_es.ui.ventana import Ventana


def cliente(respuesta: httpx.Response | Exception, pedidos: list[httpx.Request] | None = None) -> httpx.Client:
    def manejar(pedido: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(pedido)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    return httpx.Client(transport=httpx.MockTransport(manejar))


def release(**datos: Any) -> httpx.Response:
    return httpx.Response(200, json={"tag_name": "v2.1.0", "html_url": "https://github.com/x/r/2.1.0", **datos})


def test_numeros_de_version() -> None:
    assert actualizaciones.numeros("v2.1.0") == (2, 1, 0) and actualizaciones.numeros("10.0.3") == (10, 0, 3)
    assert actualizaciones.numeros("2.1.0-rc1") is None and actualizaciones.numeros("nada") is None


@pytest.mark.parametrize(
    ("actual", "esperada"),
    [("2.0.0", Novedad("2.1.0", "https://github.com/x/r/2.1.0")), ("2.1.0", None), ("3.0.0", None)],
)
def test_solo_avisa_si_es_mas_nueva(actual: str, esperada: Novedad | None) -> None:
    pedidos: list[httpx.Request] = []
    with cliente(release(), pedidos) as c:
        assert actualizaciones.buscar(actual, c) == esperada
    assert str(pedidos[0].url) == "https://api.github.com/repos/Consterna/ModpackES/releases/latest"
    assert pedidos[0].headers["user-agent"].startswith("ModpackES/")


@pytest.mark.parametrize(
    "respuesta",
    [
        release(prerelease=True),
        release(draft=True),
        httpx.Response(404, json={"message": "Not Found"}),
        httpx.Response(200, text="no es JSON"),
        httpx.Response(200, json=["lista"]),
        httpx.ConnectError("sin internet"),
        httpx.ReadTimeout("lento"),
    ],
)
def test_cualquier_problema_es_silencioso(respuesta: httpx.Response | Exception) -> None:
    with cliente(respuesta) as c:
        assert actualizaciones.buscar("2.0.0", c) is None


def _ventana(qtbot: QtBot, buscar: Callable[[], Novedad | None]) -> Ventana:
    v = Ventana(buscar_instancias=list, buscar_novedad=buscar)
    qtbot.addWidget(v)
    return v


def test_la_ventana_muestra_el_enlace(qtbot: QtBot) -> None:
    v = _ventana(qtbot, lambda: Novedad("9.9.9", "https://github.com/Consterna/ModpackES/releases/tag/v9.9.9"))
    qtbot.waitUntil(lambda: v.novedad.isVisible() or v.novedad.text() != "", timeout=10000)
    assert "9.9.9" in v.novedad.text() and "releases/tag/v9.9.9" in v.novedad.text()
    assert "versión nueva" in v.log.toPlainText()


def test_sin_novedad_no_muestra_nada_y_se_puede_desactivar(qtbot: QtBot) -> None:
    llamadas: list[int] = []

    def nada() -> Novedad | None:
        llamadas.append(1)
        return None

    v = _ventana(qtbot, nada)
    qtbot.waitUntil(lambda: v._hilo_novedad is None, timeout=10000)  # pyright: ignore[reportPrivateUsage]
    assert llamadas == [1] and v.novedad.text() == ""
    v.c_avisar.setChecked(False)
    assert configuracion.leer_preferencias()["avisar_version"] is False
    otra = _ventana(qtbot, nada)
    assert not otra.c_avisar.isChecked() and llamadas == [1]  # desactivado: ni se consulta


def test_en_pruebas_y_en_la_autoprueba_no_sale_a_internet(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    def prohibido(*_: object) -> None:
        raise AssertionError("no debía consultar GitHub")

    monkeypatch.setattr(actualizaciones, "buscar", prohibido)
    monkeypatch.setenv("TRADUCTOR_ES_PRUEBA_UI", "1")
    qtbot.addWidget(Ventana(buscar_instancias=list))
    monkeypatch.delenv("TRADUCTOR_ES_PRUEBA_UI")
    qtbot.addWidget(Ventana(buscar_instancias=list, avisar_version=False))

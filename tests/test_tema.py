"""Tema agua marina y morado: contraste WCAG, aplicación en Qt, seguimiento del modo de Windows e íconos."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from traductor_es.ui import iconos, tema


@pytest.fixture
def app(qtbot: QtBot) -> Iterator[QApplication]:
    instancia = QApplication.instance()
    assert isinstance(instancia, QApplication)
    yield instancia
    instancia.setStyleSheet("")


@pytest.mark.parametrize("paleta", [tema.OSCURO, tema.CLARO], ids=["oscuro", "claro"])
def test_contraste_wcag_de_cada_par(paleta: tema.Paleta) -> None:
    assert tema.pares_insuficientes(paleta) == []


def test_contraste_conocido() -> None:
    assert tema.contraste("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert tema.contraste("#777777", "#777777") == pytest.approx(1.0)


def test_la_hoja_usa_los_colores_de_la_paleta() -> None:
    hoja = tema.hoja(tema.OSCURO)
    assert tema.OSCURO.acento in hoja and tema.OSCURO.morado in hoja and 'tipo="primario"' in hoja
    assert tema.CLARO.acento in tema.hoja(tema.CLARO) and tema.OSCURO.acento not in tema.hoja(tema.CLARO)
    rutas = tema.recursos(tema.OSCURO)
    assert set(rutas) == {"marca", "abajo", "arriba"}
    marca = rutas["marca"]
    assert f"url({marca})" in hoja and tema.OSCURO.sobre_acento.encode() in Path(marca).read_bytes()


def test_preferencia_fija_y_fusion(app: QApplication) -> None:
    t = tema.instalar(app, "claro")
    assert t.estilo is not None and t.estilo.name().lower() == "fusion"
    assert t.paleta is tema.CLARO and tema.actual() is tema.CLARO
    assert app.palette().color(QPalette.ColorRole.Window).name().upper() == tema.CLARO.fondo.upper()
    vistos: list[tema.Paleta] = []
    t.cambiado.connect(vistos.append)
    t.elegir("oscuro")
    assert vistos == [tema.OSCURO] and tema.OSCURO.fondo in app.styleSheet()
    t.elegir("inventado")
    assert t.preferencia == "sistema"


def test_con_sistema_sigue_el_modo_de_windows(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin pantalla Qt no cambia el modo, así que se simula: el sistema informa el modo y avisa del cambio."""
    t = tema.instalar(app, "sistema")
    modo = {"actual": Qt.ColorScheme.Light}
    monkeypatch.setattr(t, "esquema_sistema", lambda: modo["actual"])
    t._al_cambiar_sistema(Qt.ColorScheme.Light)  # pyright: ignore[reportPrivateUsage]
    assert t.paleta is tema.CLARO
    modo["actual"] = Qt.ColorScheme.Dark
    t._al_cambiar_sistema(Qt.ColorScheme.Dark)  # pyright: ignore[reportPrivateUsage]
    assert t.paleta is tema.OSCURO
    modo["actual"] = Qt.ColorScheme.Unknown
    t.aplicar()
    assert t.paleta is tema.OSCURO  # si Windows no informa el modo: oscuro
    t.elegir("claro")
    modo["actual"] = Qt.ColorScheme.Dark
    t._al_cambiar_sistema(Qt.ColorScheme.Dark)  # pyright: ignore[reportPrivateUsage]
    assert t.paleta is tema.CLARO  # con una preferencia fija no sigue al sistema


def test_iconos_disponibles_y_tenidos(app: QApplication) -> None:
    nombres = iconos.disponibles()
    assert len(nombres) >= 30 and (iconos.CARPETA / "LICENSE.txt").is_file()
    for nombre in nombres:
        assert not iconos.icono(nombre).isNull()
    imagen = iconos.pixmap("square", "#2EF5C9", 24).toImage()
    colores = {
        imagen.pixelColor(x, y).name().upper()
        for x in range(24)
        for y in range(24)
        if imagen.pixelColor(x, y).alpha() == 255
    }
    assert colores == {"#2EF5C9"}  # el trazo sale del color pedido
    with pytest.raises(ValueError, match="inventado"):
        iconos.icono("inventado")


def test_sin_carpeta_temporal_la_app_abre_igual(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import tempfile

    archivo = tmp_path / "no-es-carpeta"
    archivo.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(archivo))
    r = tema.recursos(tema.OSCURO)
    assert set(r) == {"marca", "abajo", "arriba"} and all(Path(v).is_file() for v in r.values())


def test_los_iconos_se_reusan() -> None:
    assert iconos.icono("check", "#FFFFFF", 16) is iconos.icono("check", "#FFFFFF", 16)

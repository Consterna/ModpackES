"""La ventana sin pantalla: textos ajenos sin HTML, accesibilidad básica, teclado y capturas de cada estado.

Un nombre de instancia viene del lanzador o del propio modpack (`instance.cfg`, `.mrpack`) y los mensajes de
error traen nombres de archivos del modpack: nada de eso debe dibujarse como HTML (H-036).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QWidget
from pytestqt.qtbot import QtBot

from traductor_es.fuentes import vanilla
from traductor_es.fuentes.lanzadores import InstanciaEncontrada
from traductor_es.motores.base import Motor
from traductor_es.motores.simulador import Simulador
from traductor_es.ui import tema
from traductor_es.ui.componentes import etiqueta
from traductor_es.ui.ventana import Ventana

from . import fabrica

HOSTIL = '<b>Pack</b><img src="file:///C:/Windows/win.ini"><a href="https://ejemplo.invalid">clic</a>'


@pytest.fixture(autouse=True)
def _entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
    monkeypatch.setenv("TRADUCTOR_ES_PRUEBA_UI", "1")


@pytest.fixture
def app(qtbot: QtBot) -> Iterator[QApplication]:
    instancia = QApplication.instance()
    assert isinstance(instancia, QApplication)
    yield instancia
    instancia.setStyleSheet("")


def _modpack(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench"}))
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text('{ title: "Getting Started" }', encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _ventana(qtbot: QtBot, juego: Path, nombre: str = "Prueba") -> Ventana:
    def simulador(_motor: str, _clave: str | None, _modelo: str, _direccion: str) -> Motor:
        return Simulador()

    v = Ventana(
        buscar_instancias=lambda: [InstanciaEncontrada("Prism Launcher", nombre, juego)], fabrica_motor=simulador
    )
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    return v


def _se_dibuja_como_html(e: QLabel) -> bool:
    from PySide6 import QtGui

    formato = e.textFormat()
    return formato == Qt.TextFormat.RichText or (
        formato == Qt.TextFormat.AutoText and QtGui.Qt.mightBeRichText(e.text())
    )


# --- texto ajeno: nunca como HTML ------------------------------------------------------------------------------------


def test_un_nombre_de_instancia_con_html_se_muestra_tal_cual(qtbot: QtBot, tmp_path: Path) -> None:
    v = _ventana(qtbot, _modpack(tmp_path), HOSTIL)
    con_el_nombre = [e for e in v.findChildren(QLabel) if "<img" in e.text()]
    assert con_el_nombre, "el nombre debería verse en alguna etiqueta"
    assert not [e for e in con_el_nombre if _se_dibuja_como_html(e)]


def test_un_mensaje_de_error_con_html_se_muestra_tal_cual(qtbot: QtBot, tmp_path: Path) -> None:
    v = _ventana(qtbot, _modpack(tmp_path))
    v.estado.setText('✖ No pude leer <img src="file:///x.png"> en el modpack')
    assert not _se_dibuja_como_html(v.estado)


def test_las_etiquetas_con_enlace_propio_siguen_con_enlace(qtbot: QtBot, tmp_path: Path) -> None:
    v = _ventana(qtbot, _modpack(tmp_path))
    assert v.creditos.textFormat() == Qt.TextFormat.RichText and v.creditos.openExternalLinks()
    assert etiqueta("<b>x</b>").textFormat() == Qt.TextFormat.PlainText
    assert etiqueta("<b>x</b>", enriquecida=True).textFormat() == Qt.TextFormat.RichText


def test_el_aviso_de_version_escapa_lo_que_viene_de_github(qtbot: QtBot, tmp_path: Path) -> None:
    v = _ventana(qtbot, _modpack(tmp_path))
    v._mostrar_novedad(['2.3.0<img src="file:///x">', 'https://github.com/x"><b>falso'])  # pyright: ignore[reportPrivateUsage]
    texto = v.novedad.text()
    assert "<img" not in texto and "&lt;img" in texto
    assert '"><b>falso' not in texto


def test_el_dialogo_de_correcciones_muestra_texto_tal_cual(qtbot: QtBot) -> None:
    from traductor_es.nucleo.memoria import Memoria
    from traductor_es.ui.correcciones import DialogoCorrecciones

    with Memoria(":memory:") as m:
        d = DialogoCorrecciones("es_mx", memoria=m)
        qtbot.addWidget(d)
        assert all(e.textFormat() == Qt.TextFormat.PlainText for e in d.findChildren(QLabel))


# --- accesibilidad y teclado -----------------------------------------------------------------------------------------


def test_cada_boton_visible_tiene_un_nombre_para_el_lector_de_pantalla(qtbot: QtBot, tmp_path: Path) -> None:
    v = _ventana(qtbot, _modpack(tmp_path))
    v.show()
    qtbot.waitExposed(v)
    sin_nombre = [
        b.objectName() or type(b).__name__
        for b in v.findChildren(QAbstractButton)
        if b.isVisible() and not (b.text().strip() or b.accessibleName().strip() or b.toolTip().strip())
    ]
    assert sin_nombre == []


def test_con_el_teclado_se_llega_al_boton_principal(qtbot: QtBot, tmp_path: Path) -> None:
    """Sin pantalla real Qt no da el foco a la ventana: se recorre la cadena de Tab y se filtra como lo hace Qt."""
    v = _ventana(qtbot, _modpack(tmp_path))
    v.show()
    qtbot.waitExposed(v)
    con_tab: list[QWidget] = []
    actual: QWidget = v
    for _ in range(2000):
        siguiente = actual.nextInFocusChain()
        if siguiente is None or siguiente is v:
            break
        actual = siguiente
        if actual.isVisible() and actual.isEnabled() and actual.focusPolicy() & Qt.FocusPolicy.TabFocus:
            con_tab.append(actual)
    assert v.b_principal in con_tab
    assert v.lista in con_tab or any(v.lista.isAncestorOf(w) for w in con_tab)


# --- capturas de cada estado, en claro y en oscuro -------------------------------------------------------------------


def _captura_util(imagen: QImage) -> bool:
    """La captura no está vacía ni es de un solo color (la ventana se dibujó de verdad)."""
    if imagen.isNull() or imagen.width() < 200 or imagen.height() < 200:
        return False
    colores = {imagen.pixel(x, y) for x in range(0, imagen.width(), 37) for y in range(0, imagen.height(), 37)}
    return len(colores) > 8


@pytest.mark.parametrize("preferencia", ["claro", "oscuro"])
def test_capturas_de_cada_estado(qtbot: QtBot, tmp_path: Path, app: QApplication, preferencia: str) -> None:
    tema.instalar(app, preferencia)
    v = _ventana(qtbot, _modpack(tmp_path))
    v.resize(v.minimumSizeHint().expandedTo(v.minimumSize()))  # el tamaño más chico que admite la ventana
    v.show()
    qtbot.waitExposed(v)
    capturas = {"elegida": v.grab().toImage()}
    v.b_principal.click()  # analizar
    qtbot.waitUntil(lambda: v._hilo is None and v.ultimo_informe is not None, timeout=30000)  # pyright: ignore[reportPrivateUsage]
    capturas["analizada"] = v.grab().toImage()
    v.b_principal.click()  # traducir
    qtbot.waitUntil(lambda: v._hilo is None and "Listo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    capturas["traducida"] = v.grab().toImage()
    carpeta = Path(os.environ.get("MODPACKES_CAPTURAS", str(tmp_path / "capturas")))
    carpeta.mkdir(parents=True, exist_ok=True)
    for estado, imagen in capturas.items():
        assert _captura_util(imagen), estado
        assert imagen.save(str(carpeta / f"{preferencia}_{estado}.png"))
    assert capturas["elegida"] != capturas["traducida"]  # el estado se ve
    # El tamaño mínimo no corta el botón principal
    boton = v.b_principal
    assert boton.isVisible() and boton.width() >= boton.sizeHint().width() - 2

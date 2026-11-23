"""La ventana sin pantalla: textos ajenos sin HTML, accesibilidad básica, teclado y capturas de cada estado.

Un nombre de instancia viene del lanzador o del propio modpack (`instance.cfg`, `.mrpack`) y los mensajes de
error traen nombres de archivos del modpack: nada de eso debe dibujarse como HTML (H-036).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
    colores = {imagen.pixel(x, y) for x in range(0, imagen.width(), 7) for y in range(0, imagen.height(), 7)}
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
        assert imagen.save(str(carpeta / f"{preferencia}_{estado}.png"))
        assert _captura_util(imagen), estado
    assert capturas["elegida"] != capturas["traducida"]  # el estado se ve
    # En el tamaño mínimo el botón principal se ve entero o acortado con «…», nunca más angosto que eso (H-047)
    boton = v.b_principal
    assert boton.isVisible() and boton.width() >= boton.minimumSizeHint().width()


# --- ventana angosta: nada queda cortado (H-047) ---------------------------------------------------------------------

#: Arma la ventana con la plataforma real (con «offscreen» Qt no tiene fuentes y todo mide 1,7 veces más), fuera de
#: la pantalla, en el tamaño mínimo, con un nombre largo y todas las opciones: antes y después de analizar.
_MEDIR_ANCHOS = """
import json, os, sys, tempfile, time
from pathlib import Path
os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["TRADUCTOR_ES_PRUEBA_UI"] = "1"
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea
from tests import fabrica
from traductor_es.fuentes import vanilla
from traductor_es.fuentes.lanzadores import InstanciaEncontrada
from traductor_es.motores.simulador import Simulador
from traductor_es.ui import tema
from traductor_es.ui.ventana import Ventana
vanilla.raices_de_lanzadores = list
app = QApplication([])
tema.instalar(app, "claro")
salida = []
with tempfile.TemporaryDirectory() as tmp:
    juego = fabrica.prism(Path(tmp), "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench"}))
    nombre = "Un modpack con un nombre larguísimo que no entra en la barra lateral"
    v = Ventana(buscar_instancias=lambda: [InstanciaEncontrada("Prism Launcher", nombre, juego)],
                fabrica_motor=lambda *_a: Simulador())
    v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    v.lista.setCurrentRow(0)
    v.c_espana.setChecked(True)
    v.c_revisar.setChecked(True)
    v.resize(v.minimumSize())
    v.show()
    for estado in ("elegida", "analizada"):
        if estado == "analizada":
            v.b_principal.click()
            fin = time.monotonic() + 60
            while time.monotonic() < fin and not (v._hilo is None and v.ultimo_informe is not None):
                app.processEvents()
                time.sleep(0.02)
        app.processEvents()
        for a in v.findChildren(QScrollArea):
            if a.isVisible() and a.widget().minimumSizeHint().width() > a.viewport().width() + 1:
                salida.append([estado, a.viewport().width(), a.widget().minimumSizeHint().width()])
    v.close()
print(json.dumps(salida))
"""


@pytest.mark.skipif(sys.platform != "win32", reason="mide con las fuentes de Windows")
@pytest.mark.parametrize("escala", ["1", "2"])
def test_en_el_tamano_minimo_todo_cabe(escala: str) -> None:
    """Sin barra horizontal, lo que no cabía quedaba cortado: la cuarta tarjeta, el campo y los botones."""
    entorno = {**os.environ, "QT_SCALE_FACTOR": escala, "PYTHONUTF8": "1"}
    raiz = str(Path(__file__).resolve().parent.parent)
    proc = subprocess.run(
        [sys.executable, "-c", _MEDIR_ANCHOS, raiz],
        env=entorno,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []  # [estado, ancho del panel, ancho que pide]


def test_los_botones_secundarios_bajan_de_fila_si_no_caben(qtbot: QtBot, tmp_path: Path, app: QApplication) -> None:
    tema.instalar(app, "claro")
    v = _ventana(qtbot, _modpack(tmp_path), "Un modpack con un nombre larguísimo que no entra en la barra lateral")
    v.resize(2400, 900)
    v.show()
    qtbot.waitExposed(v)
    v.b_principal.click()  # analizar: aparece «Analizar de nuevo» junto al botón principal
    qtbot.waitUntil(lambda: v._hilo is None and v.ultimo_informe is not None, timeout=30000)  # pyright: ignore[reportPrivateUsage]
    QApplication.processEvents()
    assert v.fila_acciones.dos_filas is False
    v.resize(v.minimumSize())
    QApplication.processEvents()
    assert v.fila_acciones.dos_filas is True
    assert v.fila_acciones.minimumSizeHint().width() < v.b_principal.sizeHint().width()  # el principal se acorta
    assert v.b_principal.text() == v.b_principal.accessibleName()  # su texto queda entero para el lector
    v.resize(2400, 900)
    QApplication.processEvents()
    assert v.fila_acciones.dos_filas is False

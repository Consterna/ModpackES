"""Componentes de la interfaz: estados, señales, teclado, nombres accesibles y cambios de tema."""

from __future__ import annotations

import os
from collections.abc import Iterator

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from pytestqt.qtbot import QtBot

from traductor_es.ui import componentes as c
from traductor_es.ui import tema


@pytest.fixture(autouse=True)
def _tema_oscuro(qtbot: QtBot) -> Iterator[tema.Tema]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    t = tema.instalar(app, "oscuro")
    yield t
    t.elegir("oscuro")


def test_tarjeta_elegible_con_raton_y_teclado(qtbot: QtBot) -> None:
    t = c.Tarjeta(elegible=True)
    qtbot.addWidget(t)
    with qtbot.waitSignal(t.pulsada):
        QTest.mouseClick(t, Qt.MouseButton.LeftButton)
    with qtbot.waitSignal(t.pulsada):
        QTest.keyClick(t, Qt.Key.Key_Return)
    assert not t.activa
    t.fijar_activa(True)
    assert t.activa and t.property("tipo") == "tarjeta"


def test_tarjeta_de_instancia(qtbot: QtBot) -> None:
    t = c.TarjetaInstancia("Valle Encantado", "Prism Launcher", r"C:\x\minecraft")
    qtbot.addWidget(t)
    assert "leyendo" in t.e_detalle.text()
    t.fijar_datos("1.20.1", "neoforge", True)
    assert t.e_detalle.text() == "1.20.1 · NeoForge · Prism Launcher"
    assert t.e_estado.text() == "✓ Traducido" and t.e_estado.property("tipo") == "acento"
    t.fijar_datos(None, None, False)
    assert t.e_detalle.text().startswith("versión desconocida") and t.e_estado.text() == "Sin traducir"
    assert "Sin traducir" in t.accessibleDescription()
    assert t.coincide("valle") and t.coincide("PRISM") and not t.coincide("atm10") and t.coincide("  ")


def test_pasos(qtbot: QtBot) -> None:
    p = c.Pasos(["Motor", "Analizar", "Traducir", "Listo"])
    qtbot.addWidget(p)
    p.fijar(2)
    assert [p.estado(i) for i in range(4)] == ["hecho", "hecho", "actual", "pendiente"]
    assert p.accessibleName() == "Paso 3 de 4: Traducir"
    p.fijar(99)
    assert p.estado(3) == "hecho" and "terminado" in p.accessibleName()


def test_tarjeta_de_grupo(qtbot: QtBot) -> None:
    g = c.TarjetaGrupo("libros", "Libros", "book-open")
    qtbot.addWidget(g)
    assert g.incluido and g.activa and g.e_numero.text() == "—"
    g.fijar_cantidad(1234, "3 de Patchouli")
    assert g.e_numero.text() == "1.234" and g.e_detalle.text() == "3 de Patchouli"
    recibidos: list[tuple[str, bool]] = []

    def anotar(grupo: str, si: bool) -> None:
        recibidos.append((grupo, si))

    g.cambiado.connect(anotar)
    g.casilla.setChecked(False)
    assert recibidos == [("libros", False)] and not g.activa and not g.incluido


def test_aviso_con_accion_y_cierre(qtbot: QtBot) -> None:
    a = c.Aviso()
    qtbot.addWidget(a)
    assert a.isHidden()
    hechas: list[int] = []
    a.mostrar("Falta la clave", "aviso", ("Configurar", lambda: hechas.append(1)))
    assert not a.isHidden() and a.property("tipo") == "aviso-aviso"
    assert a.b_accion.text() == "Configurar" and not a.b_accion.isHidden()
    a.b_accion.click()
    assert hechas == [1]
    with qtbot.waitSignal(a.cerrado):
        a.b_cerrar.click()
    assert a.isHidden()
    a.mostrar("Algo", "inventado")
    assert a.tipo == "info" and a.b_accion.isHidden()


def test_plegable(qtbot: QtBot) -> None:
    contenido = QLabel("adentro")
    p = c.Plegable("Opciones avanzadas", contenido)
    qtbot.addWidget(p)
    p.fijar_resumen("español latino · revisión apagada")
    assert not p.abierta and contenido.isHidden()
    assert "revisión apagada" in p.cabecera.text()
    estados: list[bool] = []

    def anotar(abierta: bool) -> None:
        estados.append(abierta)

    p.alternada.connect(anotar)
    p.cabecera.click()
    assert estados == [True] and not contenido.isHidden() and p.cabecera.text() == "Opciones avanzadas"
    assert "abierta" in p.cabecera.accessibleName()


def test_boton_principal(qtbot: QtBot) -> None:
    b = c.BotonPrincipal()
    qtbot.addWidget(b)
    b.fijar("Traducir 295 textos", "languages")
    assert b.property("tipo") == "primario" and b.accessibleName() == "Traducir 295 textos" and not b.icon().isNull()


def test_un_widget_destruido_no_rompe_el_cambio_de_tema(qtbot: QtBot, _tema_oscuro: tema.Tema) -> None:
    """Regresión de diseño: los íconos que siguen al tema no pueden quedar conectados a widgets borrados."""
    efimero = c.Pasos(["A", "B"])
    efimero.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    vivo = c.BotonPrincipal()
    qtbot.addWidget(vivo)
    vivo.fijar("Analizar", "search")
    _tema_oscuro.elegir("claro")  # no tiene que fallar por el widget que ya no existe
    assert tema.actual() is tema.CLARO and not vivo.icon().isNull()

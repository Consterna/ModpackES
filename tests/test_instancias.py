"""La barra lateral: datos de cada instancia leídos en segundo plano, búsqueda y elección."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from traductor_es.ui import instancias, tema

from . import fabrica


@pytest.fixture(autouse=True)
def _tema(qtbot: QtBot) -> Iterator[None]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    tema.instalar(app, "oscuro")
    yield


def test_leer_datos(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "neoforge")
    assert instancias.leer_datos(str(juego)) == ("1.20.1", "neoforge", False)
    assert instancias.leer_datos(str(juego.parent)) == ("1.20.1", "neoforge", False)  # carpeta de la instancia
    pack = juego / "resourcepacks" / "Traduccion_ES" / "pack.mcmeta"
    pack.parent.mkdir(parents=True)
    pack.write_text("{}", encoding="utf-8")
    assert instancias.leer_datos(str(juego))[2] is True
    assert instancias.leer_datos(str(tmp_path / "no-existe")) == (None, None, None)


def test_lector_avisa_cada_instancia_en_segundo_plano(qtbot: QtBot, tmp_path: Path) -> None:
    a = fabrica.prism(tmp_path / "a", "1.20.1", "forge")
    b = fabrica.prism(tmp_path / "b", "1.21.1", "fabric")
    lector = instancias.Lector([str(a), str(b), str(tmp_path / "rota")])
    recibidos: dict[str, object] = {}

    def anotar(carpeta: str, datos: object) -> None:
        recibidos[carpeta] = datos

    lector.leido.connect(anotar)
    hilo = lector.iniciar()
    qtbot.waitUntil(lambda: len(recibidos) == 3, timeout=10000)
    hilo.join(5)
    assert recibidos[str(b)] == ("1.21.1", "fabric", False) and recibidos[str(tmp_path / "rota")] == (None, None, None)
    assert lector.terminado.is_set()


def test_lista_busca_elige_y_muestra_los_datos(qtbot: QtBot) -> None:
    lista = instancias.ListaInstancias()
    qtbot.addWidget(lista)
    assert not lista.vacio.isHidden() and lista.carpeta() is None
    elegidas: list[str] = []

    def anotar(carpeta: str) -> None:
        elegidas.append(carpeta)

    lista.elegida.connect(anotar)
    valle = lista.agregar("Valle Encantado", "Prism Launcher", r"C:\a")
    atm = lista.agregar("All the Mods 10", "CurseForge", r"C:\b")
    assert lista.count() == 2 and lista.vacio.isHidden()
    lista.setCurrentRow(1)
    assert lista.carpeta() == r"C:\b" and atm.activa and not valle.activa
    lista.elegir(atm)  # la misma: no vuelve a avisar
    lista.al_leer(r"C:\b", ("1.21.1", "neoforge", True))
    assert atm.e_detalle.text() == "1.21.1 · NeoForge · CurseForge" and atm.e_estado.text() == "✓ Traducido"
    lista.e_buscar.setText("valle")
    assert not valle.isHidden() and atm.isHidden() and lista.vacio.isHidden()
    lista.e_buscar.setText("nada que coincida")
    assert not lista.vacio.isHidden() and "Ninguna" in lista.vacio.text()
    lista.limpiar()
    assert lista.count() == 0 and lista.carpeta() is None
    assert elegidas == [r"C:\b", ""]

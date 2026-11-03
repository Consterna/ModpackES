"""La ventana sin pantalla (Qt offscreen) y la exportación."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pytestqt.qtbot import QtBot

from traductor_es.fuentes import vanilla
from traductor_es.fuentes.lanzadores import InstanciaEncontrada
from traductor_es.motores.base import Motor
from traductor_es.motores.simulador import Simulador
from traductor_es.salida import exportar
from traductor_es.ui.app import main
from traductor_es.ui.ventana import Ventana

from . import fabrica


@pytest.fixture(autouse=True)
def _entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    def ninguna() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", ninguna)
    monkeypatch.setenv("TRADUCTOR_ES_PRUEBA_UI", "1")  # sin cuadros de diálogo


def _modpack(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench"}))
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text('{ title: "Getting Started" }', encoding="utf-8")
    script = juego / "kubejs" / "server_scripts" / "s.js"
    script.parent.mkdir(parents=True)
    script.write_text("player.tell('Welcome to the pack')\n", encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _ventana(qtbot: QtBot, juego: Path) -> Ventana:
    def instancias() -> list[InstanciaEncontrada]:
        return [InstanciaEncontrada("Prism Launcher", "Prueba", juego)]

    def simulador(_clave: str, _modelo: str) -> Motor:
        return Simulador()

    v = Ventana(buscar_instancias=instancias, fabrica_motor=simulador)
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    return v


def test_analizar_traducir_y_restaurar(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path)
    v = _ventana(qtbot, juego)
    assert v.lista.count() == 1 and v.carpeta() == str(juego)
    v.b_analizar.click()
    qtbot.waitUntil(lambda: v._hilo is None and v.ultimo_informe is not None, timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert v.tabla.rowCount() == 3 and "Costo estimado" in v.costo.text()
    assert not (juego / "resourcepacks").exists()  # analizar no escribe
    v.b_traducir.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Listo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert "«ES» Welcome to the pack" in (juego / "kubejs" / "server_scripts" / "s.js").read_text("utf-8")
    assert (juego / "resourcepacks" / "Traduccion_ES" / "pack.mcmeta").is_file()
    assert "lang:es_mx" in (juego / "options.txt").read_text("utf-8")
    v.b_restaurar.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Restaurados" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert (juego / "kubejs" / "server_scripts" / "s.js").read_text("utf-8") == "player.tell('Welcome to the pack')\n"


def test_sin_instancia_avisa(qtbot: QtBot) -> None:
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    v.b_analizar.click()
    assert "Elige primero una instancia" in v.log.toPlainText()


def test_error_se_muestra_y_libera_la_ventana(qtbot: QtBot, tmp_path: Path) -> None:
    def rota() -> list[InstanciaEncontrada]:
        return [InstanciaEncontrada("Prism Launcher", "Rota", tmp_path / "no-existe")]

    v = Ventana(buscar_instancias=rota)
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    v.b_analizar.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Se detuvo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert "No encuentro" in v.log.toPlainText() and v.b_analizar.isEnabled()


def test_exportar_pack_y_kit(tmp_path: Path) -> None:
    juego = _modpack(tmp_path)
    with pytest.raises(ValueError):
        exportar.exportar_pack(juego, tmp_path / "x.zip")
    assert main(["--autoprueba", str(juego), str(tmp_path / "auto.json")]) == 0
    datos = json.loads((tmp_path / "auto.json").read_text("utf-8"))
    assert datos["icono"] is True
    assert datos["minecraft"] == "1.20.1" and {m["grupo"] for m in datos["modulos"]} == {"mods", "misiones", "scripts"}
    from traductor_es.__main__ import main as cli

    assert cli(["traducir", str(juego), "--simular"]) == 0
    n = exportar.exportar_pack(juego, tmp_path / "Traduccion_ES.zip")
    with zipfile.ZipFile(tmp_path / "Traduccion_ES.zip") as z:
        assert "pack.mcmeta" in z.namelist() and n == len(z.namelist())
    exportar.exportar_kit_servidor(juego, tmp_path / "kit.zip")
    with zipfile.ZipFile(tmp_path / "kit.zip") as z:
        nombres = set(z.namelist())
        assert {"LEEME.txt", "Traduccion_ES.zip", "config/ftbquests/quests/chapters/a.snbt"} <= nombres
        assert "kubejs/server_scripts/s.js" in nombres
        assert "«ES» Getting Started" in z.read("config/ftbquests/quests/chapters/a.snbt").decode("utf-8")


def test_probar_clave_no_congela_y_muestra_modelos(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from traductor_es import configuracion
    from traductor_es.motores.gemini import Gemini

    monkeypatch.setattr(configuracion, "leer_clave", lambda: "clave")
    modelos = SimpleNamespace(
        list=lambda: [SimpleNamespace(name="models/gemini-9-flash", supported_actions=["generateContent"])]
    )

    def fabrica(clave: str, modelo: str) -> Motor:
        return Gemini(clave, modelo, cliente=SimpleNamespace(models=modelos))

    v = Ventana(buscar_instancias=list, fabrica_motor=fabrica)
    qtbot.addWidget(v)
    v.b_probar.click()
    qtbot.waitUntil(lambda: "modelos disponibles" in v.log.toPlainText(), timeout=10000)
    assert [v.c_modelo.itemText(i) for i in range(v.c_modelo.count())] == ["gemini-9-flash"]
    assert v.b_probar.isEnabled()


def test_proceso_conecta_cancelar_y_espera_al_motor(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from traductor_es.motores.gemini import Gemini
    from traductor_es.proceso import Proceso

    juego = _modpack(tmp_path)
    mensajes: list[str] = []
    motor = Gemini("clave", cliente=SimpleNamespace())
    with Proceso(juego, motor, registro=mensajes.append) as p:
        assert motor.cancelar is p.traductor.cancelar
    motor.al_esperar("JOB_STATE_RUNNING")
    assert mensajes[-1] == "Esperando a Google (Batch API): procesando"


def test_cambiar_de_instancia_borra_el_analisis_anterior(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path / "a")
    otro = _modpack(tmp_path / "b")

    def instancias() -> list[InstanciaEncontrada]:
        return [InstanciaEncontrada("Prism Launcher", "A", juego), InstanciaEncontrada("Prism Launcher", "B", otro)]

    v = Ventana(buscar_instancias=instancias)
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    v.b_analizar.click()
    qtbot.waitUntil(lambda: v._hilo is None and v.ultimo_informe is not None, timeout=30000)  # pyright: ignore[reportPrivateUsage]
    v.lista.setCurrentRow(1)
    assert v.ultimo_informe is None and v.tabla.rowCount() == 0 and v.costo.text() == ""

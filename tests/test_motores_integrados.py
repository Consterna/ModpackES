"""Motores en la app: una clave por motor, costo según el motor, ventana y línea de comandos."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import keyring
import pytest
from keyring.backend import KeyringBackend
from pytestqt.qtbot import QtBot

from traductor_es import configuracion
from traductor_es.__main__ import main as cli
from traductor_es.fuentes import vanilla
from traductor_es.fuentes.lanzadores import InstanciaEncontrada
from traductor_es.motores import fabrica as fabrica_motores
from traductor_es.motores.base import ErrorFatal, Motor
from traductor_es.motores.compatible import Compatible
from traductor_es.motores.gemini import Gemini
from traductor_es.motores.simulador import Simulador
from traductor_es.proceso import Informe, InformeModulo
from traductor_es.ui.ventana import Ventana

from . import fabrica


class EnMemoria(KeyringBackend):
    priority = 1  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]

    def __init__(self) -> None:
        super().__init__()
        self.datos: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.datos.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.datos[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.datos.pop((service, username), None)


@pytest.fixture
def almacen() -> Iterator[EnMemoria]:
    anterior = keyring.get_keyring()
    propio = EnMemoria()
    keyring.set_keyring(propio)
    yield propio
    keyring.set_keyring(anterior)


@pytest.fixture(autouse=True)
def _sin_lanzadores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
    monkeypatch.setenv("TRADUCTOR_ES_PRUEBA_UI", "1")


def test_cada_motor_tiene_su_clave_y_la_de_gemini_no_cambia_de_lugar(
    almacen: EnMemoria, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuracion.guardar_clave("clave-de-gemini-1234")
    configuracion.guardar_clave("clave-de-openrouter-5678", "openrouter")
    assert almacen.datos == {
        ("traductor-es", "gemini"): "clave-de-gemini-1234",  # el mismo lugar que en la v2.0
        ("traductor-es", "motor:openrouter"): "clave-de-openrouter-5678",
    }
    assert configuracion.leer_clave("openrouter") == "clave-de-openrouter-5678"
    monkeypatch.setenv("MODPACKES_CLAVE_OPENROUTER", "desde-variable-9999")
    assert configuracion.leer_clave("openrouter") == "desde-variable-9999"
    configuracion.olvidar_clave("openrouter")
    assert ("traductor-es", "motor:openrouter") not in almacen.datos and configuracion.leer_clave() is not None


def test_fabrica_crea_cada_motor_y_pide_lo_que_falta() -> None:
    assert isinstance(fabrica_motores.crear("gemini", "k", "gemini-3.8-flash"), Gemini)
    local = fabrica_motores.crear("ollama", None, "qwen3:8b")
    assert isinstance(local, Compatible) and local.direccion == "http://localhost:11434/v1"
    local.cerrar()
    with pytest.raises(ErrorFatal, match="clave de Gemini"):
        fabrica_motores.crear("gemini", None, "x")
    with pytest.raises(ErrorFatal, match="clave de OpenRouter"):
        fabrica_motores.crear("openrouter", "", "x")
    assert fabrica_motores.necesita_clave("deepseek") and not fabrica_motores.necesita_clave("lmstudio")


def test_costo_segun_el_motor() -> None:
    informe = Informe([InformeModulo("mods", "Mods", "", 10, 10, 35_000)])
    assert informe.costo("gemini-3.8-flash", False) is not None
    assert informe.costo("qwen3:8b", False, "ollama") == 0.0
    assert informe.costo("gemini-3.8-flash", False, "openrouter") is None  # precio del proveedor: desconocido


def _modpack(tmp_path: Path, texto: str) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1")
    script = juego / "kubejs" / "server_scripts" / "s.js"
    script.parent.mkdir(parents=True)
    script.write_text(f"player.tell('{texto}')\n", encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def test_ventana_con_un_motor_local(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path, "Plant the magic beans")
    pedidos: list[tuple[str, str | None, str, str]] = []
    motor = Simulador()

    def crear(motor_id: str, clave: str | None, modelo: str, direccion: str) -> Motor:
        pedidos.append((motor_id, clave, modelo, direccion))
        return motor

    v = Ventana(buscar_instancias=lambda: [InstanciaEncontrada("Prism Launcher", "P", juego)], fabrica_motor=crear)
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    v.c_motor.setCurrentIndex(v.c_motor.findData("ollama"))
    assert not v.c_lotes.isEnabled() and "tu PC" in v.etiqueta_clave.text() and not v.b_clave.isEnabled()
    assert v.e_direccion.text() == "http://localhost:11434/v1" and v.e_direccion.isReadOnly()
    v.c_modelo.setCurrentText("qwen3:8b")
    v.b_analizar.click()
    qtbot.waitUntil(lambda: v._hilo is None and v.ultimo_informe is not None, timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert "Sin costo" in v.costo.text()
    v.b_traducir.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Listo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert pedidos == [("ollama", None, "qwen3:8b", "http://localhost:11434/v1")]
    preferencias = configuracion.leer_preferencias()
    assert preferencias["motor"] == "ollama" and preferencias["modelos"]["ollama"] == "qwen3:8b"
    v.c_motor.setCurrentIndex(v.c_motor.findData("gemini"))
    assert v.c_lotes.isEnabled() and v.c_modelo.currentText() != "qwen3:8b"
    v.c_motor.setCurrentIndex(v.c_motor.findData("ollama"))
    assert v.c_modelo.currentText() == "qwen3:8b"  # cada motor recuerda su modelo


def test_ventana_avisa_si_falta_lo_necesario(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path, "Check your mailbox")
    v = Ventana(buscar_instancias=lambda: [InstanciaEncontrada("Prism Launcher", "P", juego)])
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    v.c_motor.setCurrentIndex(v.c_motor.findData("personalizado"))
    assert not v.e_direccion.isReadOnly()
    v.e_direccion.setText("")
    v.c_modelo.setCurrentText("m")
    v.lanzar("traducir")
    assert "Falta la dirección" in v.log.toPlainText() and v._hilo is None  # pyright: ignore[reportPrivateUsage]


class _Servidor(BaseHTTPRequestHandler):
    recibidos: list[dict[str, Any]] = []  # noqa: RUF012 (se comparte a propósito entre pedidos)

    def do_POST(self) -> None:
        pedido = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Servidor.recibidos.append(pedido)
        textos: dict[str, Any] = json.loads(pedido["messages"][1]["content"])["textos"]
        # Cada texto llega solo o como {"texto", "contexto"} cuando trae pista
        solo = {i: str(cast(dict[str, Any], t)["texto"] if isinstance(t, dict) else t) for i, t in textos.items()}
        contenido = json.dumps({i: f"Traducido: {t}" for i, t in solo.items()}, ensure_ascii=False)
        self._responder({"choices": [{"message": {"content": contenido}}]})

    def do_GET(self) -> None:
        self._responder({"data": [{"id": "modelo-local"}]})

    def _responder(self, datos: dict[str, Any]) -> None:
        cuerpo = json.dumps(datos).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def servidor() -> Iterator[str]:
    _Servidor.recibidos = []
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
    hilo = threading.Thread(target=s.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{s.server_address[1]}/v1"
    s.shutdown()
    s.server_close()
    hilo.join()


def test_linea_de_comandos_de_punta_a_punta_con_un_servidor_real(
    tmp_path: Path, servidor: str, capsys: pytest.CaptureFixture[str]
) -> None:
    juego = _modpack(tmp_path, "Feed the chickens every morning")
    base = ["--motor", "personalizado", "--direccion", servidor]
    assert cli(["modelos", *base]) == 0
    assert "modelo-local" in capsys.readouterr().out
    assert cli(["traducir", str(juego), *base, "--modelo", "modelo-local", "--contexto", "granja"]) == 0
    script = (juego / "kubejs" / "server_scripts" / "s.js").read_text("utf-8")
    assert script == "player.tell('Traducido: Feed the chickens every morning')\n"
    assert _Servidor.recibidos[0]["model"] == "modelo-local"
    assert "granja" in _Servidor.recibidos[0]["messages"][0]["content"]


def test_linea_de_comandos_rechaza_combinaciones_imposibles(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    juego = _modpack(tmp_path, "Water the crops")
    assert cli(["traducir", str(juego), "--motor", "ollama", "--modelo", "m", "--lotes"]) == 1
    assert "--lotes solo funciona con Gemini" in capsys.readouterr().out
    assert cli(["traducir", str(juego), "--motor", "openrouter", "--modelo", "m"]) == 1
    assert "MODPACKES_CLAVE_OPENROUTER" in capsys.readouterr().out
    assert cli(["analizar", str(juego), "--motor", "ollama", "--modelo", "m"]) == 0
    assert "US$ 0.00" in capsys.readouterr().out


def test_el_modelo_escrito_se_recuerda_al_cambiar_de_motor_sin_usarlo(qtbot: QtBot) -> None:
    """Regresión: lo escrito para un motor se perdía si se cambiaba de motor antes de analizar o traducir."""
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    v.c_motor.setCurrentIndex(v.c_motor.findData("ollama"))
    v.c_modelo.setCurrentText("qwen3:8b")
    v.c_motor.setCurrentIndex(v.c_motor.findData("personalizado"))
    v.e_direccion.setText("http://127.0.0.1:9999/v1")
    v.c_motor.setCurrentIndex(v.c_motor.findData("gemini"))
    v.c_motor.setCurrentIndex(v.c_motor.findData("ollama"))
    assert v.c_modelo.currentText() == "qwen3:8b"
    v.c_motor.setCurrentIndex(v.c_motor.findData("personalizado"))
    assert v.e_direccion.text() == "http://127.0.0.1:9999/v1"

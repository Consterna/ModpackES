"""Motor compatible con OpenAI: con un transporte falso de httpx y con un servidor HTTP real en el PC."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from traductor_es.motores.base import Cancelado, Entrada, ErrorFatal, Lote
from traductor_es.motores.compatible import PERFILES, Compatible

Armado = tuple[Compatible, list[httpx.Request], list[float]]


def lote(*textos: str) -> Lote:
    return Lote(tuple(Entrada(str(i), t) for i, t in enumerate(textos)), "mision", "español", {}, "Granja")


def respuesta(contenido: str | dict[str, str], codigo: int = 200) -> httpx.Response:
    texto = contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False)
    return httpx.Response(codigo, json={"choices": [{"message": {"role": "assistant", "content": texto}}]})


def error(codigo: int, mensaje: str = "", **cabeceras: str) -> httpx.Response:
    return httpx.Response(codigo, json={"error": {"message": mensaje}}, headers=cabeceras)


@pytest.fixture
def armar() -> Iterator[Callable[..., Armado]]:
    abiertos: list[Compatible] = []

    def crear(*respuestas: httpx.Response | Exception, perfil: str = "openrouter", **kw: Any) -> Armado:
        pedidos: list[httpx.Request] = []
        esperas: list[float] = []
        cola = list(respuestas)

        def manejar(pedido: httpx.Request) -> httpx.Response:
            pedidos.append(pedido)
            r = cola.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        cliente = httpx.Client(transport=httpx.MockTransport(manejar))
        m = Compatible(PERFILES[perfil], kw.pop("modelo", "modelo-x"), cliente=cliente, esperar=esperas.append, **kw)
        abiertos.append(m)
        return m, pedidos, esperas

    yield crear
    for m in abiertos:
        m.cerrar()


def test_pide_con_esquema_e_instrucciones_comunes(armar: Callable[..., Armado]) -> None:
    m, pedidos, _ = armar(respuesta({"0": "Hola", "1": "Adiós"}), clave="sk-abc")
    assert m.traducir_lote(lote("Hello", "Bye")) == {"0": "Hola", "1": "Adiós"}
    cuerpo = json.loads(pedidos[0].content)
    assert pedidos[0].url == "https://openrouter.ai/api/v1/chat/completions"
    assert pedidos[0].headers["authorization"] == "Bearer sk-abc"
    assert cuerpo["model"] == "modelo-x" and cuerpo["provider"] == {"require_parameters": True}
    esquema = cuerpo["response_format"]["json_schema"]["schema"]
    assert esquema["required"] == ["0", "1"] and esquema["additionalProperties"] is False
    sistema, usuario = cuerpo["messages"]
    assert "⟦0⟧" in sistema["content"] and "Granja" in sistema["content"] and json.loads(usuario["content"])
    assert m.nombre == "openrouter:modelo-x"


def test_deepseek_usa_json_simple_y_sin_clave_no_manda_cabecera(armar: Callable[..., Armado]) -> None:
    m, pedidos, _ = armar(respuesta({"0": "Hola"}), perfil="deepseek")
    m.traducir_lote(lote("Hello"))
    assert json.loads(pedidos[0].content)["response_format"] == {"type": "json_object"}
    assert "authorization" not in pedidos[0].headers


def test_si_no_admite_esquema_pasa_a_json_simple(armar: Callable[..., Armado]) -> None:
    m, pedidos, _ = armar(error(400, "response_format json_schema is not supported"), respuesta({"0": "Hola"}))
    assert m.traducir_lote(lote("Hello")) == {"0": "Hola"}
    assert json.loads(pedidos[1].content)["response_format"] == {"type": "json_object"}


def test_un_400_que_no_es_del_formato_no_cambia_el_modo(armar: Callable[..., Armado]) -> None:
    m, pedidos, _ = armar(error(400, "context length exceeded"), respuesta({"0": "Hola"}))
    assert m.traducir_lote(lote("Hello")) == {}  # el traductor lo reintenta en lotes más chicos
    m.traducir_lote(lote("Hello"))
    assert json.loads(pedidos[1].content)["response_format"]["type"] == "json_schema"


def test_reintenta_429_y_5xx_respetando_retry_after(armar: Callable[..., Armado]) -> None:
    m, _, esperas = armar(error(429, "slow down", **{"retry-after": "7"}), error(503), respuesta({"0": "Hola"}))
    assert m.traducir_lote(lote("Hello")) == {"0": "Hola"}
    assert esperas == [7.0, 14.0]


def test_429_persistente_y_errores_de_clave_o_modelo_son_fatales(armar: Callable[..., Armado]) -> None:
    m, _, _ = armar(*(error(429) for _ in range(3)), reintentos=3)
    with pytest.raises(ErrorFatal, match="429"):
        m.traducir_lote(lote("Hello"))
    for codigo, texto in ((401, "clave"), (402, "saldo"), (404, "modelo")):
        m, _, _ = armar(error(codigo))
        with pytest.raises(ErrorFatal, match=texto):
            m.traducir_lote(lote("Hello"))


def test_cortes_de_red_y_respuestas_raras(armar: Callable[..., Armado]) -> None:
    m, _, _ = armar(httpx.ReadTimeout("lento"), respuesta('```json\n{"0": "Hola"}\n```'))
    assert m.traducir_lote(lote("Hello")) == {"0": "Hola"}
    m, _, _ = armar(httpx.Response(200, json={"choices": []}))
    assert m.traducir_lote(lote("Hello")) == {}
    m, _, _ = armar(respuesta("esto no es JSON"))
    assert m.traducir_lote(lote("Hello")) == {}


def test_servidor_local_apagado_avisa_sin_reintentar(armar: Callable[..., Armado]) -> None:
    m, pedidos, _ = armar(httpx.ConnectError("rechazada"), perfil="ollama")
    with pytest.raises(ErrorFatal, match="Ollama"):
        m.traducir_lote(lote("Hello"))
    assert len(pedidos) == 1


def test_cancelar_corta_antes_de_pedir(armar: Callable[..., Armado]) -> None:
    m, pedidos, _ = armar(respuesta({"0": "Hola"}))
    m.cancelar = threading.Event()
    m.cancelar.set()
    with pytest.raises(Cancelado):
        m.traducir_lote(lote("Hello"))
    assert pedidos == []


def test_faltan_direccion_o_modelo() -> None:
    with pytest.raises(ErrorFatal, match="dirección"):
        Compatible(PERFILES["personalizado"], "m")
    with pytest.raises(ErrorFatal, match="modelo"):
        Compatible(PERFILES["ollama"], " ")


def test_listar_modelos(armar: Callable[..., Armado]) -> None:
    lista = httpx.Response(200, json={"data": [{"id": "qwen3:8b"}, {"id": "llama3.2"}, {"nada": 1}]})
    m, pedidos, _ = armar(lista, perfil="ollama")
    assert m.listar_modelos() == ["llama3.2", "qwen3:8b"]
    assert pedidos[0].url == "http://localhost:11434/v1/models"
    m, _, _ = armar(error(401, "bad key"))
    with pytest.raises(ErrorFatal, match="clave"):
        m.listar_modelos()


def test_con_un_servidor_http_real() -> None:
    recibidos: list[dict[str, Any]] = []

    class Falso(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            largo = int(self.headers["Content-Length"])
            recibidos.append(json.loads(self.rfile.read(largo)))
            ids = recibidos[-1]["response_format"]["json_schema"]["schema"]["required"]
            contenido = json.dumps({i: f"traducido {i}" for i in ids})
            cuerpo = json.dumps({"choices": [{"message": {"content": contenido}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        direccion = f"http://127.0.0.1:{servidor.server_address[1]}/v1"
        m = Compatible(PERFILES["personalizado"], "local", direccion=direccion)
        try:
            assert m.traducir_lote(lote("Hello", "World")) == {"0": "traducido 0", "1": "traducido 1"}
        finally:
            m.cerrar()
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join()
    assert recibidos[0]["model"] == "local"

"""Casos límite de los motores: respuestas raras o rotas, errores de red, cancelación y creación con datos faltantes."""

import json
import threading
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from traductor_es.motores import fabrica
from traductor_es.motores.base import Cancelado, Entrada, ErrorFatal, Lote
from traductor_es.motores.compatible import PERFILES, Compatible
from traductor_es.motores.instrucciones import interpretar, sistema, usuario
from traductor_es.motores.simulador import Simulador

SUAVE = settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)


def lote(*textos: str, tarea: str = "traducir") -> Lote:
    return Lote(tuple(Entrada(str(i), t) for i, t in enumerate(textos)), "ui", "español", {}, "", tarea)


@pytest.fixture
def armar() -> Iterator[Callable[..., tuple[Compatible, list[httpx.Request], list[float]]]]:
    abiertos: list[Compatible] = []

    def crear(
        *respuestas: httpx.Response | Exception, **kw: Any
    ) -> tuple[Compatible, list[httpx.Request], list[float]]:
        pedidos: list[httpx.Request] = []
        esperas: list[float] = []
        cola = list(respuestas)

        def manejar(pedido: httpx.Request) -> httpx.Response:
            pedidos.append(pedido)
            r = cola.pop(0) if len(cola) > 1 else cola[0]
            if isinstance(r, Exception):
                raise r
            return r

        cliente = httpx.Client(transport=httpx.MockTransport(manejar))
        m = Compatible(PERFILES["openrouter"], "modelo", cliente=cliente, esperar=esperas.append, clave="sk-x", **kw)
        abiertos.append(m)
        return m, pedidos, esperas

    yield crear
    for m in abiertos:
        m.cerrar()


# ------------------------------------------------------------------ interpretar
@SUAVE
@given(st.one_of(st.none(), st.text(max_size=200)))
def test_interpretar_nunca_falla_y_siempre_devuelve_textos(texto: str | None) -> None:
    resultado = interpretar(texto)
    assert isinstance(resultado, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in resultado.items())


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ('{"0": "Hola ñ"}', {"0": "Hola ñ"}),
        ('```json\n{"0": "Hola"}\n```', {"0": "Hola"}),
        ('```\n{"0": "Hola"}\n```', {"0": "Hola"}),
        ('  {"0": "Hola", "1": 5, "2": null, "3": ["x"]}  ', {"0": "Hola"}),
        ('{"0": "con \\"comillas\\" y \\u00f1"}', {"0": 'con "comillas" y ñ'}),
        ("[]", {}),
        ('"solo texto"', {}),
        ("", {}),
        ("no es json", {}),
        ('{"0": "cortado', {}),
    ],
)
def test_interpretar_respuestas_tipicas_y_rotas(crudo: str, esperado: dict[str, str]) -> None:
    assert interpretar(crudo) == esperado


# ------------------------------------------------------------------ motor compatible
@pytest.mark.parametrize(
    "cuerpo",
    [  # pyright: ignore[reportUnknownArgumentType]
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": None}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": ["no", "texto"]}}]},
        {"choices": [{"message": {"content": 5}}]},
        {"choices": "no es lista"},
        [1, 2, 3],
        "texto plano",
    ],
)
def test_respuesta_con_forma_inesperada_no_rompe(armar: Callable[..., Any], cuerpo: object) -> None:
    m, _, _ = armar(httpx.Response(200, json=cuerpo))
    assert m.traducir_lote(lote("Hello there")) == {}


def test_respuesta_que_no_es_json(armar: Callable[..., Any]) -> None:
    m, _, _ = armar(httpx.Response(200, content=b"<html>Bad gateway</html>"))
    assert m.traducir_lote(lote("Hello there")) == {}


def test_error_de_servidor_persistente_devuelve_vacio_tras_reintentar(armar: Callable[..., Any]) -> None:
    m, pedidos, esperas = armar(httpx.Response(503, text="caído"), reintentos=3)
    assert m.traducir_lote(lote("Hello there")) == {}
    assert len(pedidos) == 3 and len(esperas) == 2  # esperó entre intentos, no tras el último


@pytest.mark.parametrize(
    "excepcion", [httpx.ReadTimeout("lento"), httpx.RemoteProtocolError("cortado"), httpx.WriteError("x")]
)
def test_fallos_de_red_se_reintentan_y_no_revientan(armar: Callable[..., Any], excepcion: Exception) -> None:
    m, pedidos, _ = armar(excepcion, reintentos=2)
    assert m.traducir_lote(lote("Hello there")) == {}
    assert len(pedidos) == 2


def test_retry_after_basura_no_rompe(armar: Callable[..., Any]) -> None:
    ok = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"0": "Hola"})}}]})
    m, _, _ = armar(httpx.Response(429, headers={"retry-after": "soon"}), ok, reintentos=3)
    assert m.traducir_lote(lote("Hello there")) == {"0": "Hola"}


def test_cancelar_corta_antes_de_pedir(armar: Callable[..., Any]) -> None:
    m, pedidos, _ = armar(httpx.Response(200, json={}))
    m.cancelar = threading.Event()
    m.cancelar.set()
    with pytest.raises(Cancelado):
        m.traducir_lote(lote("Hello there"))
    assert pedidos == []


@pytest.mark.parametrize(("codigo", "texto"), [(401, "clave"), (403, "clave"), (402, "saldo"), (404, "modelo")])
def test_errores_fatales_dicen_que_hacer(armar: Callable[..., Any], codigo: int, texto: str) -> None:
    m, pedidos, _ = armar(httpx.Response(codigo, json={"error": {"message": "x"}}))
    with pytest.raises(ErrorFatal, match=texto):
        m.traducir_lote(lote("Hello there"))
    assert len(pedidos) == 1  # no se insiste cuando reintentar no sirve


def test_el_pedido_lleva_el_texto_con_utf8_intacto(armar: Callable[..., Any]) -> None:
    m, pedidos, _ = armar(httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}))
    m.traducir_lote(lote("Ñandú ¡sí! 日本語 😀 ⟦0⟧"))
    cuerpo = json.loads(pedidos[0].content.decode("utf-8"))
    assert "Ñandú ¡sí! 日本語 😀 ⟦0⟧" in cuerpo["messages"][1]["content"]


# ------------------------------------------------------------------ instrucciones, simulador, fábrica
def test_instrucciones_para_cada_ambito_y_tarea() -> None:
    for ambito in ("ui", "mision", "libro", "script", "desconocido"):
        for tarea in ("traducir", "revisar"):
            lt = Lote(
                (Entrada("0", "Hello ⟦0⟧", "p", "Hola ⟦0⟧"),),
                ambito,
                "español mexicano",
                {"Iron": "Hierro"},
                "granja",
                tarea,
            )
            assert "español mexicano" in sistema(lt) or tarea == "revisar"
            assert "Hello ⟦0⟧" in usuario(lt)


def test_simulador_conserva_marcadores_y_bordes() -> None:
    r = Simulador().traducir_lote(lote("⟦0⟧ Hello ⟦1⟧"))
    assert r == {"0": "«ES» ⟦0⟧ Hello ⟦1⟧"} or "⟦0⟧" in r["0"]


@pytest.mark.parametrize("motor", list(fabrica.MOTORES))
def test_fabrica_pide_lo_que_falta(motor: str) -> None:
    if fabrica.necesita_clave(motor):
        with pytest.raises(ErrorFatal, match="Falta la clave"):
            fabrica.crear(motor, None, "modelo")
    elif motor == "personalizado":
        with pytest.raises(ErrorFatal, match="dirección"):
            fabrica.crear(motor, None, "modelo")
    else:
        m = fabrica.crear(motor, None, "modelo")
        assert m.nombre
        cerrar = getattr(m, "cerrar", None)
        if callable(cerrar):
            cerrar()


def test_fabrica_motor_desconocido() -> None:
    with pytest.raises(ErrorFatal, match="desconocido"):
        fabrica.crear("no-existe", "clave", "modelo")

"""Carga segura de los motores locales: pausas entre pedidos, vigilancia de la GPU y pedidos más chicos."""

from __future__ import annotations

import json

import httpx
import pytest

from traductor_es.motores import fabrica
from traductor_es.motores.base import Entrada, Lote
from traductor_es.motores.carga import Enfriador
from traductor_es.motores.compatible import PERFILES, Compatible
from traductor_es.motores.gemini import Gemini


def test_la_pausa_cumple_el_ciclo_de_trabajo() -> None:
    dormidas: list[float] = []
    e = Enfriador(ciclo=0.7, dormir=dormidas.append, leer=lambda: None)
    e.despues(10.0)
    assert dormidas == [pytest.approx(10 * 0.3 / 0.7)]  # 70 % trabajando, 30 % descansando
    assert e.pausas == pytest.approx(4.2857, abs=1e-3)


def test_con_ciclo_completo_no_hay_pausa() -> None:
    dormidas: list[float] = []
    Enfriador(ciclo=1.0, dormir=dormidas.append).despues(10.0)
    assert dormidas == []


def test_un_ciclo_imposible_se_rechaza() -> None:
    with pytest.raises(ValueError, match="ciclo"):
        Enfriador(ciclo=0.0)


def test_espera_a_que_la_gpu_baje_de_temperatura() -> None:
    lecturas = iter([86, 83, 74])
    dormidas: list[float] = []
    avisos: list[str] = []
    e = Enfriador(maxima=80, leer=lambda: next(lecturas), dormir=dormidas.append, aviso=avisos.append)
    e.antes()
    assert dormidas == [5.0, 5.0]
    assert len(avisos) == 1 and "86 °C" in avisos[0]


def test_no_espera_para_siempre_si_la_gpu_sigue_caliente() -> None:
    dormidas: list[float] = []
    e = Enfriador(maxima=80, espera_maxima=15.0, leer=lambda: 95, dormir=dormidas.append)
    e.antes()
    assert sum(dormidas) == 15.0


def test_sin_nvidia_smi_no_se_vigila_nada() -> None:
    dormidas: list[float] = []
    Enfriador(leer=lambda: None, dormir=dormidas.append).antes()
    assert dormidas == []


def test_el_motor_descansa_despues_de_cada_pedido() -> None:
    dormidas: list[float] = []
    cliente = httpx.Client(
        transport=httpx.MockTransport(
            lambda _p: httpx.Response(
                200, json={"choices": [{"message": {"role": "assistant", "content": json.dumps({"0": "Hola"})}}]}
            )
        )
    )
    enfriador = Enfriador(ciclo=0.5, dormir=dormidas.append, leer=lambda: None)
    motor = Compatible(PERFILES["ollama"], "m", cliente=cliente, enfriador=enfriador)
    assert motor.traducir_lote(Lote((Entrada("0", "Hello"),), "ui", "español")) == {"0": "Hola"}
    assert len(dormidas) == 1 and dormidas[0] >= 0
    motor.cerrar()


def test_un_motor_en_localhost_cuenta_como_local() -> None:
    en_pc = Compatible(PERFILES["personalizado"], "m", direccion="http://127.0.0.1:8089/v1")
    en_nube = Compatible(PERFILES["openrouter"], "m", clave="k")
    assert en_pc.es_local and not en_nube.es_local
    assert Compatible(PERFILES["ollama"], "m").es_local
    for m in (en_pc, en_nube):
        m.cerrar()


def test_los_pedidos_locales_son_mas_chicos() -> None:
    local = Compatible(PERFILES["personalizado"], "m", direccion="http://localhost:8089/v1")
    assert fabrica.limites_de_lote(local) == fabrica.LIMITES_LOCALES
    assert fabrica.limites_de_lote(Gemini("clave")) == fabrica.LIMITES_NORMALES
    local.cerrar()


def test_cancelar_corta_las_pausas_y_la_espera_de_la_gpu() -> None:
    import threading
    import time

    evento = threading.Event()
    e = Enfriador(maxima=80, leer=lambda: 95)  # GPU siempre caliente: sin cancelar esperaría 180 s
    e.cancelar = evento
    threading.Timer(0.05, evento.set).start()
    inicio = time.monotonic()
    e.antes()
    e.despues(1000.0)  # ya cancelado: no descansa
    assert time.monotonic() - inicio < 10

"""Grabar y reproducir respuestas del motor: lo mismo pedido dos veces sale igual y no se vuelve a pagar."""

from __future__ import annotations

from pathlib import Path

from traductor_es.motores.base import Entrada, Lote
from traductor_es.motores.compatible import PERFILES, Compatible
from traductor_es.motores.fabrica import LIMITES_LOCALES, limites_de_lote
from traductor_es.motores.grabadora import MotorGrabado, clave_del_pedido
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.ejemplos import Ejemplos
from traductor_es.validacion import medicion

BANCO = Path(__file__).parent / "datos" / "referencia_es.json"


def _lote(*textos: str) -> Lote:
    return Lote(tuple(Entrada(str(i), t) for i, t in enumerate(textos)), "ui", "español")


def test_lo_grabado_se_reutiliza_y_no_llega_al_motor(tmp_path: Path) -> None:
    ruta = tmp_path / "g.sqlite"
    with MotorGrabado(Simulador(), ruta) as g:
        assert g.traducir_lote(_lote("Iron Gear")) == {"0": "«ES» Iron Gear"}
    otro = Simulador()
    with MotorGrabado(otro, ruta) as g2:
        assert g2.traducir_lote(_lote("Iron Gear")) == {"0": "«ES» Iron Gear"}
        assert otro.lotes_recibidos == [] and (g2.aciertos, g2.pedidos) == (1, 0)


def test_cada_repeticion_tiene_su_grabacion_y_solo_grabado_no_llama(tmp_path: Path) -> None:
    ruta = tmp_path / "g.sqlite"
    with MotorGrabado(Simulador(), ruta, repeticion=1) as g:
        g.traducir_lote(_lote("Iron Gear"))
    otro = Simulador()
    with MotorGrabado(otro, ruta, repeticion=2, solo_grabado=True) as g2:
        assert g2.traducir_lote(_lote("Iron Gear")) == {}  # la 2.ª repetición no está grabada
        assert g2.faltantes == 1 and otro.lotes_recibidos == []
    assert clave_del_pedido("m", _lote("a"), 1) != clave_del_pedido("m", _lote("a"), 2)


def test_un_motor_grabado_usa_los_limites_del_real(tmp_path: Path) -> None:
    local = Compatible(PERFILES["personalizado"], "m", direccion="http://127.0.0.1:8089/v1")
    with MotorGrabado(local, tmp_path / "g.sqlite") as g:
        assert limites_de_lote(g) == LIMITES_LOCALES


def test_sin_ejemplos_no_se_cuela_ninguno() -> None:
    pares = {"Iron Gear": "Engranaje de hierro", "Iron Plate": "Placa de hierro"}
    sin = Ejemplos(cantidad=0)
    sin.agregar_pares(pares)
    assert sin.parecidos(["Iron Ingot"]) == {}
    con_uno = Ejemplos(cantidad=1)
    con_uno.agregar_pares(pares)
    assert len(con_uno.parecidos(["Iron Ingot"])) == 1


def test_reproducir_un_banco_da_lo_mismo_con_varios_hilos(tmp_path: Path) -> None:
    banco = medicion.Banco.leer(BANCO)
    ruta = tmp_path / "g.sqlite"
    with MotorGrabado(Simulador(), ruta, 1) as grabado:
        primera = medicion.medir(grabado, banco, "s", "", "simulador", hilos=4)[0]
    with MotorGrabado(Simulador(), ruta, 1, solo_grabado=True) as reproducido:
        segunda = medicion.medir(reproducido, banco, "s", "", "simulador", hilos=4)[0]
        assert reproducido.faltantes == 0 and reproducido.pedidos == 0
    assert segunda.traducidos == primera.traducidos and segunda.chrf == primera.chrf

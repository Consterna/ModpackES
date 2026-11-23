"""El gasto real que informa la medición incluye lo que cuesta la revisión (hallazgo H-019)."""

from __future__ import annotations

from pathlib import Path

from traductor_es.motores.base import Lote
from traductor_es.motores.simulador import Simulador
from traductor_es.validacion import medicion

BANCO = Path(__file__).parent / "datos" / "referencia_es.json"


class ConUso(Simulador):
    """Simulador que factura como Gemini: 10 tokens de entrada y 5 de salida por texto pedido."""

    def __init__(self) -> None:
        super().__init__(marcar=frozenset({"«ES» Getting Started"}))
        self.uso = [0, 0]

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.uso[0] += 10 * len(lote.entradas)
        self.uso[1] += 5 * len(lote.entradas)
        return super().traducir_lote(lote)


def test_la_fila_con_revision_cuenta_tambien_lo_que_gasto_el_juez() -> None:
    motor = ConUso()
    antes, despues = medicion.medir(motor, medicion.Banco.leer(BANCO), "sim", "gemini-3.8-flash", revisar=True)
    assert antes.tokens_reales is not None and despues.tokens_reales is not None
    assert despues.tokens_reales[0] > antes.tokens_reales[0]  # el juez también pidió textos
    assert despues.tokens_reales == (motor.uso[0], motor.uso[1])  # acumulado: todo lo facturado
    assert antes.costo_real is not None and despues.costo_real is not None
    assert despues.costo_real > antes.costo_real

"""Las ramas que faltaban por cubrir en la validación y en el lang JSON5 (criterio del plan: ≥ 95 % o explicado).

- El juez a ciegas: si falla, no se cambia nada («igual»); si el usuario cancela, se corta de verdad.
- chrF de textos vacíos o hechos solo de espacios.
- lang JSON5: un archivo que no es un objeto, o con miles de niveles de anidamiento, es un archivo roto (ValueError).
"""

from __future__ import annotations

import pytest

from traductor_es.formatos import lang_json5
from traductor_es.motores.base import Cancelado, Lote
from traductor_es.validacion.chrf import chrf
from traductor_es.validacion.verificacion import gana_la_nueva, veredictos

CASO = ("Iron Plate", "item", "Placa de hierro", "Lámina de hierro")


class _Juez:
    def __init__(self, error: Exception | None = None, respuesta: dict[str, str] | None = None) -> None:
        self.error = error
        self.respuesta = respuesta or {}

    @property
    def nombre(self) -> str:
        return "juez"

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        if self.error is not None:
            raise self.error
        return self.respuesta


def test_si_el_juez_falla_no_se_cambia_nada() -> None:
    assert veredictos(_Juez(RuntimeError("sin red")), "es_mx", "mision", [CASO, CASO]) == ["igual", "igual"]
    assert gana_la_nueva(_Juez(RuntimeError("sin red")), "es_mx", "mision", [CASO]) == [False]


def test_cancelar_corta_al_juez() -> None:
    with pytest.raises(Cancelado):
        veredictos(_Juez(Cancelado()), "es_mx", "mision", [CASO])


def test_respuestas_raras_del_juez() -> None:
    juez = _Juez(respuesta={"0": " b ", "1": "a, claramente", "2": "ninguna"})
    assert veredictos(juez, "es_mx", "mision", [CASO, CASO, CASO, CASO]) == ["B", "A", "igual", "igual"]
    assert gana_la_nueva(juez, "es_mx", "mision", []) == []


@pytest.mark.parametrize(
    ("hipotesis", "referencia", "esperado"),
    [("", "", 100.0), ("   ", " ", 100.0), ("", "a", 0.0), ("a", "", 0.0), ("ab", "ab", 100.0)],
)
def test_chrf_con_textos_vacios(hipotesis: str, referencia: str, esperado: float) -> None:
    assert chrf(hipotesis, referencia) == pytest.approx(esperado)


@pytest.mark.parametrize("texto", ["[1, 2]", '"solo un texto"', "null", "[" * 5000 + "]" * 5000])
def test_lang_json5_que_no_es_un_objeto(texto: str) -> None:
    with pytest.raises(ValueError):  # el mensaje cambia según el caso
        lang_json5.leer(texto)


def test_lang_json5_ignora_lo_que_no_es_texto() -> None:
    assert lang_json5.leer('{"a": 1, "b": ["x", 2, null, "y"], "c": {"d": "e"}, "f": "g"}') == {
        "b": ["x", "y"],
        "f": "g",
    }

"""La máscara de códigos ante textos y respuestas adversarias: nunca devuelve un texto con códigos distintos.

Si el motor pierde, duplica, inventa o altera un marcador, `desenmascarar` debe devolver None (la traducción se
descarta) o un texto con exactamente los mismos códigos que el original.
"""

from __future__ import annotations

from collections import Counter

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from traductor_es.nucleo.mascara import desenmascarar, enmascarar

_CODIGOS = ["§a", "§l§n", "&c", "%s", "%1$s", "%2$d", "%%", "{0}", "{name}", "$(l)", "$(br)", "<b>", "\\n", "${x}"]
_PALABRAS = ["Craft", "the", "Iron", "Plate", "now", "!", " ", "ñandú", "⟦", "⟧", "⟦0⟧", "0", "⟦ 1 ⟧"]
_TEXTO = st.lists(st.sampled_from(_CODIGOS + _PALABRAS), min_size=1, max_size=12).map(" ".join)
_AJUSTES = settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def _codigos(texto: str) -> Counter[str]:
    return Counter(t for t in enmascarar(texto).tokens)


@_AJUSTES
@given(_TEXTO)
def test_ida_y_vuelta_o_descarte_nunca_otro_texto(texto: str) -> None:
    m = enmascarar(texto)
    vuelta = desenmascarar(m.texto, m.tokens)
    assert vuelta is None or vuelta == texto


@_AJUSTES
@given(_TEXTO, st.data())
def test_respuesta_alterada_del_motor_nunca_cambia_los_codigos(texto: str, data: st.DataObject) -> None:
    m = enmascarar(texto)
    if not m.tokens:
        return
    marcadores = [f"⟦{i}⟧" for i in range(len(m.tokens))]
    # El «motor» devuelve una permutación/duplicación/pérdida/invención arbitraria de marcadores con texto español
    elegidos = data.draw(st.lists(st.sampled_from([*marcadores, "⟦99⟧", "⟦-1⟧", "⟦0", "0⟧", "⟦ 0 ⟧"]), max_size=6))
    respuesta = "Texto " + " ".join(elegidos) + " fin"
    vuelta = desenmascarar(respuesta, m.tokens)
    if vuelta is not None:
        assert _codigos(vuelta) == Counter(m.tokens), (respuesta, vuelta)


@pytest.mark.parametrize("original", ["Use ⟦0⟧ and %s", "⟦1⟧ first %s then %d", "Literal ⟦⟧ %s"])
def test_texto_que_ya_trae_marcadores_se_descarta(original: str) -> None:
    """Caracterización (H-011): falla cerrado; el texto queda sin traducir en vez de traducirse mal."""
    m = enmascarar(original)
    assert desenmascarar(m.texto, m.tokens) is None

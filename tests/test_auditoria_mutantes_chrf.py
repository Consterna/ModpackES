"""chrF contra una implementación de referencia escrita aparte (Popović, 2015: n-gramas de caracteres de 1 a 6, sin
espacios, F-beta con beta = 2, promedio simple de precisión y recall sobre los órdenes que existen).

Fija las constantes (orden máximo 6 y beta 2) y el borde de los textos vacíos: mutaciones que antes sobrevivían
(`logs/fase-03/mutacion_chrf.log`, 58,8 %).
"""

from __future__ import annotations

from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from traductor_es.validacion.chrf import chrf


def _referencia(hipotesis: str, referencia: str) -> float:
    h_txt, r_txt = "".join(hipotesis.split()), "".join(referencia.split())
    precisiones: list[float] = []
    recalls: list[float] = []
    for n in range(1, 7):
        h = Counter(h_txt[i : i + n] for i in range(len(h_txt) - n + 1))
        r = Counter(r_txt[i : i + n] for i in range(len(r_txt) - n + 1))
        if not h or not r:
            continue
        comunes = sum(min(c, r[g]) for g, c in h.items())
        precisiones.append(comunes / sum(h.values()))
        recalls.append(comunes / sum(r.values()))
    if not precisiones:
        return 100.0 if hipotesis.strip() == referencia.strip() else 0.0
    p, r = sum(precisiones) / len(precisiones), sum(recalls) / len(recalls)
    if p == r == 0:
        return 0.0
    return 100 * 5 * p * r / (4 * p + r)


def test_un_valor_hecho_a_mano() -> None:
    # «ab» frente a «abc»: P = (1 + 1) / 2 = 1, R = (2/3 + 1/2) / 2 = 7/12, F2 = 5·P·R / (4·P + R) = 35/55
    assert chrf("ab", "abc") == pytest.approx(100 * 35 / 55)


def test_orden_siete_no_cuenta() -> None:
    # Iguales en los primeros 7 caracteres y distintos en el octavo: con orden máximo 7 daría otro valor
    assert chrf("abcdefgh", "abcdefgx") == pytest.approx(_referencia("abcdefgh", "abcdefgx"))


@settings(max_examples=300, deadline=None)
@given(st.text("abcde xy", max_size=14), st.text("abcde xy", max_size=14))
def test_igual_a_la_referencia(hipotesis: str, referencia: str) -> None:
    assert chrf(hipotesis, referencia) == pytest.approx(_referencia(hipotesis, referencia))


def test_sin_ngramas() -> None:
    assert chrf("", "") == 100.0
    assert chrf("  ", "\t") == 100.0
    assert chrf("", "a") == 0.0
    assert chrf("ab", "cd") == 0.0

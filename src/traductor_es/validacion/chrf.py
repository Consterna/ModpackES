"""chrF de una oración (Popović, 2015): parecido entre dos textos por n-gramas de caracteres."""

from __future__ import annotations

import re
from collections import Counter

_N_MAXIMO, _BETA = 6, 2.0


def _ngramas(texto: str, n: int) -> Counter[str]:
    sin_espacios = re.sub(r"\s+", "", texto)
    return Counter(sin_espacios[i : i + n] for i in range(len(sin_espacios) - n + 1))


def chrf(hipotesis: str, referencia: str) -> float:
    """chrF de una oración (0 a 100): F-beta (beta 2) de n-gramas de caracteres de 1 a 6, sin espacios."""
    precisiones: list[float] = []
    recalls: list[float] = []
    for n in range(1, _N_MAXIMO + 1):
        h, r = _ngramas(hipotesis, n), _ngramas(referencia, n)
        if not h or not r:
            continue
        comunes = sum((h & r).values())
        precisiones.append(comunes / sum(h.values()))
        recalls.append(comunes / sum(r.values()))
    if not precisiones:
        return 100.0 if hipotesis.strip() == referencia.strip() else 0.0
    p, r = sum(precisiones) / len(precisiones), sum(recalls) / len(recalls)
    if p == 0 and r == 0:
        return 0.0
    b2 = _BETA**2
    return 100 * (1 + b2) * p * r / (b2 * p + r)

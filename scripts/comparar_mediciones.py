"""Compara dos grupos de mediciones del mismo banco con un intervalo de confianza para la diferencia.

Cada grupo es una o varias salidas de `medir_calidad.py` (build/*.json). Se promedia el chrF de cada texto entre
las corridas de un grupo y se remuestrean los textos (bootstrap pareado): así se ve si una mejora es mayor que
el ruido del propio banco y no solo del azar de una corrida.

Uso:  uv run python scripts/comparar_mediciones.py --a build/sin1.json build/sin2.json
                                                    --b build/con1.json build/con2.json
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

from traductor_es.validacion.medicion import chrf


def _puntajes(archivos: list[Path]) -> dict[str, float]:
    """{texto original: chrF promedio entre corridas}, con el chrF recalculado de cada traducción."""
    por_texto: dict[str, list[float]] = {}
    for ruta in archivos:
        datos: list[dict[str, Any]] = json.loads(ruta.read_text(encoding="utf-8"))
        for t in datos[-1].get("traducciones", []):
            por_texto.setdefault(t["original"], []).append(chrf(t["traduccion"], t["referencia"]))
    return {o: statistics.fmean(v) for o, v in por_texto.items()}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", nargs="+", type=Path, required=True, help="grupo base")
    ap.add_argument("--b", nargs="+", type=Path, required=True, help="grupo con la mejora")
    ap.add_argument("--remuestreos", type=int, default=2000)
    args = ap.parse_args(argv)
    a, b = _puntajes(args.a), _puntajes(args.b)
    comunes = sorted(set(a) & set(b))
    if len(comunes) < 5:
        print("Hay muy pocos textos en común para comparar.")
        return 1
    diferencias = [b[o] - a[o] for o in comunes]
    azar = random.Random(0)
    medias = sorted(statistics.fmean(azar.choices(diferencias, k=len(diferencias))) for _ in range(args.remuestreos))
    bajo, alto = medias[int(0.025 * args.remuestreos)], medias[int(0.975 * args.remuestreos) - 1]
    media = statistics.fmean(diferencias)
    veredicto = "mejora" if bajo > 0 else "empeora" if alto < 0 else "no se distingue del ruido"
    print(f"Textos en común: {len(comunes)} · corridas: {len(args.a)} contra {len(args.b)}")
    base = statistics.fmean(a[o] for o in comunes)
    mejora = statistics.fmean(b[o] for o in comunes)
    print(f"chrF base {base:.1f} · con la mejora {mejora:.1f}")
    print(f"Diferencia {media:+.2f} (IC 95 %: {bajo:+.2f} a {alto:+.2f}) → {veredicto}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

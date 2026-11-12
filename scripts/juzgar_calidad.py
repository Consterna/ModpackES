"""Juzga con un motor distinto las traducciones guardadas por `medir_calidad.py` (al estilo GEMBA-MQM).

Lee el detalle que dejó `medir_calidad.py` (build/medicion.json), pide a otro motor que marque errores con
gravedad y categoría, sin mirar la referencia, y lo hace en dos órdenes de lectura para ver cuánto cambia el
veredicto por la posición. Es una herramienta de desarrollo: usa un motor DISTINTO del que tradujo (los
jueces tienden a preferir su propia familia). No toca ninguna instancia ni la memoria.

Uso:  uv run python scripts/juzgar_calidad.py [--entrada build/medicion.json] [--motor gemini] [--modelo M]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from traductor_es import configuracion
from traductor_es.motores import fabrica
from traductor_es.motores.gemini import MODELO_POR_DEFECTO
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.validacion import revision

RAIZ = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entrada", type=Path, default=RAIZ / "build" / "medicion.json")
    ap.add_argument("--motor", choices=list(fabrica.MOTORES), default=fabrica.GEMINI)
    ap.add_argument("--modelo", default="")
    ap.add_argument("--direccion", default="")
    ap.add_argument(
        "--medicion", type=int, default=-1, help="cuál de las mediciones del archivo (por defecto la última)"
    )
    args = ap.parse_args(argv)
    datos: list[dict[str, Any]] = json.loads(args.entrada.read_text(encoding="utf-8"))
    medicion = datos[args.medicion]
    traducciones: list[dict[str, str]] = medicion.get("traducciones", [])
    if not traducciones:
        print("El archivo no trae las traducciones: vuelve a correr medir_calidad.py con esta versión.")
        return 1
    modelo = args.modelo or (MODELO_POR_DEFECTO if args.motor == fabrica.GEMINI else "")
    print(f"Tradujo: {medicion['motor']} · Juez: {args.motor}:{modelo}")
    if medicion["motor"].endswith(f":{modelo}") or medicion["motor"] == f"{args.motor}:{modelo}":
        print("Aviso: el juez es el mismo modelo que tradujo; tiende a preferir su propio estilo.")
    motor = fabrica.crear(args.motor, configuracion.leer_clave(args.motor), modelo, args.direccion)
    por_ambito: dict[str, dict[str, str]] = {}
    for t in traducciones:
        por_ambito.setdefault(t["ambito"], {})[t["original"]] = t["traduccion"]
    marcados: list[set[str]] = [set(), set()]
    categorias: Counter[str] = Counter()
    revisados = 0
    with Memoria(":memory:") as memoria:
        traductor = Traductor(motor, memoria, Glosario())
        for ambito, pares in por_ambito.items():
            revisados += len(pares)
            for vuelta, invertir in enumerate((False, True)):
                for h in revision.revisar(traductor, pares, ambito, invertir=invertir):
                    if h.gravedad in revision.A_REHACER:
                        marcados[vuelta].add(h.original)
                        if vuelta == 0:
                            categorias[h.categoria] += 1
    union = marcados[0] | marcados[1]
    acuerdo = len(marcados[0] & marcados[1]) / len(union) if union else 1.0
    print(f"Textos juzgados: {revisados}")
    for i, nombre in enumerate(("orden normal", "orden inverso")):
        por_cien = 100 * len(marcados[i]) / max(revisados, 1)
        print(f"Errores graves o críticos ({nombre}): {len(marcados[i])} ({por_cien:.1f} por cada 100)")
    print(f"Acuerdo entre los dos órdenes: {100 * acuerdo:.0f} %")
    if categorias:
        print("Por categoría (orden normal): " + ", ".join(f"{c} {n}" for c, n in categorias.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

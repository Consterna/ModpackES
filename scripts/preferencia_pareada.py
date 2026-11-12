"""Pregunta a un juez cuál de dos traducciones del mismo texto es mejor (comparación pareada, en los dos órdenes).

Sirve para medir una mejora cuando no hay traducciones de referencia (misiones, libros): se corre
`medir_calidad.py` con y sin la mejora y aquí se comparan las dos salidas. Cada par se juzga dos veces, cambiando
el orden de A y B; solo cuenta como victoria si el juez elige lo mismo en los dos órdenes. El juez ve el contexto que
recibió el traductor. Si el juez es el mismo modelo que tradujo, tiende a preferir su estilo: usa otro si puedes.

Uso:  uv run python scripts/preferencia_pareada.py --a build/sin.json --b build/con.json [--motor gemini --modelo M]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from traductor_es import configuracion
from traductor_es.motores import fabrica
from traductor_es.motores.base import Entrada, Lote
from traductor_es.motores.gemini import MODELO_POR_DEFECTO
from traductor_es.nucleo.dialectos import DIALECTOS

POR_LOTE = 20


def _leer(ruta: Path) -> dict[str, dict[str, str]]:
    datos: list[dict[str, Any]] = json.loads(ruta.read_text(encoding="utf-8"))
    return {t["original"]: t for t in datos[-1].get("traducciones", [])}


def _elegir(motor: Any, ambito: str, textos: list[tuple[str, str, str, str]]) -> list[str]:
    """Para (original, pista, A, B) devuelve «A», «B» o «igual» por texto."""
    veredictos: list[str] = []
    for i in range(0, len(textos), POR_LOTE):
        trozo = textos[i : i + POR_LOTE]
        entradas = tuple(
            Entrada(str(j), o, pista, traduccion=a, alternativa=b) for j, (o, pista, a, b) in enumerate(trozo)
        )
        salida = motor.traducir_lote(Lote(entradas, ambito, DIALECTOS["es_mx"], tarea="comparar"))
        for j in range(len(trozo)):
            v = str(salida.get(str(j), "")).strip().upper()
            veredictos.append("A" if v.startswith("A") else "B" if v.startswith("B") else "igual")
    return veredictos


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", type=Path, required=True, help="salida base de medir_calidad.py")
    ap.add_argument("--b", type=Path, required=True, help="salida con la mejora")
    ap.add_argument("--motor", choices=list(fabrica.MOTORES), default=fabrica.GEMINI)
    ap.add_argument("--modelo", default="")
    ap.add_argument("--direccion", default="")
    args = ap.parse_args(argv)
    a, b = _leer(args.a), _leer(args.b)
    comunes = sorted(o for o in a if o in b and a[o]["traduccion"] != b[o]["traduccion"])
    iguales = len(set(a) & set(b)) - len(comunes)
    if not comunes:
        print("Las dos corridas tradujeron todo igual: no hay nada que comparar.")
        return 0
    modelo = args.modelo or (MODELO_POR_DEFECTO if args.motor == fabrica.GEMINI else "")
    motor = fabrica.crear(args.motor, configuracion.leer_clave(args.motor), modelo, args.direccion)
    ambito = a[comunes[0]]["ambito"]
    directo = [(o, b[o].get("pista", ""), a[o]["traduccion"], b[o]["traduccion"]) for o in comunes]
    inverso = [(o, b[o].get("pista", ""), b[o]["traduccion"], a[o]["traduccion"]) for o in comunes]
    v1, v2 = _elegir(motor, ambito, directo), _elegir(motor, ambito, inverso)
    gana_b = sum(1 for x, y in zip(v1, v2, strict=True) if x == "B" and y == "A")
    gana_a = sum(1 for x, y in zip(v1, v2, strict=True) if x == "A" and y == "B")
    empates = len(comunes) - gana_b - gana_a
    # Prueba de signos exacta (dos colas) sobre las victorias de cada lado
    n = gana_a + gana_b
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(gana_a, gana_b) + 1)) / 2**n) if n else 1.0
    print(f"Juez: {args.motor}:{modelo} · textos distintos: {len(comunes)} (iguales en las dos: {iguales})")
    print(f"Gana la mejora (B): {gana_b} · gana la base (A): {gana_a} · empate o juez inconsistente: {empates}")
    print(f"Prueba de signos: p = {p:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

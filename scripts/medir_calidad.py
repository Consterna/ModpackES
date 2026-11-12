"""Traduce el banco de referencia (tests/datos/referencia_es.json) con un motor y muestra las métricas.

Uso:  uv run python scripts/medir_calidad.py [--motor gemini] [--modelo M] [--direccion URL] [--revisar] [--simular]
Usa la clave guardada del motor (o su variable de entorno) y escribe el detalle en build/medicion.json.
Con Gemini cuesta unos centavos; --simular no gasta nada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from traductor_es import configuracion
from traductor_es.modulos.base import quitar_vecindad
from traductor_es.motores import fabrica
from traductor_es.motores.base import Motor
from traductor_es.motores.gemini import MODELO_POR_DEFECTO
from traductor_es.motores.simulador import Simulador
from traductor_es.validacion import medicion

RAIZ = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--motor", choices=list(fabrica.MOTORES), default=fabrica.GEMINI)
    ap.add_argument("--modelo", default="")
    ap.add_argument("--direccion", default="")
    ap.add_argument("--revisar", action="store_true", help="medir también después de la revisión automática")
    ap.add_argument(
        "--sin-contexto", action="store_true", help="medir sin las pistas ni los ejemplos del banco (como antes)"
    )
    ap.add_argument(
        "--glosario-laxo", action="store_true", help="no rechazar traducciones a las que les falta un término"
    )
    ap.add_argument(
        "--sin-vecindad",
        action="store_true",
        help="quitar de las pistas el título y la línea anterior (misiones y libros)",
    )
    ap.add_argument("--simular", action="store_true", help="sin API: solo comprueba que todo funcione")
    ap.add_argument("--banco", type=Path, default=RAIZ / "tests" / "datos" / "referencia_es.json")
    ap.add_argument("--salida", type=Path, default=RAIZ / "build" / "medicion.json")
    args = ap.parse_args(argv)
    modelo = args.modelo or (MODELO_POR_DEFECTO if args.motor == fabrica.GEMINI else "")
    if args.simular:
        motor: Motor = Simulador()
        nombre = "simulador"
    else:
        motor = fabrica.crear(args.motor, configuracion.leer_clave(args.motor), modelo, args.direccion)
        nombre = f"{args.motor}:{modelo}"
    banco = medicion.Banco.leer(args.banco)
    if args.sin_vecindad:
        banco.casos = [medicion.Caso(c.ambito, c.original, c.referencia, quitar_vecindad(c.pista)) for c in banco.casos]
    if args.sin_contexto:
        banco.ejemplos = {}
        banco.casos = [medicion.Caso(c.ambito, c.original, c.referencia) for c in banco.casos]
    resultados = medicion.medir(
        motor, banco, nombre, modelo, args.motor, revisar=args.revisar, glosario_estricto=not args.glosario_laxo
    )
    for m in resultados:
        print(m.tabla(), end="\n\n")
    peores = resultados[-1].ejemplos[:5]
    if peores:
        print("Más lejos de la referencia (no siempre son errores):")
        for e in peores:
            print(f"  [{e['chrf']}] {e['original']}\n      → {e['traduccion']}\n      ref. {e['referencia']}")
    medicion.guardar(resultados, args.salida)
    print(f"\nDetalle en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

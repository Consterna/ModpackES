"""Traduce el banco de referencia (tests/datos/referencia_es.json) con un motor y muestra las métricas.

Uso:  uv run python scripts/medir_calidad.py [--motor gemini] [--modelo M] [--direccion URL] [--revisar] [--simular]
Usa la clave guardada del motor (o su variable de entorno) y escribe el detalle en build/medicion.json.
Con Gemini cuesta unos centavos; --simular no gasta nada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from traductor_es import configuracion
from traductor_es.modulos.base import quitar_vecindad
from traductor_es.modulos.mods import es_nombre
from traductor_es.motores import fabrica
from traductor_es.motores.base import Motor
from traductor_es.motores.carga import Enfriador
from traductor_es.motores.gemini import MODELO_POR_DEFECTO
from traductor_es.motores.grabadora import MotorGrabado
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.ejemplos import CANTIDAD_EN_LA_APP
from traductor_es.nucleo.traductor import ECONOMICO, PERFILES
from traductor_es.validacion import medicion

RAIZ = Path(__file__).resolve().parent.parent


def nombres_del_juego(carpeta: Path, dialecto: str) -> dict[str, str]:
    """{inglés: español} de los nombres de objetos, bloques y criaturas del juego (el dialecto primero)."""
    ingles: dict[str, str] = json.loads((carpeta / "en_us.json").read_text(encoding="utf-8"))
    salida: dict[str, str] = {}
    for variante in dict.fromkeys((dialecto, "es_mx", "es_es")):
        ruta = carpeta / f"{variante}.json"
        if not ruta.is_file():
            continue
        traducido: dict[str, str] = json.loads(ruta.read_text(encoding="utf-8"))
        for clave, en in ingles.items():
            es = traducido.get(clave)
            if es_nombre(clave) and isinstance(es, str) and en.strip() and es.strip():
                salida.setdefault(en.strip(), es.strip())
    return salida


def usos_del_juego(carpeta: Path, dialecto: str) -> list[tuple[dict[str, str], dict[str, str]]]:
    """El archivo completo del juego en inglés y en el dialecto, para ver cómo se usan las palabras en minúscula."""
    ruta = carpeta / f"{dialecto}.json"
    if not ruta.is_file():
        ruta = carpeta / "es_mx.json"
    if not ruta.is_file():
        return []
    ingles: dict[str, str] = json.loads((carpeta / "en_us.json").read_text(encoding="utf-8"))
    return [(ingles, json.loads(ruta.read_text(encoding="utf-8")))]


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
        "--carga-segura",
        action="store_true",
        help="motor local: descansar entre pedidos (ciclo 70/30), vigilar la GPU (pausa sobre 80 °C) y usar 1 hilo",
    )
    ap.add_argument("--hilos", type=int, default=0, help="pedidos a la vez (0: 4, o 1 con --carga-segura)")
    ap.add_argument(
        "--n-ejemplos", type=int, default=CANTIDAD_EN_LA_APP, help="cuántos ejemplos parecidos se mandan por lote"
    )
    ap.add_argument(
        "--sin-vecindad",
        action="store_true",
        help="quitar de las pistas el título y la línea anterior (misiones y libros)",
    )
    ap.add_argument(
        "--sin-controles",
        action="store_true",
        help="sin los controles de forma (mayúsculas del glosario, nombres que no se traducen, repeticiones)",
    )
    ap.add_argument(
        "--vanilla",
        type=Path,
        default=None,
        help="carpeta con en_us.json, es_mx.json y es_es.json del juego: sus nombres entran como oficiales (como "
        "en la app) si el banco no los trae",
    )
    ap.add_argument(
        "--grabacion",
        type=Path,
        default=None,
        help="archivo SQLite donde se graban las respuestas del motor; un pedido ya grabado no se vuelve a pagar",
    )
    ap.add_argument(
        "--solo-grabado",
        action="store_true",
        help="con --grabacion: no llamar a la API; lo que no esté grabado queda sin respuesta (mide gratis)",
    )
    ap.add_argument(
        "--repeticiones",
        type=int,
        default=1,
        help="corridas independientes (cada una con su grabación); la salida lleva _1, _2… en el nombre",
    )
    ap.add_argument("--simular", action="store_true", help="sin API: solo comprueba que todo funcione")
    ap.add_argument(
        "--calidad",
        choices=PERFILES,
        default=ECONOMICO,
        help="perfil de calidad (por defecto economico, para comparar con las mediciones anteriores)",
    )
    ap.add_argument("--banco", type=Path, default=RAIZ / "tests" / "datos" / "referencia_es.json")
    ap.add_argument("--salida", type=Path, default=RAIZ / "build" / "medicion.json")
    args = ap.parse_args(argv)
    modelo = args.modelo or (MODELO_POR_DEFECTO if args.motor == fabrica.GEMINI else "")
    if args.simular:
        motor: Motor = Simulador()
        nombre = "simulador"
    else:
        enfriador = Enfriador(aviso=print) if args.carga_segura else None
        motor = fabrica.crear(args.motor, configuracion.leer_clave(args.motor), modelo, args.direccion, enfriador)
        nombre = f"{args.motor}:{modelo}"
    banco = medicion.Banco.leer(args.banco)
    if args.vanilla is not None and not banco.juego:
        banco.juego = nombres_del_juego(args.vanilla, banco.dialecto)
        banco.usos = usos_del_juego(args.vanilla, banco.dialecto)
        print(f"Nombres del juego: {len(banco.juego)}")
    if args.sin_vecindad:
        banco.casos = [medicion.Caso(c.ambito, c.original, c.referencia, quitar_vecindad(c.pista)) for c in banco.casos]
    if args.sin_contexto:
        banco.ejemplos = {}
        banco.casos = [medicion.Caso(c.ambito, c.original, c.referencia) for c in banco.casos]
    total = 0.0
    for repeticion in range(1, max(1, args.repeticiones) + 1):
        usado: Motor = motor
        if args.grabacion is not None:
            usado = MotorGrabado(motor, args.grabacion, repeticion, solo_grabado=args.solo_grabado)
        resultados = medicion.medir(
            usado,
            banco,
            nombre,
            modelo,
            args.motor,
            revisar=args.revisar,
            glosario_estricto=not args.glosario_laxo,
            hilos=args.hilos or (1 if args.carga_segura else 4),
            cantidad_ejemplos=args.n_ejemplos,
            controles_de_forma=not args.sin_controles,
            perfil=args.calidad,
        )
        for m in resultados:
            print(m.tabla(), end="\n\n")
        if isinstance(usado, MotorGrabado):
            print(f"Grabación: {usado.aciertos} pedidos grabados, {usado.pedidos} nuevos, {usado.faltantes} sin grabar")
            usado.cerrar()
        peores = resultados[-1].ejemplos[:5]
        if peores and args.repeticiones == 1:
            print("Más lejos de la referencia (no siempre son errores):")
            for e in peores:
                print(f"  [{e['chrf']}] {e['original']}\n      → {e['traduccion']}\n      ref. {e['referencia']}")
        salida = args.salida
        if args.repeticiones > 1:
            salida = salida.with_name(f"{salida.stem}_{repeticion}{salida.suffix}")
        medicion.guardar(resultados, salida)
        print(f"\nDetalle en {salida}")
        total += sum(m.costo_real or 0.0 for m in resultados)
    if total:
        print(f"Gasto real en la API: US$ {total:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

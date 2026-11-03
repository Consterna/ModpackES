"""Línea de comandos: `traductor-es instancias | analizar | traducir | restaurar | modelos | clave`."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from typing import Any, cast

from . import __version__, configuracion
from .fuentes.lanzadores import buscar
from .motores.base import Cancelado, ErrorFatal, Motor
from .motores.gemini import MODELO_POR_DEFECTO, Gemini
from .motores.simulador import Simulador
from .nucleo.dialectos import DIALECTOS
from .proceso import GRUPOS, Informe, Proceso


def _escribir(texto: str) -> None:
    print(texto, flush=True)


def _motor(args: argparse.Namespace) -> Motor:
    if getattr(args, "simular", False):
        return Simulador()
    clave = configuracion.leer_clave()
    if not clave:
        raise ErrorFatal("Falta la clave de Gemini. Guárdala con «traductor-es clave guardar» o usa GEMINI_API_KEY.")
    return Gemini(clave, args.modelo)


def _mostrar(informe: Informe, modelo: str, lotes: bool) -> None:
    for m in informe.modulos:
        linea = f"  {m.nombre}: {m.descripcion} — {m.textos} textos, {m.a_traducir} para el motor ({m.caracteres} car.)"
        _escribir(linea + (f"\n      {m.resumen}" if m.resumen else ""))
    costo = informe.costo(modelo, lotes)
    _escribir(f"Total para el motor: {informe.a_traducir} textos, {informe.caracteres} caracteres")
    if costo is not None:
        _escribir(f"Costo estimado con {modelo}{' (por lotes)' if lotes else ''}: US$ {costo:.2f}")
    for aviso in informe.avisos:
        _escribir(f"⚠ {aviso}")
    if informe.revision and informe.revision.inconsistentes:
        _escribir(f"⚠ {informe.revision}")
    if informe.pack_activado:
        _escribir("Juego: " + ", ".join(informe.pack_activado))


def _argumentos() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="traductor-es", description="Traduce modpacks de Minecraft al español.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("instancias", help="lista las instancias de los lanzadores del PC")

    def comunes(p: argparse.ArgumentParser) -> None:
        p.add_argument("carpeta", help="carpeta de la instancia (o su carpeta minecraft)")
        p.add_argument("--dialecto", choices=list(DIALECTOS), default="es_mx")
        p.add_argument("--solo", default=",".join(GRUPOS), help="grupos separados por comas: " + ",".join(GRUPOS))
        p.add_argument("--modelo", default=MODELO_POR_DEFECTO)
        p.add_argument("--lotes", action="store_true", help="usar la Batch API (mitad de precio, tarda más)")

    comunes(sub.add_parser("analizar", help="cuenta lo que falta traducir y estima el costo (no escribe nada)"))
    traducir = sub.add_parser("traducir", help="traduce y escribe el resultado")
    comunes(traducir)
    traducir.add_argument("--hilos", type=int, default=4)
    traducir.add_argument("--simular", action="store_true", help="prueba sin API: antepone «ES» a todo")
    traducir.add_argument("--no-activar", action="store_true", help="no tocar options.txt")
    traducir.add_argument("--no-idioma", action="store_true", help="no cambiar el idioma del juego")
    restaurar = sub.add_parser("restaurar", help="devuelve misiones, scripts y libros propios a su original")
    restaurar.add_argument("carpeta")
    sub.add_parser("modelos", help="lista los modelos de Gemini que acepta tu clave")
    clave = sub.add_parser("clave", help="guarda u olvida la clave de Gemini en el sistema")
    clave.add_argument("accion", choices=["guardar", "olvidar"])
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    cast(Any, sys.stdout).reconfigure(encoding="utf-8", errors="replace")
    args = _argumentos().parse_args(argv)
    try:
        if args.orden == "instancias":
            for e in buscar():
                _escribir(f"{e.lanzador}: {e.nombre}\n    {e.juego}")
        elif args.orden == "clave":
            if args.accion == "guardar":
                configuracion.guardar_clave(getpass.getpass("Clave de Gemini (no se muestra): "))
                _escribir("Clave guardada en el almacén de credenciales del sistema.")
            else:
                configuracion.olvidar_clave()
                _escribir("Clave olvidada.")
        elif args.orden == "modelos":
            clave = configuracion.leer_clave()
            if not clave:
                raise ErrorFatal("Falta la clave de Gemini.")
            for m in Gemini(clave).listar_modelos():
                _escribir(m)
        elif args.orden == "restaurar":
            with Proceso(args.carpeta, Simulador(), registro=_escribir) as p:
                restaurados = p.restaurar()
            _escribir(f"Restaurados {len(restaurados)} archivos.")
        else:
            motor = Simulador() if args.orden == "analizar" else _motor(args)
            grupos = [g.strip() for g in args.solo.split(",") if g.strip()]
            with Proceso(
                args.carpeta, motor, args.dialecto, grupos, registro=_escribir,
                hilos=getattr(args, "hilos", 4), usar_lotes=args.lotes,
            ) as p:  # fmt: skip
                _escribir(f"Minecraft {p.instancia.version} · {p.instancia.loader or '¿loader?'} · {p.instancia.juego}")
                if args.orden == "analizar":
                    informe = p.analizar()
                else:
                    informe = p.ejecutar(activar=not args.no_activar, poner_idioma=not args.no_idioma)
            _mostrar(informe, args.modelo, args.lotes)
    except (ErrorFatal, ValueError) as e:
        _escribir(f"✖ {e}")
        return 1
    except (Cancelado, KeyboardInterrupt):
        _escribir("Cancelado. Lo traducido hasta ahora quedó guardado en la memoria.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

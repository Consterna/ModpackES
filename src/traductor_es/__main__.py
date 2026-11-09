"""Línea de comandos: `modpackes instancias | analizar | traducir | restaurar | modelos | clave`."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from typing import Any, cast

from . import NOMBRE, __version__, configuracion
from .fuentes.instancia import Instancia
from .fuentes.lanzadores import buscar
from .modulos.cobertura import informe_en_json
from .motores import fabrica
from .motores.base import Cancelado, ErrorFatal, Motor
from .motores.gemini import MODELO_POR_DEFECTO
from .motores.simulador import Simulador
from .nucleo.dialectos import DIALECTOS
from .proceso import GRUPOS, Informe, Proceso
from .registro import LOGGER, configurar
from .salida import mod_apoyo


def _escribir(texto: str) -> None:
    print(texto, flush=True)
    LOGGER.info(texto)


def _modelo(args: argparse.Namespace) -> str:
    return args.modelo or (MODELO_POR_DEFECTO if args.motor == fabrica.GEMINI else "")


def _crear(args: argparse.Namespace) -> Motor:
    clave = configuracion.leer_clave(args.motor) if fabrica.necesita_clave(args.motor) else None
    if fabrica.necesita_clave(args.motor) and not clave:
        raise ErrorFatal(
            f"Falta la clave de {fabrica.MOTORES[args.motor]}. Guárdala con «modpackes clave guardar --motor "
            f"{args.motor}» o usa {configuracion.variable_de_entorno(args.motor)}."
        )
    return fabrica.crear(args.motor, clave, _modelo(args), args.direccion or "")


def _mostrar(informe: Informe, args: argparse.Namespace) -> None:
    for m in informe.modulos:
        linea = f"  {m.nombre}: {m.descripcion} — {m.textos} textos, {m.a_traducir} para el motor ({m.caracteres} car.)"
        _escribir(linea + (f"\n      {m.resumen}" if m.resumen else ""))
    modelo, lotes = _modelo(args), args.lotes
    costo = informe.costo(modelo, lotes, args.motor, args.revisar)
    _escribir(f"Total para el motor: {informe.a_traducir} textos, {informe.caracteres} caracteres")
    if costo is not None:
        _escribir(f"Costo estimado con {modelo}{' (por lotes)' if lotes else ''}: US$ {costo:.2f}")
    for aviso in informe.avisos:
        _escribir(f"⚠ {aviso}")
    if informe.revision_automatica is not None:
        _escribir(str(informe.revision_automatica))
    if informe.revision and informe.revision.inconsistentes:
        _escribir(f"⚠ {informe.revision}")
    if informe.pack_activado:
        _escribir("Juego: " + ", ".join(informe.pack_activado))


def _opciones_de_motor(p: argparse.ArgumentParser) -> None:
    p.add_argument("--motor", choices=list(fabrica.MOTORES), default=fabrica.GEMINI, help="motor de traducción")
    p.add_argument("--direccion", default="", help="dirección del servidor (para --motor personalizado)")


def _argumentos() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="modpackes", description="Traduce modpacks de Minecraft al español.")
    ap.add_argument("--version", action="version", version=f"{NOMBRE} {__version__}")
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("instancias", help="lista las instancias de los lanzadores del PC")

    def comunes(p: argparse.ArgumentParser) -> None:
        p.add_argument("carpeta", help="carpeta de la instancia (o su carpeta minecraft)")
        p.add_argument("--dialecto", choices=list(DIALECTOS), default="es_mx")
        p.add_argument("--solo", default=",".join(GRUPOS), help="grupos separados por comas: " + ",".join(GRUPOS))
        _opciones_de_motor(p)
        p.add_argument("--modelo", default="", help=f"modelo (con Gemini, por defecto {MODELO_POR_DEFECTO})")
        p.add_argument("--lotes", action="store_true", help="usar la Batch API de Gemini (mitad de precio, tarda más)")
        p.add_argument("--contexto", default="", help="ambientación del modpack para el tono y los términos")
        p.add_argument("--revisar", action="store_true", help="revisión automática de misiones y libros (cuesta más)")
        p.add_argument(
            "--exhaustivo",
            action="store_true",
            help="en los scripts de KubeJS traduce toda frase, aunque no se sepa dónde se muestra (puede tocar lógica)",
        )
        p.add_argument(
            "--java",
            action="store_true",
            help="también el texto escrito en el código de los mods (lo muestra el mod de apoyo; ver instalar-runtime)",
        )

    comunes(sub.add_parser("analizar", help="cuenta lo que falta traducir y estima el costo (no escribe nada)"))
    traducir = sub.add_parser("traducir", help="traduce y escribe el resultado")
    comunes(traducir)
    traducir.add_argument("--hilos", type=int, default=4)
    traducir.add_argument("--simular", action="store_true", help="prueba sin API: antepone «ES» a todo")
    traducir.add_argument("--no-activar", action="store_true", help="no tocar options.txt")
    traducir.add_argument("--no-idioma", action="store_true", help="no cambiar el idioma del juego")
    cob = sub.add_parser("cobertura", help="dice qué texto queda en inglés y por qué (solo lee, no escribe nada)")
    cob.add_argument("carpeta", help="carpeta de la instancia (o su carpeta minecraft)")
    cob.add_argument("--java", action="store_true", help="también el texto escrito en el código de los mods (tarda)")
    cob.add_argument("--json", action="store_true", help="escribe solo el informe, como JSON (UTF-8)")
    rt = sub.add_parser(
        "instalar-runtime", help="pone o quita el mod de apoyo que muestra el texto del código de los mods"
    )
    rt.add_argument("carpeta", help="carpeta de la instancia (o su carpeta minecraft)")
    rt.add_argument("--quitar", action="store_true", help="quita el mod de apoyo de mods/")
    restaurar = sub.add_parser("restaurar", help="devuelve misiones, scripts y libros propios a su original")
    restaurar.add_argument("carpeta")
    modelos = sub.add_parser("modelos", help="lista los modelos que ofrece el motor")
    _opciones_de_motor(modelos)
    clave = sub.add_parser("clave", help="guarda u olvida la clave de un motor en el sistema")
    clave.add_argument("accion", choices=["guardar", "olvidar"])
    clave.add_argument("--motor", choices=list(fabrica.MOTORES), default=fabrica.GEMINI)
    return ap


def _traducir_o_analizar(args: argparse.Namespace) -> None:
    if args.lotes and args.motor != fabrica.GEMINI:
        raise ErrorFatal("--lotes solo funciona con Gemini.")
    if args.orden == "analizar" or args.simular:
        motor: Motor = Simulador()
    else:
        motor = _crear(args)
    grupos = [g.strip() for g in args.solo.split(",") if g.strip()]
    with Proceso(
        args.carpeta, motor, args.dialecto, grupos, registro=_escribir,
        hilos=getattr(args, "hilos", 4), usar_lotes=args.lotes, contexto=args.contexto, revisar=args.revisar,
        texto_java=args.java,
        scripts_exhaustivo=args.exhaustivo,
    ) as p:  # fmt: skip
        _escribir(f"Minecraft {p.instancia.version} · {p.instancia.loader or '¿loader?'} · {p.instancia.juego}")
        if args.orden == "analizar":
            informe = p.analizar()
        else:
            informe = p.ejecutar(activar=not args.no_activar, poner_idioma=not args.no_idioma)
    _mostrar(informe, args)


def _instalar_runtime(args: argparse.Namespace) -> None:
    with Instancia(args.carpeta) as inst:
        if not args.quitar:
            _escribir(f"Instalado: {mod_apoyo.instalar(inst)}")
            return
        quitados = mod_apoyo.quitar(inst)
        _escribir("Quité: " + ", ".join(p.name for p in quitados) if quitados else "No había mod de apoyo instalado.")


def _cobertura(args: argparse.Namespace) -> None:
    with Proceso(args.carpeta, Simulador(), registro=(lambda _m: None) if args.json else _escribir) as p:
        if not args.json:
            _escribir(f"Minecraft {p.instancia.version} · {p.instancia.loader or '¿loader?'} · {p.instancia.juego}")
        hallazgos = p.que_queda(java=args.java)
    if args.json:
        _escribir(informe_en_json(hallazgos))
        return
    for h in hallazgos:
        _escribir(f"[{h.categoria}] {h}")
    _escribir(f"{len(hallazgos)} hallazgos." if hallazgos else "No encontré texto que quede en inglés.")


def main(argv: Sequence[str] | None = None) -> int:
    cast(Any, sys.stdout).reconfigure(encoding="utf-8", errors="replace")
    args = _argumentos().parse_args(argv)
    configurar(configuracion.carpeta_datos())
    LOGGER.info("Línea de comandos: %s", args.orden)
    try:
        if args.orden == "instancias":
            for e in buscar():
                _escribir(f"{e.lanzador}: {e.nombre}\n    {e.juego}")
        elif args.orden == "instalar-runtime":
            _instalar_runtime(args)
        elif args.orden == "cobertura":
            _cobertura(args)
        elif args.orden == "clave":
            nombre = fabrica.MOTORES[args.motor]
            if args.accion == "guardar":
                configuracion.guardar_clave(getpass.getpass(f"Clave de {nombre} (no se muestra): "), args.motor)
                _escribir("Clave guardada en el almacén de credenciales del sistema.")
            else:
                configuracion.olvidar_clave(args.motor)
                _escribir("Clave olvidada.")
        elif args.orden == "modelos":
            args.modelo = _modelo_para_listar(args)
            motor = _crear(args)
            try:
                for m in cast(Any, motor).listar_modelos():
                    _escribir(m)
            finally:
                if hasattr(motor, "cerrar"):
                    cast(Any, motor).cerrar()
        elif args.orden == "restaurar":
            with Proceso(args.carpeta, Simulador(), registro=_escribir) as p:
                restaurados = p.restaurar()
            _escribir(f"Restaurados {len(restaurados)} archivos.")
        else:
            _traducir_o_analizar(args)
    except (ErrorFatal, ValueError) as e:
        _escribir(f"✖ {e}")
        return 1
    except (Cancelado, KeyboardInterrupt):
        _escribir("Cancelado. Lo traducido hasta ahora quedó guardado en la memoria.")
        return 130
    except Exception:
        LOGGER.exception("Error no previsto en la línea de comandos")
        raise
    return 0


def _modelo_para_listar(args: argparse.Namespace) -> str:
    """Para listar modelos no hace falta elegir uno: se usa un nombre cualquiera que no se llega a pedir."""
    return MODELO_POR_DEFECTO if args.motor == fabrica.GEMINI else "listar"


if __name__ == "__main__":
    raise SystemExit(main())

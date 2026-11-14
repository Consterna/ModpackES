"""Línea de comandos: `modpackes instancias | analizar | cambios | traducir | exportar | paquete | …`."""

from __future__ import annotations

import argparse
import contextlib
import getpass
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from . import NOMBRE, __version__, configuracion
from .fuentes.instancia import Instancia
from .fuentes.lanzadores import buscar
from .fuentes.modpack import datos_del_modpack
from .modulos.cambios import Cambios
from .modulos.cobertura import informe_en_json
from .motores import fabrica
from .motores.base import Cancelado, ErrorFatal, Motor
from .motores.gemini import MODELO_POR_DEFECTO
from .motores.simulador import Simulador
from .nucleo.dialectos import DIALECTOS
from .nucleo.memoria import Memoria
from .proceso import GRUPOS, Informe, Proceso
from .registro import LOGGER, configurar
from .salida import exportar, mod_apoyo, paquete


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
    if informe.cambios is not None and informe.cambios.base == "indice":
        _escribir(informe.cambios.resumen() + " Detalle con «modpackes cambios».")
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
        p.add_argument(
            "--tambien-es-es",
            action="store_true",
            help="traducir además una versión aparte en español de España (solo va a es_es; cuesta otra traducción)",
        )
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
    cambios = sub.add_parser(
        "cambios", help="qué cambió desde la última traducción y cuánto cuesta traducir solo eso (no escribe nada)"
    )
    comunes(cambios)
    cambios.add_argument("--json", action="store_true", help="escribe solo el informe, como JSON (UTF-8)")
    traducir = sub.add_parser("traducir", help="traduce y escribe el resultado")
    comunes(traducir)
    traducir.add_argument("--hilos", type=int, default=4)
    traducir.add_argument(
        "--simular", action="store_true", help="prueba sin API: antepone «ES» a todo (no toca la memoria)"
    )
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
    exp = sub.add_parser("exportar", help="guarda el resource pack listo para publicar, o el kit de servidor")
    exp.add_argument("carpeta", help="carpeta de la instancia (o su carpeta minecraft)")
    exp.add_argument("archivo", nargs="?", default="", help="dónde guardarlo (por defecto, en la carpeta actual)")
    exp.add_argument("--kit", action="store_true", help="kit para servidores en vez del pack para jugadores")
    exp.add_argument("--revisado", action="store_true", help="avisa en el LEEME que una persona revisó la traducción")
    paq = sub.add_parser(
        "paquete", help=f"exporta o importa un paquete de traducción ({paquete.EXTENSION}) o un resource pack"
    )
    paq.add_argument("accion", choices=["exportar", "importar"])
    paq.add_argument("carpeta", help="carpeta de la instancia (o su carpeta minecraft)")
    paq.add_argument(
        "archivo",
        nargs="?",
        default="",
        help=f"exportar: dónde guardarlo (por defecto, en la carpeta actual) · importar: el {paquete.EXTENSION}, "
        "o un resource pack en español (.zip o carpeta)",
    )
    paq.add_argument("--dialecto", choices=list(DIALECTOS), default=None, help="por defecto es_mx o el del paquete")
    paq.add_argument("--revisado", action="store_true", help="exportar: anota que una persona revisó la traducción")
    paq.add_argument("--java", action="store_true", help="exportar: incluye el texto escrito en el código de los mods")
    paq.add_argument("--no-activar", action="store_true", help="importar: no tocar options.txt")
    paq.add_argument("--no-idioma", action="store_true", help="importar: no cambiar el idioma del juego")
    restaurar = sub.add_parser("restaurar", help="devuelve misiones, scripts y libros propios a su original")
    restaurar.add_argument("carpeta")
    modelos = sub.add_parser("modelos", help="lista los modelos que ofrece el motor")
    _opciones_de_motor(modelos)
    glosario = sub.add_parser("glosario", help="los términos que quieres que se traduzcan siempre igual")
    glosario.add_argument("accion", choices=["listar", "agregar", "quitar", "importar"])
    glosario.add_argument("valores", nargs="*", help="agregar INGLÉS ESPAÑOL · quitar INGLÉS · importar ARCHIVO.json")
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
    simular = args.orden == "traducir" and args.simular
    # Lo simulado («ES» delante) no puede ir a la memoria real: la próxima traducción de verdad lo reutilizaría
    with (
        Memoria(":memory:") if simular else contextlib.nullcontext() as memoria,
        Proceso(
            args.carpeta, motor, args.dialecto, grupos, memoria=memoria, registro=_escribir,
            hilos=getattr(args, "hilos", 4), usar_lotes=args.lotes, contexto=args.contexto, revisar=args.revisar,
            texto_java=args.java,
            scripts_exhaustivo=args.exhaustivo, tambien_es_es=args.tambien_es_es,
        ) as p,
    ):  # fmt: skip
        if simular:
            _escribir("Simulación: la memoria de traducciones no se toca.")
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


def _glosario(args: argparse.Namespace) -> None:
    """Edita el glosario del usuario: lo que escribes aquí manda sobre todo lo demás y se exige en cada texto."""
    terminos = configuracion.leer_glosario_usuario()
    valores: list[str] = args.valores
    if args.accion == "listar":
        for ingles, espanol in sorted(terminos.items(), key=lambda par: par[0].lower()):
            _escribir(f"{ingles} = {espanol}")
        _escribir(f"{len(terminos)} términos en {configuracion.ruta_glosario_usuario()}")
        return
    if args.accion == "agregar":
        if len(valores) != 2 or not valores[0].strip() or not valores[1].strip():
            raise ValueError('Uso: glosario agregar "INGLÉS" "ESPAÑOL"')
        terminos[valores[0].strip()] = valores[1].strip()
    elif args.accion == "quitar":
        if len(valores) != 1 or valores[0].strip() not in terminos:
            raise ValueError("Uso: glosario quitar INGLÉS (con un término que esté en el glosario)")
        del terminos[valores[0].strip()]
    else:
        if len(valores) != 1:
            raise ValueError("Uso: glosario importar ARCHIVO.json")
        try:
            nuevos: Any = json.loads(Path(valores[0]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ValueError(f"No pude leer {valores[0]}: {e}") from e
        if not isinstance(nuevos, dict):
            raise ValueError('El archivo debe ser un objeto JSON: {"inglés": "español", …}')
        terminos.update({str(k): str(v) for k, v in cast(dict[str, Any], nuevos).items() if isinstance(v, str)})
    configuracion.guardar_glosario_usuario(terminos)
    _escribir(f"Glosario guardado: {len(terminos)} términos.")


def _exportar(args: argparse.Namespace) -> None:
    with Instancia(args.carpeta) as inst:
        carpeta = inst.juego
    if args.kit:
        destino = Path(args.archivo or "Kit_servidor_traduccion.zip")
        n = exportar.exportar_kit_servidor(carpeta, destino)
    else:
        destino = Path(args.archivo or exportar.nombre_sugerido(carpeta))
        n = exportar.exportar_pack(carpeta, destino, revisado=args.revisado)
    _escribir(f"Exportado: {destino.resolve()} ({n} archivos)")


def _paquete(args: argparse.Namespace) -> None:
    """Exporta lo traducido de un modpack, o importa un paquete o resource pack y lo aplica sin llamar a la API."""
    archivo = Path(args.archivo) if args.archivo else None
    if args.accion == "importar":
        if archivo is None:
            raise ValueError(f"Uso: paquete importar CARPETA ARCHIVO ({paquete.EXTENSION}, .zip o carpeta)")
        dialecto = args.dialecto or (
            str(paquete.leer_metadatos(archivo)["dialecto"]) if paquete.es_paquete(archivo) else "es_mx"
        )
        with Proceso(args.carpeta, Simulador(), dialecto, registro=_escribir) as p:
            _escribir(f"Minecraft {p.instancia.version} · {p.instancia.loader or '¿loader?'} · {p.instancia.juego}")
            _, informe = paquete.aplicar(p, archivo, activar=not args.no_activar, poner_idioma=not args.no_idioma)
        args.motor, args.modelo, args.lotes, args.revisar = fabrica.GEMINI, "", False, False
        _mostrar(informe, args)
        return
    with Proceso(
        args.carpeta, Simulador(), args.dialecto or "es_mx", registro=_escribir, texto_java=args.java
    ) as p:  # fmt: skip
        destino = archivo or Path(paquete.nombre_de_archivo(datos_del_modpack(p.instancia.juego)))
        resumen = paquete.exportar_paquete(p, destino, revisado=args.revisado)
    for aviso in resumen.avisos:
        _escribir(f"⚠ {aviso}")
    _escribir(str(resumen))


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


def _cambios(args: argparse.Namespace) -> None:
    """Qué cambió en el inglés del modpack desde la última traducción, por mod y por archivo. Solo lee."""
    if args.lotes and args.motor != fabrica.GEMINI:
        raise ErrorFatal("--lotes solo funciona con Gemini.")
    grupos = [g.strip() for g in args.solo.split(",") if g.strip()]
    with Proceso(
        args.carpeta, Simulador(), args.dialecto, grupos, registro=(lambda _m: None) if args.json else _escribir,
        texto_java=args.java, scripts_exhaustivo=args.exhaustivo, tambien_es_es=args.tambien_es_es,
    ) as p:  # fmt: skip
        if not args.json:
            _escribir(f"Minecraft {p.instancia.version} · {p.instancia.loader or '¿loader?'} · {p.instancia.juego}")
        informe = p.analizar()
    cambios = informe.cambios or Cambios()
    diferencia = informe.diferencia
    modelo = _modelo(args)
    costo = diferencia.costo(modelo, args.lotes, args.motor, args.revisar)
    if args.json:
        datos = {
            "base": cambios.base, "fecha": cambios.fecha, "nuevas": cambios.nuevas, "cambiadas": cambios.cambiadas,
            "borradas": cambios.borradas, "a_traducir": diferencia.a_traducir, "caracteres": diferencia.caracteres,
            "costo": costo, "modelo": modelo, "lugares": cambios.en_json(),
        }  # fmt: skip
        _escribir(json.dumps(datos, ensure_ascii=False, indent=2))
        return
    if cambios.base == "memoria":
        _escribir(
            "No hay índice de una traducción anterior (nunca se tradujo con esta versión de la app): "
            "cuento como nuevo lo que no está en la memoria. Tras la próxima traducción se compara clave por clave."
        )
    _escribir(cambios.texto())
    if not cambios.lugares:
        return
    _escribir(
        f"Para traducir solo lo nuevo y lo cambiado: {diferencia.a_traducir} textos para el motor, "
        f"{diferencia.caracteres} caracteres (el resto sale de la memoria)"
    )
    if costo is not None:
        _escribir(f"Costo estimado con {modelo}{' (por lotes)' if args.lotes else ''}: US$ {costo:.2f}")
    _escribir("Para aplicarlo: «modpackes traducir» (lo que ya está en la memoria no se vuelve a pagar).")


#: Órdenes que solo llaman a una función con los argumentos.
_ORDENES: dict[str, Callable[[argparse.Namespace], None]] = {
    "instalar-runtime": _instalar_runtime,
    "cobertura": _cobertura,
    "cambios": _cambios,
    "glosario": _glosario,
    "exportar": _exportar,
    "paquete": _paquete,
}


def main(argv: Sequence[str] | None = None) -> int:
    cast(Any, sys.stdout).reconfigure(encoding="utf-8", errors="replace")
    args = _argumentos().parse_args(argv)
    configurar(configuracion.carpeta_datos())
    LOGGER.info("Línea de comandos: %s", args.orden)
    try:
        if args.orden == "instancias":
            for e in buscar():
                _escribir(f"{e.lanzador}: {e.nombre}\n    {e.juego}")
        elif args.orden in _ORDENES:
            _ORDENES[args.orden](args)
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
    except (ErrorFatal, ValueError, OSError) as e:  # como la ventana: un archivo bloqueado o sin permiso no es un fallo
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

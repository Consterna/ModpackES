"""Paquete de traducción (`.modpackes.zip`): una persona traduce y paga; las demás lo aplican gratis.

Lleva la parte de la memoria que usa el modpack, las correcciones de esos textos, el glosario del usuario y
unos metadatos (pack, versión, modelos, dialecto, si se revisó). Importarlo no llama a ningún motor: guarda
todo en la memoria local y escribe la traducción como si saliera de ella.

También se puede importar un resource pack en español (`.zip` o carpeta), esté o no activo en el juego: sus
textos se emparejan con el inglés de la instancia y pasan a la memoria del mismo modo.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .. import NOMBRE as NOMBRE_APP
from .. import __version__, configuracion
from ..fuentes.modpack import DatosModpack, datos_del_modpack
from ..fuentes.recursos import PRIORIDAD_PACKS, Fuente, abrir_pack, leer_idiomas
from ..modulos.base import contar
from ..nucleo.dialectos import DIALECTOS, VARIANTES
from ..nucleo.mascara import es_traducible, separar_bordes
from ..nucleo.memoria import Fila, codigos_iguales

if TYPE_CHECKING:
    from ..proceso import Informe, Proceso

EXTENSION = ".modpackes.zip"
#: Versión del formato del paquete. Un paquete de un formato más nuevo no se importa (pide actualizar la app).
FORMATO = 1
_META, _MEMORIA, _CORRECCIONES, _GLOSARIO = "modpackes.json", "memoria.json", "correcciones.json", "glosario.json"
_AMBITOS = frozenset({"ui", "mision", "libro", "script"})
#: Topes al leer un paquete ajeno: nadie debería poder llenar la memoria o la RAM con un archivo preparado.
_MAX_ARCHIVO, _MAX_META, _MAX_TEXTO, _MAX_TERMINO = 128 * 1024 * 1024, 1024 * 1024, 20_000, 200
#: Motores cuyo resultado no es una traducción de verdad: no se comparten.
_NO_SE_COMPARTE = frozenset({"simulador"})


@dataclass(slots=True)
class ResumenExportacion:
    ruta: Path
    memoria: int = 0
    correcciones: int = 0
    glosario: int = 0
    modelos: list[str] = field(default_factory=list[str])
    avisos: list[str] = field(default_factory=list[str])

    def __str__(self) -> str:
        partes = [
            contar(self.memoria, "traducción", "traducciones"),
            contar(self.correcciones, "corrección", "correcciones"),
            contar(self.glosario, "término del glosario", "términos del glosario"),
        ]
        return f"Paquete guardado en {self.ruta}: " + ", ".join(partes) + "."


@dataclass(slots=True)
class ResumenImportacion:
    origen: str  #: «paquete» o «resource pack»
    memoria: int = 0
    correcciones: int = 0
    glosario: int = 0
    descartados: int = 0  #: textos que no pasaron las comprobaciones (vacíos, códigos cambiados…)
    conservados: int = 0  #: correcciones y términos tuyos que se dejaron como estaban
    modelos: list[str] = field(default_factory=list[str])
    avisos: list[str] = field(default_factory=list[str])

    def __str__(self) -> str:
        partes = [contar(self.memoria, "traducción", "traducciones")]
        if self.origen == "paquete":
            partes += [
                contar(self.correcciones, "corrección", "correcciones"),
                contar(self.glosario, "término nuevo", "términos nuevos") + " en el glosario",
            ]
        texto = f"Importado ({self.origen}): " + ", ".join(partes) + "."
        if self.conservados:
            texto += f" Se mantuvieron {self.conservados} correcciones o términos tuyos que eran distintos."
        if self.descartados:
            texto += f" Se descartaron {contar(self.descartados, 'texto dañado', 'textos dañados')}."
        return texto


# ------------------------------------------------------------------ exportar
def nombre_de_archivo(datos: DatosModpack, extension: str = EXTENSION, prefijo: str = "") -> str:
    """Nombre de archivo con el modpack y su versión, sin caracteres que Windows no acepte."""
    partes = [p for p in (prefijo, datos.nombre, datos.version) if p]
    limpio = "_".join(re.sub(r"[^\w.\-]+", "_", p).strip("._") for p in partes)
    return (limpio or "traduccion") + extension


def textos_del_modpack(proceso: Proceso) -> tuple[set[tuple[str, str]], list[str]]:
    """Los textos (núcleo, ámbito) que la traducción del modpack busca en la memoria. Solo lee.

    Son los mismos que reúne el análisis: así el paquete lleva justo lo que este pack necesita.
    """
    textos: set[tuple[str, str]] = set()
    avisos: list[str] = []
    for _grupo, modulo in proceso.modulos():
        try:
            piezas = modulo.recolectar()
        except (ValueError, OSError) as e:
            avisos.append(f"{modulo.nombre}: no se pudo leer ({e}). Queda fuera del paquete.")
            continue
        textos |= {(separar_bordes(p.texto)[1], modulo.ambito) for p in piezas if es_traducible(p.texto)}
    return textos, avisos


def exportar_paquete(proceso: Proceso, destino: Path, revisado: bool = False) -> ResumenExportacion:
    """Guarda el paquete del modpack de `proceso` en `destino`."""
    dialecto = proceso.ctx.dialecto
    textos, avisos = textos_del_modpack(proceso)
    filas = [f for f in proceso.memoria.filas(textos, dialecto) if f.motor not in _NO_SE_COMPARTE]
    nucleos = {n for n, _ in textos}
    correcciones = {o: t for o, t in proceso.memoria.correcciones(dialecto).items() if o in nucleos}
    glosario = configuracion.leer_glosario_usuario()
    if not filas and not correcciones:
        raise ValueError("La memoria no tiene traducciones de este modpack en ese dialecto: traduce primero.")
    datos = datos_del_modpack(proceso.instancia.juego)
    modelos = sorted({f.motor for f in filas})
    meta: dict[str, Any] = {
        "formato": FORMATO,
        "app": NOMBRE_APP,
        "version_app": __version__,
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "modpack": {"nombre": datos.nombre, "version": datos.version},
        "minecraft": proceso.instancia.version.texto,
        "loader": proceso.instancia.loader or "",
        "dialecto": dialecto,
        "revisado": revisado,
        "modelos": modelos,
        "cantidades": {"memoria": len(filas), "correcciones": len(correcciones), "glosario": len(glosario)},
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".tmp")
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_META, _json(meta))
        filas_json = [{"origen": f.origen, "ambito": f.ambito, "traduccion": f.traduccion, "motor": f.motor}
                      for f in filas]  # fmt: skip
        zf.writestr(_MEMORIA, _json(filas_json))
        zf.writestr(_CORRECCIONES, _json(dict(sorted(correcciones.items()))))
        zf.writestr(_GLOSARIO, _json(dict(sorted(glosario.items()))))
    temporal.replace(destino)
    return ResumenExportacion(destino, len(filas), len(correcciones), len(glosario), modelos, avisos)


def _json(datos: object) -> bytes:
    return (json.dumps(datos, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


# ------------------------------------------------------------------ leer un paquete ajeno
def es_paquete(ruta: Path) -> bool:
    if not ruta.is_file() or not zipfile.is_zipfile(ruta):
        return False
    with zipfile.ZipFile(ruta) as zf:
        return _META in zf.namelist()


def _leer(zf: zipfile.ZipFile, nombre: str, maximo: int = _MAX_ARCHIVO) -> Any:
    try:
        info = zf.getinfo(nombre)
    except KeyError:
        return None
    if info.file_size > maximo:
        raise ValueError(f"El paquete trae un {nombre} demasiado grande.")
    with zf.open(info) as f:
        datos = f.read(maximo + 1)
    if len(datos) > maximo:
        raise ValueError(f"El paquete trae un {nombre} demasiado grande.")
    try:
        return json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ValueError(f"El paquete está dañado ({nombre}: {e}).") from e


def leer_metadatos(ruta: Path) -> dict[str, Any]:
    """Los metadatos de un paquete, comprobados. Lanza ValueError si no es un paquete que esta app entienda."""
    try:
        with zipfile.ZipFile(ruta) as zf:
            meta = _leer(zf, _META, _MAX_META)
    except (zipfile.BadZipFile, OSError) as e:
        raise ValueError(f"No pude abrir {ruta.name}: {e}") from e
    if not isinstance(meta, dict):
        raise ValueError(f"{ruta.name} no es un paquete de traducción de {NOMBRE_APP}.")
    datos = cast(dict[str, Any], meta)
    formato = datos.get("formato")
    if not isinstance(formato, int) or formato < 1:
        raise ValueError(f"{ruta.name} no es un paquete de traducción de {NOMBRE_APP}.")
    if formato > FORMATO:
        raise ValueError("El paquete se hizo con una versión más nueva de la app: actualízala para importarlo.")
    if datos.get("dialecto") not in DIALECTOS:
        raise ValueError(f"El paquete no dice en qué español está (dialecto {datos.get('dialecto')!r}).")
    return datos


def _texto_valido(origen: object, traduccion: object) -> bool:
    return (
        isinstance(origen, str)
        and isinstance(traduccion, str)
        and 0 < len(origen) <= _MAX_TEXTO
        and 0 < len(traduccion.strip()) <= _MAX_TEXTO
        and origen == origen.strip()
        and codigos_iguales(origen, traduccion)
    )


def _filas_validas(crudo: object, resumen: ResumenImportacion) -> list[Fila]:
    filas: list[Fila] = []
    for item in cast(list[object], crudo) if isinstance(crudo, list) else []:
        d = cast(dict[str, Any], item) if isinstance(item, dict) else {}
        origen, ambito, traduccion, motor = d.get("origen"), d.get("ambito"), d.get("traduccion"), d.get("motor")
        if ambito not in _AMBITOS or not isinstance(motor, str) or not _texto_valido(origen, traduccion):
            resumen.descartados += 1
            continue
        filas.append(Fila(cast(str, origen), cast(str, ambito), cast(str, traduccion).strip(), motor[:200]))
    return filas


def _pares_validos(crudo: object, largo: int, resumen: ResumenImportacion) -> dict[str, str]:
    pares: dict[str, str] = {}
    elementos: list[tuple[object, object]] = (
        list(cast(dict[object, object], crudo).items()) if isinstance(crudo, dict) else []
    )
    for clave, valor in elementos:
        if (
            isinstance(clave, str)
            and isinstance(valor, str)
            and clave.strip()
            and valor.strip()
            and (len(clave) <= largo and len(valor) <= largo)
        ):
            pares[clave.strip()] = valor.strip()
        else:
            resumen.descartados += 1
    return pares


def _avisos_de_version(proceso: Proceso, meta: dict[str, Any]) -> list[str]:
    avisos: list[str] = []
    propio = datos_del_modpack(proceso.instancia.juego)
    modpack = cast(dict[str, Any], meta.get("modpack")) if isinstance(meta.get("modpack"), dict) else {}
    nombre, version = str(modpack.get("nombre") or ""), str(modpack.get("version") or "")
    if nombre and nombre.casefold() != propio.nombre.casefold():
        avisos.append(f"El paquete es de «{nombre}» y esta instancia parece «{propio.nombre}».")
    if version and propio.version and version != propio.version:
        avisos.append(
            f"El paquete se hizo para la versión {version} del modpack y esta instancia tiene la {propio.version}: "
            "lo que haya cambiado quedará en inglés."
        )
    minecraft = str(meta.get("minecraft") or "")
    if minecraft and minecraft != proceso.instancia.version.texto:
        avisos.append(f"El paquete es de Minecraft {minecraft} y esta instancia es {proceso.instancia.version}.")
    return avisos


def importar_paquete(proceso: Proceso, ruta: Path) -> ResumenImportacion:
    """Guarda el paquete en la memoria local y en el glosario. Tus correcciones y términos no se pisan."""
    meta = leer_metadatos(ruta)
    dialecto = str(meta["dialecto"])
    if dialecto != proceso.ctx.dialecto:
        raise ValueError(f"El paquete está en {dialecto}: elige ese dialecto para importarlo.")
    resumen = ResumenImportacion("paquete")
    with zipfile.ZipFile(ruta) as zf:
        filas = _filas_validas(_leer(zf, _MEMORIA), resumen)
        correcciones = _pares_validos(_leer(zf, _CORRECCIONES), _MAX_TEXTO, resumen)
        glosario = _pares_validos(_leer(zf, _GLOSARIO), _MAX_TERMINO, resumen)
    resumen.avisos = _avisos_de_version(proceso, meta)
    resumen.modelos = sorted({f.motor for f in filas})
    resumen.memoria = proceso.memoria.importar(filas, dialecto)
    mias = proceso.memoria.correcciones(dialecto)
    for origen, traduccion in correcciones.items():
        if origen in mias:
            resumen.conservados += mias[origen] != traduccion
            continue
        if not _texto_valido(origen, traduccion):
            resumen.descartados += 1
            continue
        proceso.memoria.corregir(origen, dialecto, traduccion)
        resumen.correcciones += 1
    terminos = configuracion.leer_glosario_usuario()
    nuevos = {en: es for en, es in glosario.items() if en not in terminos}
    resumen.conservados += sum(1 for en, es in glosario.items() if en in terminos and terminos[en] != es)
    if nuevos:
        configuracion.guardar_glosario_usuario({**terminos, **nuevos})
    resumen.glosario = len(nuevos)
    return resumen


def importar_resource_pack(proceso: Proceso, ruta: Path) -> ResumenImportacion:
    """Lee los textos en español de un resource pack (activo o no) y los guarda en la memoria."""
    contenedor = abrir_pack(ruta)
    if contenedor is not None and not any(n.startswith("assets/") for n in contenedor.nombres()):
        contenedor.cerrar()
        contenedor = None
    if contenedor is None:
        raise ValueError(f"{ruta.name} no es un resource pack (le falta la carpeta assets).")
    try:
        externo = leer_idiomas(
            [Fuente(contenedor, PRIORIDAD_PACKS, "pack")], ("en_us", *VARIANTES), proceso.instancia.legacy
        )
        nombre = contenedor.nombre
    finally:
        contenedor.cerrar()
    dialecto = proceso.ctx.dialecto
    orden = list(dict.fromkeys((dialecto, "es_mx", "es_es", *VARIANTES)))
    juego = proceso.instancia.tabla_idiomas()
    resumen = ResumenImportacion("resource pack")
    pares: dict[str, str] = {}
    for ns, por_idioma in externo.datos.items():
        ingles = {**externo.textos(ns, "en_us"), **juego.textos(ns, "en_us")}  # manda el inglés de la instancia
        claves = {c for v in orden for c in por_idioma.get(v, {})}
        for clave in sorted(claves):
            espanol = next(por_idioma[v][clave].valor for v in orden if clave in por_idioma.get(v, {}))
            en = ingles.get(clave)
            if en is None or not es_traducible(en):
                continue  # una clave que este modpack no usa, o sin nada que traducir
            original, traduccion = separar_bordes(en)[1], separar_bordes(espanol)[1]
            if traduccion == original or not _texto_valido(original, traduccion):
                resumen.descartados += 1
                continue
            pares[original] = traduccion
    if not pares:
        raise ValueError(f"{ruta.name} no tiene textos en español de los mods de esta instancia.")
    motor = f"pack:{nombre}"
    proceso.memoria.guardar(pares, dialecto, "ui", motor)
    resumen.memoria, resumen.modelos = len(pares), [motor]
    return resumen


def importar(proceso: Proceso, ruta: Path) -> ResumenImportacion:
    """Un paquete `.modpackes.zip` o un resource pack (`.zip` o carpeta), según lo que sea `ruta`."""
    if es_paquete(ruta):
        return importar_paquete(proceso, ruta)
    if ruta.is_dir() or (ruta.is_file() and ruta.suffix.lower() == ".zip"):
        return importar_resource_pack(proceso, ruta)
    raise ValueError(f"No sé importar {ruta.name}: elige un {EXTENSION}, un resource pack en .zip o su carpeta.")


def aplicar(
    proceso: Proceso, ruta: Path, activar: bool = True, poner_idioma: bool = True
) -> tuple[ResumenImportacion, Informe]:
    """Importa y escribe la traducción sin llamar a ningún motor. Lo que no traiga queda en inglés."""
    resumen = importar(proceso, ruta)
    proceso.registro(str(resumen))
    informe = proceso.ejecutar(activar=activar, poner_idioma=poner_idioma, solo_memoria=True)
    if proceso.ctx.pack is not None:
        proceso.ctx.pack.anotar_motores(resumen.modelos)
    informe.avisos[:0] = resumen.avisos
    return resumen, informe

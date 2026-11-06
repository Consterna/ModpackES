"""Textos de datapacks y packs de recursos que el jugador ve en el chat o en pantalla: funciones, logros y tips.

Los archivos se buscan por su **estructura** y no por la carpeta de un modpack concreto: cualquier ruta que
contenga `data/<espacio>/function(s)/…`, `data/<espacio>/advancement(s)/…` o `assets/<espacio>/tips/…` cuenta,
esté en `kubejs/data`, `global_packs/*/*`, `datapacks`, `config/openloader`, `saves/*/datapacks`… Cada formato
reconocido es un `Formato` con su documentación; lo que no se reconoce no se toca. Se traduce en el sitio, con
copia de seguridad.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ..formatos import comandos, componente
from ..nucleo.mascara import es_traducible
from ..salida.resource_pack import NOMBRE as NOMBRE_PACK_SALIDA
from .base import Contexto, Pieza, Resumen, contar, parece_clave
from .scripts import AMBITO, aplicar_comando, unidades_comando

#: Carpetas que nunca se recorren: cachés, registros, mods (sus jars se leen en otro sitio) y lo que genera la app.
IGNORAR = frozenset({
    "mods", "logs", "crash-reports", "traductor_es", "cache", "libraries", "versions", "screenshots", "shaderpacks",
    "backups", "probe", "node_modules", "modernfix", "xaerowaypoints", "xaeroworldmap", "journeymap",
    NOMBRE_PACK_SALIDA.lower(),
})  # fmt: skip
PROFUNDIDAD_MAXIMA = 10
LIMITE_ZIP = 64 * 1024 * 1024  #: más grande que esto no es un datapack, es un resource pack pesado: no se abre
CAMPOS_LOGRO = ("title", "description")


def _componente(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False)


def _traducibles(partes: list[str] | None) -> list[str]:
    return [p for p in partes or [] if not parece_clave(p)]


def _nodos(datos: Any, claves: tuple[str, ...]) -> list[tuple[dict[str, Any], str]]:
    """(diccionario, clave) de cada valor de texto que hay que traducir dentro de un JSON."""
    if not isinstance(datos, dict):
        return []
    d = cast("dict[str, Any]", datos)
    return [(d, k) for k in claves if k in d]


# ---------------------------------------------------------------- funciones (.mcfunction)
def _lineas(texto: str) -> list[tuple[str, comandos.Comando | None, str]]:
    """Cada línea separada en (línea sin fin, su comando de chat, fin de línea)."""
    res: list[tuple[str, comandos.Comando | None, str]] = []
    for linea in texto.split("\n"):
        fin = "\r" if linea.endswith("\r") else ""
        cuerpo = linea[: len(linea) - len(fin)]
        cmd = comandos.analizar(cuerpo)
        res.append((cuerpo, cmd if cmd is not None and unidades_comando(cmd) else None, fin))
    return res


def _unidades_funcion(texto: str) -> list[str]:
    return [t for _, cmd, _ in _lineas(texto) if cmd for t in unidades_comando(cmd)]


def _reescribir_funcion(texto: str, traducciones: Mapping[str, str]) -> str:
    return "\n".join((aplicar_comando(cmd, traducciones) if cmd else linea) + fin for linea, cmd, fin in _lineas(texto))


# ---------------------------------------------------------------- JSON con componentes (logros, tips)
def _nodos_logro(datos: Any) -> list[tuple[dict[str, Any], str]]:
    """`display.title` y `display.description` de un logro."""
    display = cast("dict[str, Any]", datos).get("display") if isinstance(datos, dict) else None
    return _nodos(display, CAMPOS_LOGRO)


def _nodos_tip(datos: Any) -> list[tuple[dict[str, Any], str]]:
    """Tips: `{"tip": …}` (Tips de Darkhax) y `{"tips": [{"text": …}]}` (el port de NeoForge)."""
    if not isinstance(datos, dict):
        return []
    d = cast("dict[str, Any]", datos)
    nodos = _nodos(d, ("tip",))
    lista = d.get("tips")
    if isinstance(lista, list):
        for t in cast("list[Any]", lista):
            nodos += _nodos(t, ("text",))
    return nodos


def _unidades_json(texto: str, nodos: Callable[[Any], list[tuple[dict[str, Any], str]]]) -> list[str]:
    return [u for d, k in nodos(json.loads(texto)) for u in _traducibles(componente.unidades(_componente(d[k])))]


def _reescribir_json(
    texto: str, traducciones: Mapping[str, str], nodos: Callable[[Any], list[tuple[dict[str, Any], str]]]
) -> str:
    datos = json.loads(texto)
    for d, k in nodos(datos):
        d[k] = json.loads(componente.reconstruir(_componente(d[k]), traducciones))
    return json.dumps(datos, indent=2, ensure_ascii=False) + "\n"


@dataclass(frozen=True, slots=True)
class Formato:
    nombre: str
    pista: str  #: contexto que se le da al motor de traducción
    reconoce: Callable[[tuple[str, ...]], bool]  #: recibe la ruta desde «data» o «assets»: (data, espacio, carpeta, …)
    unidades: Callable[[str], list[str]]  #: puede lanzar ValueError si el archivo no se entiende
    reescribir: Callable[[str, Mapping[str, str]], str]


def _es(ruta: tuple[str, ...], raiz: str, carpetas: tuple[str, ...], sufijo: str) -> bool:
    return len(ruta) >= 4 and ruta[0] == raiz and ruta[2] in carpetas and ruta[-1].lower().endswith(sufijo)


FORMATOS: tuple[Formato, ...] = (
    Formato(
        "función", "mensaje de una función",
        lambda r: _es(r, "data", ("function", "functions"), ".mcfunction"),
        _unidades_funcion, _reescribir_funcion,
    ),
    Formato(
        "logro", "logro del juego",
        lambda r: _es(r, "data", ("advancement", "advancements"), ".json"),
        lambda t: _unidades_json(t, _nodos_logro), lambda t, tr: _reescribir_json(t, tr, _nodos_logro),
    ),
    Formato(
        "tip", "consejo de las pantallas de carga",
        lambda r: _es(r, "assets", ("tips",), ".json") or (_es(r, "data", ("tips",), ".json") and r[1] == "tipsmod"),
        lambda t: _unidades_json(t, _nodos_tip), lambda t, tr: _reescribir_json(t, tr, _nodos_tip),
    ),
)  # fmt: skip


def clasificar(ruta: Path) -> Formato | None:
    """El formato de este archivo según su ruta, o None. Busca el ancla «data» o «assets» en cualquier posición."""
    partes = ruta.parts
    for i, parte in enumerate(partes):
        if parte in ("data", "assets"):
            for formato in FORMATOS:
                if formato.reconoce(partes[i:]):
                    return formato
    return None


def _recorrer(juego: Path) -> Iterator[Path]:
    """Cada archivo de la instancia, sin entrar en mods, cachés ni mundos (de un mundo solo sus datapacks)."""
    base = len(juego.parts)
    for raiz, carpetas, archivos in os.walk(juego):
        actual = Path(raiz)
        if len(actual.parts) - base >= PROFUNDIDAD_MAXIMA:
            carpetas.clear()
        elif actual.parent.name.lower() == "saves":
            carpetas[:] = [c for c in carpetas if c.lower() == "datapacks"]
        else:
            carpetas[:] = sorted(c for c in carpetas if c.lower() not in IGNORAR and not c.startswith("."))
        for nombre in sorted(archivos):
            yield actual / nombre


def buscar_archivos(juego: Path) -> list[tuple[Path, Formato]]:
    """Todos los archivos de texto conocidos que están sueltos en la instancia."""
    encontrados: list[tuple[Path, Formato]] = []
    for ruta in _recorrer(juego):
        if (formato := clasificar(ruta.relative_to(juego))) is not None:
            encontrados.append((ruta, formato))
    return encontrados


def _entradas_del_zip(ruta: Path) -> list[tuple[str, Formato]]:
    """Las entradas de un .zip (datapack o pack de recursos) con texto conocido. Solo lee su índice."""
    if ruta.stat().st_size > LIMITE_ZIP:
        return []
    try:
        with zipfile.ZipFile(ruta) as z:
            return [(n, f) for n in z.namelist() if not n.endswith("/") and (f := clasificar(Path(n))) is not None]
    except (zipfile.BadZipFile, OSError):
        return []


def buscar_zips(juego: Path) -> list[tuple[Path, list[tuple[str, Formato]]]]:
    """Los .zip con texto conocido dentro (datapacks de `global_packs`, `datapacks`, mundos…)."""
    res: list[tuple[Path, list[tuple[str, Formato]]]] = []
    for ruta in _recorrer(juego):
        if ruta.suffix.lower() == ".zip" and (entradas := _entradas_del_zip(ruta)):
            res.append((ruta, entradas))
    return res


@dataclass(slots=True)
class _Archivo:
    ruta: Path  #: el archivo suelto o el .zip que lo contiene
    formato: Formato
    texto: str
    piezas: list[str] = field(default_factory=list[str])
    entrada: str | None = None  #: nombre dentro del .zip; None si es un archivo suelto


def _reescribir_zip(original: bytes, nuevos: Mapping[str, str]) -> bytes:
    """El mismo .zip con esas entradas cambiadas; las demás, el orden y las fechas quedan igual."""
    salida = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as entrada, zipfile.ZipFile(salida, "w") as z:
        for info in entrada.infolist():
            datos = nuevos[info.filename].encode("utf-8") if info.filename in nuevos else entrada.read(info)
            z.writestr(info, datos, compress_type=info.compress_type)
    return salida.getvalue()


class Datos:
    nombre = "Funciones, logros y tips"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._leidos: list[_Archivo] = []
        self._zips: dict[Path, bytes] = {}  #: contenido original de cada .zip leído

    def detectar(self) -> bool:
        juego = self.ctx.instancia.juego
        return bool(buscar_archivos(juego) or buscar_zips(juego))

    def describir(self) -> str:
        juego = self.ctx.instancia.juego
        n = len(buscar_archivos(juego)) + sum(len(e) for _, e in buscar_zips(juego))
        return contar(n, "archivo de datos", "archivos de datos")

    def _leer(self, ruta: Path, formato: Formato, datos: bytes, entrada: str | None) -> list[Pieza]:
        try:
            texto = datos.decode("utf-8-sig")
            unidades = [t for t in formato.unidades(texto) if es_traducible(t)]
        except (ValueError, UnicodeDecodeError):
            self.ctx.registro(f"{entrada or ruta.name}: no pude leerlo con seguridad, se deja igual")
            return []
        if not unidades:
            return []
        self._leidos.append(_Archivo(ruta, formato, texto, unidades, entrada))
        return [Pieza(t, formato.pista) for t in unidades]

    def recolectar(self) -> list[Pieza]:
        self._leidos, self._zips = [], {}
        juego = self.ctx.instancia.juego
        piezas: list[Pieza] = []
        for ruta, formato in buscar_archivos(juego):
            if (original := self.ctx.respaldo.original(ruta)) is not None:
                piezas += self._leer(ruta, formato, original, None)
        for ruta, entradas in buscar_zips(juego):
            if (original := self.ctx.respaldo.original(ruta)) is None:
                continue
            try:
                with zipfile.ZipFile(io.BytesIO(original)) as z:
                    contenidos = [(n, f, z.read(n)) for n, f in entradas]
            except (zipfile.BadZipFile, OSError, KeyError):
                self.ctx.registro(f"{ruta.name}: no pude abrirlo, se deja igual")
                continue
            self._zips[ruta] = original
            for nombre, formato, datos in contenidos:
                piezas += self._leer(ruta, formato, datos, nombre)
        return piezas

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        en_zip: dict[Path, dict[str, str]] = {}
        for a in self._leidos:
            hechas = sum(1 for t in set(a.piezas) if t in traducciones)
            resumen.traducidos += hechas
            resumen.pendientes += len(set(a.piezas)) - hechas
            nuevo = a.formato.reescribir(a.texto, traducciones)
            if not hechas or nuevo == a.texto:
                continue
            if a.entrada is not None:
                en_zip.setdefault(a.ruta, {})[a.entrada] = nuevo
            elif not a.ruta.is_file() or a.ruta.read_bytes() != nuevo.encode("utf-8"):  # en bytes: sin traducir \r\n
                self.ctx.respaldo.escribir(a.ruta, nuevo.encode("utf-8"))
                resumen.archivos.append(a.ruta)
        for ruta, nuevos in en_zip.items():
            datos = _reescribir_zip(self._zips[ruta], nuevos)
            if ruta.read_bytes() != datos:
                self.ctx.respaldo.escribir(ruta, datos)
                resumen.archivos.append(ruta)
        return resumen

    def restaurar(self) -> list[Path]:
        juego = self.ctx.instancia.juego
        propios = [r for r in self.ctx.respaldo.registrados() if clasificar(Path(r)) is not None or r.endswith(".zip")]
        hechos: list[Path] = []
        for ruta in propios:  # Respaldo restaura por prefijo: la ruta completa es el prefijo más estricto
            hechos += self.ctx.respaldo.restaurar(ruta) if (juego / ruta).exists() else []
        return hechos

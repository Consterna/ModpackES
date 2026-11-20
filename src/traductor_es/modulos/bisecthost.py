"""Anuncio de servidor de BisectHost Menu: `config/bhmenu-client.toml`.

El banner «Need a server?» muestra `title` y `description` de `[modules.server_creator_banner.pack]` tal cual, salvo que
`use_language_files = true` (entonces usa las claves `server_entry.title` y `server_entry.description`, y ese texto ya
lo traduce el módulo de mods si alguien las define). El archivo tiene un solo idioma: se reescribe en su lugar con copia
y solo cambian esas dos cadenas, línea por línea; lo demás (ids, comentarios, orden) queda igual byte por byte.
Un código de descuento («Use CODE: LunaPixel for 25% OFF!») se protege para que llegue exacto.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, contar, parece_clave
from .cambios import Lugar

AMBITO = "ui"
ARCHIVO = "config/bhmenu-client.toml"
TABLA = ("modules", "server_creator_banner", "pack")
CAMPOS = ("title", "description")
PISTA = "anuncio de un servidor en el menú multijugador: corto"
#: Una línea `campo = "texto"` (cadena básica de TOML, sin saltos de línea)
_LINEA = re.compile(
    r'^(?P<antes>\s*(?P<campo>[A-Za-z_]+)\s*=\s*)(?P<valor>"(?:[^"\\\r\n]|\\.)*")(?P<despues>[^\r\n]*)$'
)
_TABLA = re.compile(r"^\s*\[(?P<nombre>[^\[\]]+)\]\s*(?:#.*)?$")
#: El código de un cupón: la palabra que sigue a «code» se manda protegida
_CODIGO = re.compile(r"(?i)(?<=\bcode)(\s*:?\s*)([A-Za-z0-9_-]+)")


def marcar(texto: str) -> tuple[str, list[str]]:
    """El texto con cada código de cupón cambiado por `{pN}` (la máscara lo protege) y la lista de códigos."""
    codigos: list[str] = []

    def cambiar(m: re.Match[str]) -> str:
        codigos.append(m.group(2))
        return f"{m.group(1)}{{p{len(codigos) - 1}}}"

    return _CODIGO.sub(cambiar, texto), codigos


def desmarcar(traducido: str, codigos: list[str]) -> str | None:
    """Los códigos de vuelta; None si el motor perdió o inventó alguno."""
    if sorted(re.findall(r"\{p(\d+)\}", traducido)) != sorted(str(i) for i in range(len(codigos))):
        return None
    return re.sub(r"\{p(\d+)\}", lambda m: codigos[int(m.group(1))], traducido)


def escapar(texto: str) -> str:
    """Una cadena básica de TOML con ese texto."""
    cuerpo = texto.replace("\\", "\\\\").replace('"', '\\"')
    cuerpo = re.sub(r"[\x00-\x1f\x7f]", lambda m: f"\\u{ord(m.group()):04X}", cuerpo)
    return f'"{cuerpo}"'


@dataclass(slots=True)
class _Linea:
    numero: int
    campo: str
    texto: str


@dataclass(slots=True)
class _Archivo:
    ruta: Path
    lineas: list[str]  #: con su fin de línea
    elegidas: list[_Linea]


def leer(src: str) -> list[_Linea]:
    """Las líneas del título y la descripción del banner que se ven tal cual (vacío si usa archivos de idioma)."""
    datos = tomllib.loads(src)
    tabla: object = datos
    for parte in TABLA:
        tabla = tabla.get(parte) if isinstance(tabla, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(tabla, dict) or tabla.get("use_language_files") is True:  # pyright: ignore[reportUnknownMemberType]
        return []
    res: list[_Linea] = []
    actual: tuple[str, ...] = ()
    for i, linea in enumerate(src.splitlines()):
        if m := _TABLA.match(linea):
            actual = tuple(p.strip().strip('"') for p in m.group("nombre").split("."))
            continue
        m = _LINEA.match(linea)
        if actual != TABLA or m is None or m.group("campo") not in CAMPOS:
            continue
        texto = tomllib.loads(f"v = {m.group('valor')}")["v"]
        # Solo si la línea dice lo mismo que el archivo leído entero (si no, algo raro: no se toca)
        if texto == tabla.get(m.group("campo")) and texto.strip() and es_traducible(texto) and not parece_clave(texto):  # pyright: ignore[reportUnknownMemberType]
            res.append(_Linea(i, m.group("campo"), texto))
    return res


class BisectHost:
    nombre = "Anuncio de BisectHost"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._archivo: _Archivo | None = None

    def _ruta(self) -> Path:
        return self.ctx.instancia.juego / ARCHIVO

    def detectar(self) -> bool:
        return self._ruta().is_file()

    def describir(self) -> str:
        return contar(1 if self.detectar() else 0, "anuncio", "anuncios")

    def recolectar(self) -> list[Pieza]:
        self._archivo = None
        ruta = self._ruta()
        original = self.ctx.respaldo.original(ruta)
        if original is None:
            return []
        try:
            src = original.decode("utf-8")
            elegidas = leer(src)
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            self.ctx.registro(f"{ruta.name}: no pude leerlo con seguridad, se deja igual")
            return []
        if not elegidas:
            return []
        self._archivo = _Archivo(ruta, src.splitlines(keepends=True), elegidas)
        return [Pieza(marcar(e.texto)[0], PISTA) for e in elegidas]

    def lugares(self) -> list[Lugar]:
        a = self._archivo
        return [Lugar(ARCHIVO, [e.texto for e in a.elegidas])] if a else []

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        a = self._archivo
        if a is None:
            return resumen
        lineas = list(a.lineas)
        hechos = 0
        for e in a.elegidas:
            marcado, codigos = marcar(e.texto)
            traducido = traducciones.get(marcado)
            final = desmarcar(traducido, codigos) if traducido is not None else None
            if final is None:
                continue
            linea = lineas[e.numero]
            cuerpo = linea.rstrip("\r\n")
            m = _LINEA.match(cuerpo)
            if m is None:
                continue
            lineas[e.numero] = f"{m.group('antes')}{escapar(final)}{m.group('despues')}{linea[len(cuerpo) :]}"
            hechos += 1
        resumen.traducidos += hechos
        resumen.pendientes += len(a.elegidas) - hechos
        datos = "".join(lineas).encode("utf-8")
        try:
            tomllib.loads(datos.decode("utf-8"))  # lo escrito tiene que seguir siendo TOML válido
        except tomllib.TOMLDecodeError:
            self.ctx.registro(f"{a.ruta.name}: la traducción no quedó como TOML válido, se deja igual")
            return Resumen(pendientes=len(a.elegidas))
        actual = a.ruta.read_bytes() if a.ruta.is_file() else None
        if hechos and actual != datos:
            self.ctx.respaldo.escribir(a.ruta, datos)
            resumen.archivos.append(a.ruta)
        return resumen

    def restaurar(self) -> list[Path]:
        return self.ctx.respaldo.restaurar(ARCHIVO)

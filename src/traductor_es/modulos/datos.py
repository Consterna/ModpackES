"""Textos de los datos de KubeJS (`kubejs/data`): títulos de logros y mensajes de las funciones.

Los logros salen en el chat cuando el jugador los consigue, y las funciones (`.mcfunction`) pueden mandar
mensajes con `tellraw`, `title` o `say`. Los archivos se traducen en el sitio, con copia de seguridad.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ..formatos import comandos
from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, aplicar, contar, parece_clave, unidades
from .scripts import AMBITO, aplicar_comando, unidades_comando

RAIZ = "kubejs/data"
#: Carpeta de logros y de funciones dentro de un espacio de nombres (el nombre cambió entre versiones).
LOGROS = frozenset({"advancements", "advancement"})
FUNCIONES = frozenset({"functions", "function"})
CAMPOS_LOGRO = ("title", "description")


def _componente(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False)


def _logro(datos: Any) -> dict[str, Any] | None:
    """El bloque `display` de un logro, o None si el archivo no es un logro con texto."""
    if not isinstance(datos, dict):
        return None
    display = cast("dict[str, Any]", datos).get("display")
    return cast("dict[str, Any]", display) if isinstance(display, dict) else None


@dataclass(slots=True)
class _Archivo:
    ruta: Path
    texto: str
    #: Logros: el JSON entero. Funciones: None (se trabaja por líneas).
    datos: Any = None
    piezas: list[str] = field(default_factory=list[str])


def _unidades_logro(display: Mapping[str, Any]) -> list[str]:
    return [t for campo in CAMPOS_LOGRO if campo in display for t in unidades(_componente(display[campo]), True)]


def _lineas(texto: str) -> list[tuple[str, comandos.Comando | None, str]]:
    """Cada línea separada en (línea sin fin, su comando de chat, fin de línea)."""
    res: list[tuple[str, comandos.Comando | None, str]] = []
    for linea in texto.split("\n"):
        fin = "\r" if linea.endswith("\r") else ""
        cuerpo = linea[: len(linea) - len(fin)]
        cmd = comandos.analizar(cuerpo)
        res.append((cuerpo, cmd if cmd is not None and unidades_comando(cmd) else None, fin))
    return res


class DatosKubeJS:
    nombre = "Logros y funciones de KubeJS"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._archivos_leidos: list[_Archivo] = []

    def _archivos(self) -> list[Path]:
        raiz = self.ctx.instancia.juego / RAIZ
        if not raiz.is_dir():
            return []
        encontrados: list[Path] = []
        for ruta in sorted(raiz.rglob("*")):
            partes = ruta.relative_to(raiz).parts  # (espacio de nombres, carpeta, …)
            if len(partes) < 3 or not ruta.is_file():
                continue
            if (partes[1] in LOGROS and ruta.suffix == ".json") or (
                partes[1] in FUNCIONES and ruta.suffix == ".mcfunction"
            ):
                encontrados.append(ruta)
        return encontrados

    def detectar(self) -> bool:
        return bool(self._archivos())

    def describir(self) -> str:
        return contar(len(self._archivos()), "archivo de datos", "archivos de datos")

    def recolectar(self) -> list[Pieza]:
        self._archivos_leidos = []
        piezas: list[Pieza] = []
        for ruta in self._archivos():
            original = self.ctx.respaldo.original(ruta)
            if original is None:
                continue
            try:
                texto = original.decode("utf-8-sig")
                archivo = _Archivo(ruta, texto)
                if ruta.suffix == ".json":
                    archivo.datos = json.loads(texto)
                    display = _logro(archivo.datos)
                    archivo.piezas = _unidades_logro(display) if display is not None else []
                    pista = "logro del juego"
                else:
                    archivo.piezas = [t for _, cmd, _ in _lineas(texto) if cmd for t in unidades_comando(cmd)]
                    pista = "mensaje de una función"
            except (ValueError, UnicodeDecodeError):
                self.ctx.registro(f"{ruta.name}: no pude leerlo con seguridad, se deja igual")
                continue
            if archivo.piezas:
                self._archivos_leidos.append(archivo)
                piezas += [Pieza(t, pista) for t in archivo.piezas if es_traducible(t) and not parece_clave(t)]
        return piezas

    def _reescribir(self, a: _Archivo, traducciones: Mapping[str, str]) -> str:
        if a.ruta.suffix == ".mcfunction":
            return "\n".join(
                (aplicar_comando(cmd, traducciones) if cmd else linea) + fin for linea, cmd, fin in _lineas(a.texto)
            )
        datos: dict[str, Any] = a.datos
        display = _logro(datos)
        assert display is not None
        for campo in CAMPOS_LOGRO:
            if campo in display:
                display[campo] = json.loads(aplicar(_componente(display[campo]), traducciones, True))
        return json.dumps(datos, indent=2, ensure_ascii=False) + "\n"

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        for a in self._archivos_leidos:
            hechas = sum(1 for t in set(a.piezas) if t in traducciones)
            resumen.traducidos += hechas
            resumen.pendientes += len(set(a.piezas)) - hechas
            nuevo = self._reescribir(a, traducciones)
            actual = a.ruta.read_text(encoding="utf-8-sig") if a.ruta.is_file() else None
            if hechas and nuevo not in (a.texto, actual):
                self.ctx.respaldo.escribir(a.ruta, nuevo.encode("utf-8"))
                resumen.archivos.append(a.ruta)
        return resumen

    def restaurar(self) -> list[Path]:
        return self.ctx.respaldo.restaurar(RAIZ + "/")

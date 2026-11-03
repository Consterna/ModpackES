"""El resource pack que genera la app: textos de mods y libros para todas las variantes de español."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .. import __version__
from ..formatos import lang_json, lang_legacy
from ..fuentes.instancia import Instancia
from ..fuentes.recursos import MARCA
from ..fuentes.version import mcmeta
from ..nucleo.dialectos import nombre_archivo_lang

NOMBRE = "Traduccion_ES"


class PackSalida:
    def __init__(self, instancia: Instancia, nombre: str = NOMBRE) -> None:
        self.instancia = instancia
        self.nombre = nombre
        self.raiz = instancia.juego / "resourcepacks" / nombre

    def _ruta(self, relativa: str) -> Path:
        partes = PurePosixPath(relativa).parts
        if not partes or ".." in partes or PurePosixPath(relativa).is_absolute():
            raise ValueError(f"Ruta fuera del pack: {relativa!r}")
        return self.raiz.joinpath(*partes)

    def preparar(self) -> None:
        self.raiz.mkdir(parents=True, exist_ok=True)
        meta = mcmeta(self.instancia.formato_recursos(), "§eTraducción al español del modpack")
        self.escribir("pack.mcmeta", (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        marca = {
            "app": "traductor-es",
            "version": __version__,
            "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.escribir(MARCA, (json.dumps(marca, indent=2) + "\n").encode("utf-8"))

    def escribir(self, relativa: str, datos: bytes) -> Path:
        ruta = self._ruta(relativa)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(ruta.name + ".tmp")
        temporal.write_bytes(datos)
        temporal.replace(ruta)
        return ruta

    def ruta_lang(self, namespace: str, idioma: str) -> str:
        nombre = nombre_archivo_lang(idioma, self.instancia.version.partes)
        extension = "lang" if self.instancia.legacy else "json"
        return f"assets/{namespace}/lang/{nombre}.{extension}"

    def escribir_lang(self, namespace: str, idioma: str, textos: dict[str, str]) -> Path:
        """Escribe (y combina con lo que ya hubiera de una ejecución anterior) un archivo de idioma."""
        relativa = self.ruta_lang(namespace, idioma)
        legacy = self.instancia.legacy
        previo: dict[str, str] = {}
        ruta = self._ruta(relativa)
        if ruta.is_file():
            try:
                previo = lang_legacy.leer(ruta.read_bytes()) if legacy else lang_json.leer(ruta.read_bytes())
            except ValueError:
                previo = {}
        combinado = dict(sorted({**previo, **textos}.items()))
        datos = lang_legacy.escribir(combinado) if legacy else lang_json.escribir(combinado)
        return self.escribir(relativa, datos)

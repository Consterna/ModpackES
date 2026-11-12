"""El resource pack que genera la app: textos de mods y libros para todas las variantes de español."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .. import NOMBRE as NOMBRE_APP
from .. import __version__
from ..formatos import lang_json, lang_legacy
from ..fuentes.instancia import Instancia
from ..fuentes.recursos import MARCA
from ..fuentes.version import mcmeta
from ..nucleo.dialectos import nombre_archivo_lang

NOMBRE = "Traduccion_ES"
#: Un segmento de ruta seguro: sin barras invertidas, dos puntos ni caracteres que Windows no admite.
_PARTE_VALIDA = re.compile(r"[^\\/:*?\"<>|\x00-\x1f]+")
#: Nombres de dispositivo de Windows (CON, NUL, COM1…): no se pueden usar como carpeta ni archivo.
_RESERVADOS = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
)


def leer_marca(raiz: Path) -> dict[str, Any]:
    """Lo que la app anotó en su pack (versión, fecha, motores); vacío si no hay marca o está dañada."""
    try:
        datos: Any = json.loads((raiz / MARCA).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cast(dict[str, Any], datos) if isinstance(datos, dict) else {}


def motores_de(marca: dict[str, Any]) -> list[str]:
    lista: object = marca.get("motores")
    if not isinstance(lista, list):
        return []
    return sorted({m for m in cast(list[object], lista) if isinstance(m, str)})


def _parte_segura(parte: str) -> bool:
    if not _PARTE_VALIDA.fullmatch(parte) or parte in (".", "..") or parte != parte.rstrip(". "):
        return False  # Windows quita los puntos y espacios del final: «a.» y «a» serían la misma carpeta
    return parte.split(".", maxsplit=1)[0].upper() not in _RESERVADOS


class PackSalida:
    def __init__(self, instancia: Instancia, nombre: str = NOMBRE) -> None:
        self.instancia = instancia
        self.nombre = nombre
        self.raiz = instancia.juego / "resourcepacks" / nombre
        self._escritos: set[Path] = set()

    def _ruta(self, relativa: str) -> Path:
        """Ruta dentro del pack. Rechaza todo lo que pueda salir de él (también trucos de Windows)."""
        partes = relativa.split("/")
        if not relativa or any(not _parte_segura(p) for p in partes):
            raise ValueError(f"Ruta fuera del pack: {relativa!r}")
        ruta = self.raiz.joinpath(*partes)
        if not ruta.resolve().is_relative_to(self.raiz.resolve()):
            raise ValueError(f"Ruta fuera del pack: {relativa!r}")
        return ruta

    def preparar(self) -> None:
        self.raiz.mkdir(parents=True, exist_ok=True)
        meta = mcmeta(self.instancia.formato_recursos(), "§eTraducción al español del modpack")
        self.escribir("pack.mcmeta", (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        self._escribir_marca(motores_de(leer_marca(self.raiz)))

    def _escribir_marca(self, motores: list[str]) -> None:
        marca: dict[str, Any] = {
            "app": NOMBRE_APP,
            "version": __version__,
            "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        if motores:
            marca["motores"] = motores  # para los créditos del pack publicado
        self.escribir(MARCA, (json.dumps(marca, indent=2) + "\n").encode("utf-8"))

    def anotar_motores(self, motores: Iterable[str]) -> None:
        """Suma a la marca los motores (y modelos) que tradujeron algo de este pack."""
        nuevos = {m for m in motores if m}
        if not nuevos or not (self.raiz / "pack.mcmeta").is_file():
            return
        previos = motores_de(leer_marca(self.raiz))
        if not nuevos <= set(previos):
            self._escribir_marca(sorted({*previos, *nuevos}))

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
        """Escribe un archivo de idioma completo (reemplaza el de una ejecución anterior)."""
        relativa = self.ruta_lang(namespace, idioma)
        ordenado = dict(sorted(textos.items()))
        datos = lang_legacy.escribir(ordenado) if self.instancia.legacy else lang_json.escribir(ordenado)
        ruta = self.escribir(relativa, datos)
        self._escritos.add(ruta)
        return ruta

    def vaciar_idiomas_viejos(self) -> list[Path]:
        """Deja vacíos los archivos de idioma de ejecuciones anteriores que esta no volvió a escribir.

        Así, si un mod trae ahora su propia traducción, la de la app ya no la tapa. No se borra nada:
        un archivo de idioma vacío no cambia nada en el juego.
        """
        vaciados: list[Path] = []
        vacio = lang_legacy.escribir({}) if self.instancia.legacy else lang_json.escribir({})
        assets = self.raiz / "assets"
        anteriores: list[Path] = sorted(assets.glob("*/lang/*.*")) if assets.is_dir() else []
        for ruta in anteriores:
            if ruta not in self._escritos and ruta.suffix in (".json", ".lang") and ruta.read_bytes() != vacio:
                ruta.write_bytes(vacio)
                vaciados.append(ruta)
        return vaciados

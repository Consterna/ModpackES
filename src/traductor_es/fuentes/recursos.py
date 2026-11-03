"""Fuentes de recursos de una instancia y la tabla de idiomas que el juego realmente ve.

Minecraft junta los textos de todas las fuentes: primero los mods, luego los packs siempre activos
(KubeJS, Global Packs, OpenLoader, Paxi) y al final los resource packs activados en options.txt,
donde el último de la lista gana. Lo mismo hace esta tabla, para saber qué texto ve el jugador.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..formatos import lang_json, lang_legacy
from ..nucleo.mascara import es_traducible
from .contenedores import Carpeta, Contenedor, Zip

#: Archivo que marca los packs generados por esta app (nunca se leen como fuente).
MARCA = "traductor_es.json"

PRIORIDAD_VANILLA, PRIORIDAD_MOD, PRIORIDAD_KUBEJS, PRIORIDAD_GLOBAL, PRIORIDAD_PACKS = -1, 0, 1, 2, 10
_LANG = re.compile(r"assets/([^/]+)/lang/([a-zA-Z]{2,3}_[a-zA-Z]{2,4})\.(json|lang)")


@dataclass(frozen=True, slots=True)
class Fuente:
    contenedor: Contenedor
    prioridad: int
    tipo: str  #: «mod», «kubejs», «global», «pack», «resourceloader»


def _abrir_pack(ruta: Path, nombre: str | None = None) -> Contenedor | None:
    if ruta.is_dir():
        if (ruta / MARCA).exists() or not (ruta / "assets").is_dir():
            return None
        return Carpeta(ruta, nombre or ruta.name)
    if ruta.suffix.lower() == ".zip" and ruta.is_file():
        try:
            z = Zip.abrir(ruta)
        except (zipfile.BadZipFile, OSError):
            return None
        if MARCA in z.nombres():
            z.cerrar()
            return None
        return z
    return None


def _packs_en(carpeta: Path) -> list[Path]:
    return sorted(carpeta.iterdir()) if carpeta.is_dir() else []


def fuentes_de_recursos(juego: Path, mods: Sequence[Contenedor], packs_activos: Sequence[str]) -> list[Fuente]:
    fuentes = [Fuente(m, PRIORIDAD_MOD, "mod") for m in mods]
    kubejs = juego / "kubejs" / "assets"
    if kubejs.is_dir():
        fuentes.append(Fuente(Carpeta(kubejs, "kubejs/assets", prefijo="assets/"), PRIORIDAD_KUBEJS, "kubejs"))
    resourceloader = juego / "resources"  # mod ResourceLoader (1.7-1.12): resources/<mod>/lang/...
    if resourceloader.is_dir():
        fuentes.append(
            Fuente(Carpeta(resourceloader, "resources", prefijo="assets/"), PRIORIDAD_GLOBAL, "resourceloader")
        )
    siempre = [
        juego / "global_packs" / "required_resources",
        juego / "openloader" / "resources",
        juego / "config" / "openloader" / "resources",
        juego / "config" / "paxi" / "resourcepacks",
    ]
    for carpeta in siempre:
        for ruta in _packs_en(carpeta):
            if c := _abrir_pack(ruta):
                fuentes.append(Fuente(c, PRIORIDAD_GLOBAL, "global"))
    for i, nombre in enumerate(packs_activos):
        if c := _abrir_pack(juego / "resourcepacks" / nombre, nombre):
            fuentes.append(Fuente(c, PRIORIDAD_PACKS + i, "pack"))
    return fuentes


@dataclass(frozen=True, slots=True)
class Texto:
    valor: str
    prioridad: int
    origen: str


@dataclass(frozen=True, slots=True)
class Pendiente:
    """Un texto que el jugador vería en inglés en alguna variante de español."""

    namespace: str
    clave: str
    ingles: str
    faltan: tuple[str, ...]  #: variantes de español donde falta
    existente: str | None  #: traducción válida que ya hay en otra variante (se copia sin gastar)


@dataclass(slots=True)
class TablaIdiomas:
    #: {namespace: {idioma: {clave: Texto}}}: lo que gana en cada idioma
    datos: dict[str, dict[str, dict[str, Texto]]] = field(default_factory=dict[str, dict[str, dict[str, Texto]]])
    #: {namespace: {clave: [(prioridad, valor)]}}: todas las versiones del inglés, para saber si cambió
    historial_en: dict[str, dict[str, list[tuple[int, str]]]] = field(
        default_factory=dict[str, dict[str, list[tuple[int, str]]]]
    )
    #: Si no se encontró el español oficial del juego, sus propias claves no se tocan nunca
    #: (el juego sí lo tiene; traducirlas taparía la traducción de Mojang).
    vanilla_sin_espanol: bool = False

    def agregar(self, namespace: str, idioma: str, textos: dict[str, str], prioridad: int, origen: str) -> None:
        destino = self.datos.setdefault(namespace, {}).setdefault(idioma, {})
        historial = self.historial_en.setdefault(namespace, {}) if idioma == "en_us" else None
        for clave, valor in textos.items():
            previo = destino.get(clave)
            if previo is None or prioridad >= previo.prioridad:
                destino[clave] = Texto(valor, prioridad, origen)
            if historial is not None:
                historial.setdefault(clave, []).append((prioridad, valor))

    def _ingles_hasta(self, namespace: str, clave: str, prioridad: int) -> str | None:
        """El inglés que regía cuando se escribió una traducción de esa prioridad."""
        previos = [(p, v) for p, v in self.historial_en.get(namespace, {}).get(clave, []) if p <= prioridad]
        return max(previos, key=lambda par: par[0])[1] if previos else None

    def _es_de_vanilla(self, namespace: str, clave: str, en: Texto) -> bool:
        """El texto inglés que ve el jugador es el del propio juego (aunque un mod lo repita igual)."""
        return any(
            p == PRIORIDAD_VANILLA and v.strip() == en.valor.strip()
            for p, v in self.historial_en.get(namespace, {}).get(clave, [])
        )

    def textos(self, namespace: str, idioma: str) -> dict[str, str]:
        return {k: t.valor for k, t in self.datos.get(namespace, {}).get(idioma, {}).items()}

    def es_valida(self, namespace: str, idioma: str, clave: str) -> bool:
        """Hay una traducción que el juego usaría y que no es una copia del inglés."""
        por_idioma = self.datos.get(namespace, {})
        en = por_idioma.get("en_us", {}).get(clave)
        tr = por_idioma.get(idioma, {}).get(clave)
        if tr is None or en is None:
            return tr is not None
        if tr.prioridad < en.prioridad:
            # Un mod o pack de más prioridad volvió a declarar el inglés: si lo cambió, la traducción vieja
            # ya no corresponde; si es el mismo texto, sigue valiendo.
            base = self._ingles_hasta(namespace, clave, tr.prioridad)
            if base is not None and base.strip() != en.valor.strip():
                return False
        if tr.prioridad == PRIORIDAD_VANILLA:
            return True  # la traducción oficial manda aunque sea igual al inglés («Minecraft», «Nether»)
        # Una «traducción» idéntica al inglés suele ser una copia sin traducir (pasa en mods y packs rotos)
        return tr.valor.strip() != en.valor.strip() or not es_traducible(en.valor)

    def pendientes(self, variantes: Sequence[str], preferidas: Sequence[str] = ("es_mx", "es_es")) -> list[Pendiente]:
        """Textos que faltan. Para copiar una traducción de otra variante se prefieren las de `preferidas`."""
        orden = [*(v for v in preferidas if v in variantes), *(v for v in variantes if v not in preferidas)]
        salida: list[Pendiente] = []
        for ns in sorted(self.datos):
            ingles = self.datos[ns].get("en_us", {})
            for clave, en in ingles.items():
                if not es_traducible(en.valor) or (self.vanilla_sin_espanol and self._es_de_vanilla(ns, clave, en)):
                    continue
                faltan = tuple(v for v in variantes if not self.es_valida(ns, v, clave))
                if not faltan:
                    continue
                existente = next(
                    (self.datos[ns][v][clave].valor for v in orden if v not in faltan),
                    None,
                )
                salida.append(Pendiente(ns, clave, en.valor, faltan, existente))
        return salida


def leer_idiomas(fuentes: Iterable[Fuente], idiomas: Iterable[str], legacy: bool) -> TablaIdiomas:
    """Lee los lang de todas las fuentes. Antes de 1.13 el juego solo usa .lang; desde 1.13, solo .json."""
    buscados = {i.lower() for i in idiomas}
    extension = "lang" if legacy else "json"
    tabla = TablaIdiomas()
    for f in sorted(fuentes, key=lambda f: f.prioridad):
        for nombre in f.contenedor.nombres():
            m = _LANG.fullmatch(nombre)
            if not m or m.group(3) != extension or m.group(2).lower() not in buscados:
                continue
            try:
                datos = f.contenedor.leer(nombre)
                textos = lang_legacy.leer(datos) if legacy else lang_json.leer(datos)
            except (ValueError, KeyError, OSError):
                continue
            tabla.agregar(m.group(1), m.group(2).lower(), textos, f.prioridad, f.contenedor.nombre)
    return tabla

"""Qué texto en inglés queda en la instancia aunque se traduzca todo, y por qué.

La traducción no puede cubrirlo todo: un resource pack no llega al texto escrito en el código de un mod, y hay
cadenas de scripts cuyo uso no se entiende. Este informe lo dice con datos en lugar de dejar al jugador con la duda.
Solo lee; no escribe nada en la instancia.
"""

from __future__ import annotations

import re
import struct
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..fuentes.instancia import Instancia
from ..nucleo.mascara import es_traducible
from .base import Contexto, parece_clave
from .datos import clasificar, recorrer
from .scripts import ScriptsKubeJS

MAX_EJEMPLOS = 3
#: Nombres que delatan una clase que construye texto: `Component.literal` (Mojang), `m_237113_` (SRG 1.19+),
#: `method_43470` (Fabric) y los `TextComponent`, `StringTextComponent` y `TextComponentString` anteriores.
_MARCAS_TEXTO = ("literal", "m_237113_", "method_43470")
_CLASES_TEXTO = ("TextComponent", "StringTextComponent", "TextComponentString")
#: Una frase en inglés: puede empezar con códigos de color (§c) y llevar %s, números y puntuación.
_FRASE = re.compile(r"(?:§[0-9a-fk-or])*[A-Z][A-Za-z']+(?: [§A-Za-z0-9,.'!?:%\-]+){2,}[.!?:]?")
_ESPANOL = re.compile(r"\b(de|la|el|los|las|con|sin|para|por|una|un|del)\b")
#: Frases de registros y errores internos: casi nunca llegan al jugador.
_INTERNO = re.compile(
    r"^(Failed|Could not|Couldn't|Unable|Unexpected|Invalid|Missing|Exception|Error|Cannot|No )", re.I
)
#: Tamaño de cada tipo de constante de un .class (tras la etiqueta), según la especificación de la JVM
_TAMANO_CONSTANTE = {
    3: 4,
    4: 4,
    5: 8,
    6: 8,
    7: 2,
    8: 2,
    9: 4,
    10: 4,
    11: 4,
    12: 4,
    15: 3,
    16: 2,
    17: 4,
    18: 4,
    19: 2,
    20: 2,
}


@dataclass(frozen=True, slots=True)
class Hallazgo:
    """Una cosa que queda en inglés: dónde, cuántos textos y unos ejemplos."""

    categoria: str  #: «script», «formato» o «java»
    donde: str
    cantidad: int
    motivo: str
    ejemplos: tuple[str, ...] = ()

    def __str__(self) -> str:
        ej = f" Por ejemplo: {' | '.join(f'«{e}»' for e in self.ejemplos)}." if self.ejemplos else ""
        return f"{self.donde}: {self.cantidad} {'texto' if self.cantidad == 1 else 'textos'}. {self.motivo}.{ej}"


def hallazgos_de_scripts(juego: Path, sin_elegir: list[tuple[Path, list[str]]]) -> list[Hallazgo]:
    """Frases de los scripts que parecen texto y que la traducción no tocó (pueden ser mensajes)."""
    return [
        Hallazgo(
            "script", ruta.relative_to(juego).as_posix(), len(textos),
            "Parece una frase, pero no se usa como texto visible (puede ser lógica o un mensaje armado de otra forma)",
            tuple(t[:60] for t in textos[:MAX_EJEMPLOS]),
        )
        for ruta, textos in sin_elegir
    ]  # fmt: skip


def constantes_utf8(datos: bytes) -> list[str]:
    """Las cadenas de la tabla de constantes de un .class (JVMS §4.4). Vacío si el archivo no se entiende."""
    if len(datos) < 10 or datos[:4] != b"\xca\xfe\xba\xbe":
        return []
    (cantidad,) = struct.unpack_from(">H", datos, 8)
    pos, i = 10, 1
    textos: list[str] = []
    try:
        while i < cantidad:
            etiqueta = datos[pos]
            pos += 1
            if etiqueta == 1:
                (largo,) = struct.unpack_from(">H", datos, pos)
                textos.append(datos[pos + 2 : pos + 2 + largo].decode("utf-8", "ignore"))
                pos += 2 + largo
            else:
                pos += _TAMANO_CONSTANTE[etiqueta]
                i += 1 if etiqueta in (5, 6) else 0  # long y double ocupan dos casillas
            i += 1
    except (IndexError, KeyError, struct.error):
        return []
    return textos if pos <= len(datos) else []  # si la tabla se pasa del final, el archivo está truncado


def _frases_de_clase(datos: bytes) -> list[str]:
    constantes = constantes_utf8(datos)
    if not any(c in _MARCAS_TEXTO or any(n in c for n in _CLASES_TEXTO) for c in constantes):
        return []  # la clase no construye texto para el jugador
    return [
        c for c in constantes
        if len(c) > 14 and _FRASE.fullmatch(c) and not _INTERNO.match(c) and not _ESPANOL.search(c.lower())
    ]  # fmt: skip


def frases_por_mod(
    instancia: Instancia, progreso: Callable[[int, int], None] = lambda _a, _b: None
) -> list[tuple[Path, list[str]]]:
    """Por cada mod, las frases en inglés escritas en su código y mostradas como texto (sin repetir)."""
    res: list[tuple[Path, list[str]]] = []
    jars = instancia.jars()
    for i, jar in enumerate(jars):
        progreso(i, len(jars))
        frases: list[str] = []
        try:
            with zipfile.ZipFile(jar) as z:
                for info in z.infolist():
                    if (
                        info.filename.endswith(".class")
                        and not info.filename.startswith("META-INF")
                        and info.file_size < 3_000_000
                    ):
                        frases += _frases_de_clase(z.read(info))
        except (zipfile.BadZipFile, OSError):
            continue
        unicas = list(dict.fromkeys(f for f in frases if es_traducible(f) and not parece_clave(f)))
        if unicas:
            res.append((jar, unicas))
    return res


def textos_en_java(instancia: Instancia, progreso: Callable[[int, int], None] = lambda _a, _b: None) -> list[Hallazgo]:
    """Frases en inglés escritas en el código de los mods. Un resource pack no puede traducirlas."""
    res = [
        Hallazgo(
            "java", jar.name, len(unicas),
            "Escrito en el código del mod: un resource pack no lo traduce",
            tuple(f[:60] for f in unicas[:MAX_EJEMPLOS]),
        )
        for jar, unicas in frases_por_mod(instancia, progreso)
    ]  # fmt: skip
    return sorted(res, key=lambda h: -h.cantidad)


#: Carpetas de un datapack o resource pack que no llevan texto para el jugador (o que ya se traducen por otro lado).
_SIN_TEXTO = frozenset({
    "recipes", "recipe", "tags", "loot_tables", "loot_table", "predicates", "worldgen", "dimension", "dimension_type",
    "structures", "structure", "lang", "textures", "models", "blockstates", "sounds", "particles", "shaders", "font",
    "atlases", "item_modifiers", "chat_type", "damage_type", "enchantment", "trim_pattern", "trim_material",
    "banner_pattern", "jukebox_song", "painting_variant", "patchouli_books", "optifine", "equipment", "items",
})  # fmt: skip
#: Un valor de texto con aspecto de frase en inglés dentro de un JSON.
_TEXTO_JSON = re.compile(r'"(?:text|title|description|message|tip|name|lore)"\s*:\s*"([A-Z][^"\\]{11,})"')
_TAMANO_MAXIMO = 300_000


def formatos_desconocidos(juego: Path) -> list[Hallazgo]:
    """Carpetas de datos o recursos con frases en inglés cuyo formato la app no conoce (no se tocan)."""
    por_carpeta: dict[str, list[str]] = {}
    for ruta in recorrer(juego):
        partes = ruta.relative_to(juego).parts
        if ruta.suffix != ".json" or clasificar(Path(*partes)) is not None:
            continue
        ancla = next(
            (i for i, parte in enumerate(partes) if parte in ("data", "assets") and len(partes) - i >= 4), None
        )
        if ancla is None or partes[ancla + 2] in _SIN_TEXTO:
            continue
        try:
            if ruta.stat().st_size > _TAMANO_MAXIMO:
                continue
            frases = [
                f
                for f in _TEXTO_JSON.findall(ruta.read_text(encoding="utf-8-sig", errors="ignore"))
                if es_traducible(f)
            ]
        except OSError:
            continue
        if frases:
            por_carpeta.setdefault("/".join(partes[: ancla + 3]), []).extend(frases)
    return [
        Hallazgo(
            "formato", carpeta, len(frases), "Formato que la app no conoce: no se traduce (no se toca ningún archivo)",
            tuple(f[:60] for f in frases[:MAX_EJEMPLOS]),
        )
        for carpeta, frases in sorted(por_carpeta.items(), key=lambda kv: -len(kv[1]))
    ]  # fmt: skip


def revisar_cobertura(
    ctx: Contexto, java: bool = False, progreso: Callable[[int, int], None] = lambda _a, _b: None
) -> list[Hallazgo]:
    """Lo que queda en inglés. El análisis del código Java tarda (lee todos los mods): solo si se pide."""
    hallazgos = hallazgos_de_scripts(ctx.instancia.juego, ScriptsKubeJS(ctx).candidatas())
    hallazgos += formatos_desconocidos(ctx.instancia.juego)
    if java:
        hallazgos += textos_en_java(ctx.instancia, progreso)
    return hallazgos


__all__ = ["Hallazgo", "frases_por_mod", "revisar_cobertura"]

"""Oráculo de la auditoría: inventario de todo texto en inglés que un modpack podría mostrar, sin el código de la app.

No importa nada de `traductor_es`: si compartiera sus filtros, heredaría sus cegueras. Recorre la instancia entera y
los jars, zips y carpetas que trae (mods, resource packs, datapacks, shaderpacks…), lee cada formato de texto que
conoce (JSON, JSON5, SNBT, NBT, TOML, CFG, properties, JS, ZS, mcfunction, lang, MD, TXT) y anota cada cadena que
parece una frase en inglés visible, con su ubicación. Es deliberadamente generoso: lo que sobre (falsos positivos) se
filtra al comparar con la app y al revisar los grupos a mano. Lo que se descarta de entrada, y por qué, está en
`SALTAR`, `SIN_TEXTO` y `CAMPOS_NO`.

Uso:
    uv run python scripts/auditoria/inventario.py C:/dev/corpus-modpacks/ftb-86 --salida build/auditoria/ftb-86
Deja `inventario.jsonl` (una fila por texto) y `resumen.json` (cuántos por patrón de ruta).
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import struct
import sys
import zipfile
import zlib
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, cast

# ----------------------------------------------------------------------------- qué es una frase en inglés


def _palabras(texto: str) -> frozenset[str]:
    return frozenset(texto.split())


_INGLES = _palabras(
    "the a an and or of to in on at for with by from is are was were be been this that these those it its your you "
    "can will not no all any some more most each every into out up down over under use used using make made get "
    "has have had do does did when where which who what how why if then than there here once also only just can't "
    "don't won't it's you're you'll need needs required requires allows allow lets increases decreases gives "
    "click right left press hold place break craft crafted crafting found find kill defeat collect obtain bring "
    "enemy enemies player players item items block blocks level levels power energy damage speed time chance "
    "per while after before during until again new old first last next other another same very much many "
    "may might should would could must one two three four five"
)
_ESPANOL = _palabras(
    "el la los las un una unos unas y o de del al en con por para que es son fue ser este esta estos estas su sus "
    "tu tus se no más muy cuando donde como pero también solo puede pueden haz usa usar objeto objetos bloque "
    "bloques nivel daño velocidad tiempo"
)
#: Campos que casi siempre son texto visible: aquí cuenta también una sola palabra con mayúscula.
CAMPOS_VISIBLES = _palabras(
    "name title text description desc subtitle tooltip tooltips lore message messages msg tip tips label "
    "display displayname display_name hover header subtext landing_text link_text page pages body content "
    "summary motd welcome greeting quest chapter task reward lock_message fallback contents value line lines "
    "caption hint info information entry customname text1 text2 text3 text4"
)
#: Campos que nunca son texto visible (ids, tipos, rutas, comentarios del autor…).
CAMPOS_NO = _palabras(
    "id type key modid mod namespace resource registry item items tag tags icon texture textures model sound "
    "sounds font color colour background image path file url link uuid parent criteria trigger condition "
    "conditions predicate function functions loot_table translate translation score selector nbt keybind "
    "storage entity block fluid biome dimension structure recipe group category_id dependencies target source "
    "op ops mode comment _comment __comment comments author authors credits license version metadata "
    "mixins refmap package entrypoints"
)
#: Una clave de configuración que lleva un mensaje para el jugador.
_CAMPO_DE_MENSAJE = re.compile(
    r"message|text|title|name|desc|tooltip|motd|welcome|tip|lore|label|greet|announce|broadcast|subtitle|header|footer",
    re.I,
)
_CODIGOS = re.compile(
    r"§.|&[0-9a-fk-or]|\$\([^)]*\)|%(?:\d+\$)?[sdf]|\{[^{}\s]{0,40}\}|<[^<>]{1,60}>|\\n|\\u[0-9a-fA-F]{4}"
)
_PALABRA = re.compile(r"[A-Za-zÀ-ÿ']+")
_ID = re.compile(r"^#?[a-z0-9_.\-]+:[a-z0-9_./\-]+$")
_CLAVE = re.compile(r"^[A-Za-z0-9_\-]+(\.[A-Za-z0-9_\-]+)+$")
_RUTA = re.compile(r"^[\w.\-]*(/[\w.\-]+)+/?$")
_URL = re.compile(r"https?://|www\.", re.I)
_SNAKE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$")
_HEX = re.compile(r"^#?(0x)?[0-9a-fA-F]{6,}$")
_CAMEL = re.compile(r"^[a-z]+([A-Z][a-z0-9]*)+$")


def sin_codigos(texto: str) -> str:
    return _CODIGOS.sub(" ", texto)


def _campo_simple(campo: str) -> str:
    """La última parte de la ruta de un valor: `pools[0].functions[1].name` → `name`."""
    return re.sub(r"(\[\d*\]|<json>)+$", "", campo.lower()).rsplit(".", 1)[-1].strip(":0123456789")


def es_frase_inglesa(texto: str, campo: str = "") -> bool:
    """¿Parece una frase (o un nombre, si el campo es de texto visible) en inglés que el jugador lee?"""
    t = texto.strip()
    if len(t) < 3 or len(t) > 20000:
        return False
    if _URL.search(t) and " " not in t:
        return False
    if any(r.match(t) for r in (_ID, _CLAVE, _RUTA, _SNAKE, _HEX, _CAMEL)):
        return False
    limpio = sin_codigos(t)
    palabras = _PALABRA.findall(limpio)
    letras = sum(len(p) for p in palabras)
    if letras < 3 or letras < 0.4 * len(limpio.replace(" ", "")):
        return False
    bajas = [p.lower() for p in palabras]
    ingles = sum(p in _INGLES for p in bajas)
    espanol = sum(p in _ESPANOL for p in bajas)
    if espanol > ingles or re.search(r"[áéíóúñ¿¡]", limpio):
        return False
    simple = _campo_simple(campo)
    if simple in CAMPOS_NO:
        return False
    separadas = [w for w in limpio.split() if _PALABRA.search(w)]  # palabras separadas por espacios
    if len(separadas) >= 3:
        return ingles >= 1 or (simple in CAMPOS_VISIBLES and separadas[0][:1].isupper())
    if len(separadas) == 2:
        return ingles >= 1 or simple in CAMPOS_VISIBLES or all(p[:1].isupper() for p in separadas)
    # una sola palabra: solo en campos de texto visible y con mayúscula («Copper», no «true» ni «FORGE»)
    p = palabras[0]
    return simple in CAMPOS_VISIBLES and p[:1].isupper() and not p.isupper() and len(p) >= 3


# ----------------------------------------------------------------------------------------------- registros


@dataclass(slots=True)
class Texto:
    contenedor: str  #: el jar, zip o carpeta que lo trae, relativo al juego ("" = suelto en la instancia)
    ruta: str  #: dentro del contenedor, con «/»
    formato: str
    campo: str  #: ruta del valor dentro del archivo (clave JSON, etiqueta NBT, nombre de función…)
    texto: str
    patron: str = ""  #: la ruta con el espacio y el nombre de archivo cambiados por «*», para agrupar
    clase: str = "texto"  #: «lang» (archivo de idioma en inglés) o «texto»


#: Archivos de un jar que describen el mod (su nombre y descripción salen en la lista de mods).
METADATOS = frozenset({"fabric.mod.json", "quilt.mod.json", "mcmod.info", "META-INF/mods.toml",
                       "META-INF/neoforge.mods.toml"})  # fmt: skip


def patron_de(contenedor: str, ruta: str) -> str:
    """`data/create/advancements/x.json` → `jar:data/*/advancements/*.json`."""
    if ruta in METADATOS:
        return f"jar:{ruta}"
    partes = list(PurePosixPath(ruta).parts)
    if len(partes) >= 2 and partes[0] in ("data", "assets"):
        partes[1] = "*"
    if partes:
        partes[-1] = "*" + PurePosixPath(partes[-1]).suffix
    if len(partes) > 5:  # carpetas profundas con nombres propios (capítulos, libros): se cortan
        partes = [*partes[:4], "…", partes[-1]]
    if not contenedor:
        tipo = "instancia"
    elif contenedor.startswith("mods/"):
        tipo = "jar"
    else:
        tipo = contenedor.split("/", 1)[0]
    return f"{tipo}:{'/'.join(partes)}"


# ------------------------------------------------------------------------------------------------- lectores


def _json_flexible(texto: str) -> Any:
    """JSON, o JSON5 sencillo (comentarios, comas finales, claves sin comillas)."""
    try:
        return json.loads(texto)
    except ValueError:
        pass
    sin = re.sub(r"//[^\n]*|/\*.*?\*/", "", texto, flags=re.S)
    sin = re.sub(r",(\s*[}\]])", r"\1", sin)
    sin = re.sub(r"([{,]\s*)([A-Za-z_][\w\-]*)\s*:", r'\1"\2":', sin)
    return json.loads(sin)


def _cadenas_json(valor: Any, camino: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(valor, str):
        s = valor.strip()
        if s[:1] in "{[" and s[-1:] in "}]":  # un componente de texto guardado como cadena
            try:
                yield from _cadenas_json(json.loads(s), camino + "<json>")
                return
            except ValueError:
                pass
        yield camino, valor
    elif isinstance(valor, dict):
        for k, v in cast(dict[str, Any], valor).items():
            yield from _cadenas_json(v, f"{camino}.{k}" if camino else str(k))
    elif isinstance(valor, list):
        for i, v in enumerate(cast(list[Any], valor)):
            yield from _cadenas_json(v, f"{camino}[{i}]")


_SNBT_PAR = re.compile(r'([\w.\-+]+|"[^"]*")\s*:\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\[)')
_SNBT_CADENA = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _desescapar(s: str) -> str:
    return s.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")


def _cadenas_snbt(texto: str) -> Iterator[tuple[str, str]]:
    """Pares clave: "valor" y las cadenas de las listas (con la última clave vista)."""
    clave = ""
    pos = 0
    for m in _SNBT_PAR.finditer(texto):
        for s in _SNBT_CADENA.finditer(texto, pos, m.start()):  # elementos de una lista entre dos pares
            yield f"{clave}[]", _desescapar(s.group(1))
        clave = m.group(1).strip('"')
        if m.group(2) != "[":
            yield clave, _desescapar(m.group(2)[1:-1])
        pos = m.end()
    for s in _SNBT_CADENA.finditer(texto, pos):
        yield f"{clave}[]", _desescapar(s.group(1))


#: Etiquetas NBT con texto visible: carteles (viejos y nuevos), nombres, descripciones y libros.
ETIQUETAS_NBT = frozenset({"text1", "text2", "text3", "text4", "messages", "customname", "name", "lore", "pages",
                           "title", "text", "filtered_title"})  # fmt: skip


def _descomprimir_nbt(datos: bytes) -> bytes | None:
    for intento in (gzip.decompress, zlib.decompress):
        try:
            crudo = intento(datos)
        except (OSError, zlib.error, EOFError):
            continue
        if crudo[:1] == b"\x0a":
            return crudo
    return datos if datos[:1] == b"\x0a" else None


class _LectorNBT:
    """Lector mínimo de NBT binario: solo junta las cadenas con el nombre de su etiqueta."""

    _FIJOS: ClassVar[dict[int, int]] = {1: 1, 2: 2, 3: 4, 4: 8, 5: 4, 6: 8}

    def __init__(self, crudo: bytes) -> None:
        self.f = io.BytesIO(crudo)
        self.cadenas: list[tuple[str, str]] = []

    def _leer(self, n: int) -> bytes:
        b = self.f.read(n)
        if len(b) != n:
            raise EOFError
        return b

    def _cadena(self) -> str:
        (largo,) = struct.unpack(">H", self._leer(2))
        return self._leer(largo).decode("utf-8", "replace")

    def _entero(self) -> int:
        return int(struct.unpack(">i", self._leer(4))[0])

    def carga(self, tipo: int, nombre: str, profundidad: int) -> None:
        if profundidad > 64 or tipo not in range(1, 13):
            raise EOFError
        if tipo in self._FIJOS:
            self._leer(self._FIJOS[tipo])
        elif tipo in (7, 11, 12):  # arreglos de bytes, enteros y largos
            self._leer({7: 1, 11: 4, 12: 8}[tipo] * self._entero())
        elif tipo == 8:
            self.cadenas.append((nombre, self._cadena()))
        elif tipo == 9:
            sub = self._leer(1)[0]
            for _ in range(self._entero()):
                self.carga(sub, f"{nombre}[]", profundidad + 1)
        else:  # 10: compuesto
            while (t := self._leer(1)[0]) != 0:
                self.carga(t, self._cadena(), profundidad + 1)

    def leer(self) -> list[tuple[str, str]]:
        try:
            tipo = self._leer(1)[0]
            self._cadena()
            self.carga(tipo, "", 0)
        except (EOFError, struct.error, IndexError, KeyError):
            pass
        return self.cadenas


def _cadenas_nbt(datos: bytes) -> Iterator[tuple[str, str]]:
    """Las cadenas de texto visible de un NBT binario (comprimido o no)."""
    crudo = _descomprimir_nbt(datos)
    if crudo is None:
        return
    for nombre, valor in _LectorNBT(crudo).leer():
        if nombre.lower().rstrip("[]") in ETIQUETAS_NBT:
            yield nombre, valor


_CLAVE_VALOR = re.compile(r'^\s*(?:[A-Z]:)?"?([\w.\- ]+?)"?\s*[=:]\s*(.+?)\s*$')


def _cadenas_config(texto: str) -> Iterator[tuple[str, str]]:
    """TOML, CFG de Forge (`S:nombre=valor`), properties e INI: clave = valor (sin comillas)."""
    for linea in texto.splitlines():
        if linea.lstrip().startswith(("#", ";", "//", "[")):
            continue
        if m := _CLAVE_VALOR.match(linea):
            valor = m.group(2)
            if valor.startswith("["):
                for s in re.findall(r'"((?:[^"\\]|\\.)*)"', valor):
                    yield m.group(1) + "[]", s
                continue
            yield m.group(1), valor.strip().strip('"').strip("'")


_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`')


def _cadenas_script(texto: str) -> Iterator[tuple[str, str]]:
    """Literales de JS / ZenScript, con la llamada a la que van como «campo» («tooltip», «tell»…)."""
    limpio = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group()), texto, flags=re.S)
    limpio = re.sub(r"(?m)^\s*//[^\n]*", "", limpio)
    for m in _LITERAL.finditer(limpio):
        valor = next(g for g in m.groups() if g is not None)
        antes = limpio[max(0, m.start() - 40) : m.start()]
        llamada = re.findall(r"([A-Za-z_$][\w$]*)\s*\(\s*$|([A-Za-z_$][\w$]*)\s*[:=]\s*$", antes)
        campo = next((a or b for a, b in reversed(llamada)), "") if llamada else ""
        yield campo, _desescapar(valor)


_COMANDO = re.compile(r"^\s*\$?(tellraw|title|say|msg|tell|w|me|bossbar|scoreboard|team|give|summon|data)\b(.*)$")


def _cadenas_funcion(texto: str) -> Iterator[tuple[str, str]]:
    for linea in texto.splitlines():
        if not (m := _COMANDO.match(linea)):
            continue
        orden, resto = m.group(1), m.group(2)
        if orden in ("say", "me"):
            yield orden, resto.strip()
        elif orden in ("msg", "tell", "w"):
            yield orden, resto.strip().split(" ", 1)[-1]
        else:
            for s in re.findall(r'"((?:[^"\\]|\\.)*)"', resto):  # JSON o SNBT dentro del comando
                yield orden, _desescapar(s)


def _parrafos(texto: str) -> Iterator[tuple[str, str]]:
    """Markdown y texto plano: cada párrafo fuera de los bloques de código."""
    en_codigo = False
    actual: list[str] = []
    for linea in [*texto.splitlines(), ""]:
        if linea.strip().startswith("```"):
            en_codigo = not en_codigo
            continue
        if en_codigo:
            continue
        if linea.strip():
            actual.append(linea.strip())
        elif actual:
            yield "párrafo", " ".join(actual)
            actual = []


# ---------------------------------------------------------------------------------------------- recorrido

#: Carpetas de la instancia sin texto del modpack (registros, cachés, mundos del jugador, salida de la app…).
SALTAR = _palabras(
    "logs crash-reports screenshots libraries versions assets natives .fabric .mixin.out .cache cache backups "
    "traductor_es modpackes-sonda journeymap xaero schematics local downloads .git __pycache__ exported "
    "replay_recordings moddata-cache traduccion_es"
)
#: Subcarpetas de `assets/<ns>/` y `data/<ns>/` que nunca llevan texto visible.
SIN_TEXTO = _palabras(
    "models blockstates textures animations geo particles shaders font atlases patterns sounds worldgen tags "
    "recipes recipe dimension dimension_type damage_type chat_type trim_material_disabled lua"
)
#: Carpetas de mundos que son datos binarios del juego, no del modpack.
SALTAR_EN_MUNDOS = frozenset({"region", "entities", "poi", "DIM-1", "DIM1", "playerdata", "stats", "advancements"})
#: Carpetas de `config/` con contenido del modpack (misiones, menús, diálogos): ahí no se exige una clave de mensaje.
CONFIG_DE_CONTENIDO = re.compile(
    r"^(config|defaultconfigs)/(ftbquests|ftb_quests|betterquesting|hqm|hardcorequesting|heracles|odyssey|"
    r"questlog|fancymenu|drippyloadingscreen|custommainmenu|customnpcs|easy_npc|patchouli_books|tips|"
    r"loadingtips|openloader|paxi)/",
    re.I,
)
NOMBRES_NO = re.compile(r"^(license|licence|copying|changelog|changes|credits|readme|notice|authors)", re.I)
EXTENSIONES = {
    ".json": "json", ".json5": "json", ".mcmeta": "json", ".snbt": "snbt", ".nbt": "nbt", ".dat": "nbt",
    ".toml": "config", ".cfg": "config", ".properties": "config", ".ini": "config", ".js": "script",
    ".ts": "script", ".zs": "script", ".mcfunction": "funcion", ".lang": "lang", ".md": "md", ".txt": "txt",
    ".info": "json",
}  # fmt: skip
TOPE_ARCHIVO = 16 * 1024 * 1024


def _es_lang(ruta: str) -> str | None:
    """El idioma si es un archivo de idioma (`assets/<ns>/lang/en_us.json`, `shaders/lang/en_US.lang`…)."""
    p = PurePosixPath(ruta.lower())
    if len(p.parts) >= 2 and p.parts[-2] == "lang" and p.suffix in (".json", ".lang", ".snbt", ".json5"):
        return p.stem
    return None


def _sin_texto(ruta: str) -> bool:
    partes = PurePosixPath(ruta).parts
    return len(partes) >= 3 and partes[0] in ("assets", "data") and partes[2] in SIN_TEXTO


def _pares(formato: str, datos: bytes) -> Iterator[tuple[str, str]]:
    if formato == "nbt":
        yield from _cadenas_nbt(datos)
        return
    texto = datos.decode("utf-8-sig", "replace")
    if formato == "json":
        try:
            yield from _cadenas_json(_json_flexible(texto))
        except ValueError:
            yield from _cadenas_snbt(texto)  # JSON roto o con sintaxis rara: al menos sus cadenas
        return
    lectores: dict[str, Callable[[str], Iterator[tuple[str, str]]]] = {
        "snbt": _cadenas_snbt, "config": _cadenas_config, "script": _cadenas_script, "funcion": _cadenas_funcion,
    }  # fmt: skip
    yield from lectores.get(formato, _parrafos)(texto)


def leer_archivo(contenedor: str, ruta: str, datos: bytes) -> Iterator[Texto]:
    nombre = PurePosixPath(ruta).name
    formato = EXTENSIONES.get(PurePosixPath(ruta).suffix.lower())
    if formato is None or NOMBRES_NO.match(nombre) or len(datos) > TOPE_ARCHIVO or _sin_texto(ruta):
        return
    patron = patron_de(contenedor, ruta)
    idioma = _es_lang(ruta)
    if idioma is not None:
        if idioma == "en_us":  # otros idiomas no son la fuente
            yield from _lang(contenedor, ruta, datos, patron)
        return
    metadato = ruta in METADATOS
    config = not contenedor and re.match(r"^(config|defaultconfigs)/", ruta) and not CONFIG_DE_CONTENIDO.match(ruta)
    for campo, valor in _pares(formato, datos):
        if metadato and _campo_simple(campo) not in ("description", "summary"):
            continue  # del mod solo cuenta su descripción (el nombre es un nombre propio)
        if config and not _CAMPO_DE_MENSAJE.search(campo):
            continue  # en una configuración solo las claves de mensajes («welcomeMessage», «motd»…)
        if es_frase_inglesa(valor, campo):
            yield Texto(contenedor, ruta, formato, campo, valor, patron)


def _lang(contenedor: str, ruta: str, datos: bytes, patron: str) -> Iterator[Texto]:
    texto = datos.decode("utf-8-sig", "replace")
    pares: list[tuple[str, str]] = []
    if ruta.lower().endswith(".lang"):
        for ln in texto.splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                pares.append((k.strip(), v))
    else:
        try:
            datos_json = _json_flexible(texto)
        except ValueError:
            return
        if isinstance(datos_json, dict):
            pares = [(k, v) for k, v in cast(dict[str, Any], datos_json).items() if isinstance(v, str)]
    for k, v in pares:
        if sin_codigos(v).strip() and _PALABRA.search(v):
            yield Texto(contenedor, ruta, "lang", k, v, patron, clase="lang")


def _util_en_jar(nombre: str) -> bool:
    """Dentro de un jar solo cuentan `assets/`, `data/`, los metadatos del mod y los jars anidados."""
    return nombre.startswith(("assets/", "data/")) or nombre in METADATOS or nombre.lower().endswith((".jar", ".zip"))


def _recorrer_zip(contenedor: str, z: zipfile.ZipFile, profundidad: int = 0) -> Iterator[Texto]:
    es_mod = contenedor.startswith("mods/")
    for info in z.infolist():
        nombre = info.filename
        if info.is_dir() or info.file_size > TOPE_ARCHIVO * 4 or (es_mod and not _util_en_jar(nombre)):
            continue
        try:
            datos = z.read(info)
        except (zipfile.BadZipFile, OSError, NotImplementedError, zlib.error):
            continue
        if nombre.lower().endswith((".jar", ".zip")):
            if profundidad < 3:  # jars anidados (jar-in-jar)
                try:
                    with zipfile.ZipFile(io.BytesIO(datos)) as interno:
                        yield from _recorrer_zip(f"{contenedor}!{nombre}", interno, profundidad + 1)
                except zipfile.BadZipFile:
                    pass
            continue
        yield from leer_archivo(contenedor, nombre, datos)


def _archivo_suelto(juego: Path, p: Path) -> Iterator[Texto]:
    relativa = p.relative_to(juego).as_posix()
    if p.suffix.lower() in (".jar", ".zip"):
        try:
            with zipfile.ZipFile(p) as z:
                yield from _recorrer_zip(relativa, z)
        except (zipfile.BadZipFile, OSError):
            pass
        return
    if p.suffix.lower() not in EXTENSIONES:
        return
    try:
        if p.stat().st_size > TOPE_ARCHIVO:
            return
        datos = p.read_bytes()
    except OSError:
        return
    # en un pack en carpeta, el «contenedor» es la carpeta del pack (resourcepacks/X, datapacks/X…)
    partes = PurePosixPath(relativa).parts
    if len(partes) >= 3 and partes[0] in ("resourcepacks", "datapacks", "shaderpacks", "global_packs"):
        yield from leer_archivo("/".join(partes[:2]), "/".join(partes[2:]), datos)
    else:
        yield from leer_archivo("", relativa, datos)


def recorrer(juego: Path) -> Iterator[Texto]:
    """Todo el texto de la carpeta del juego: archivos sueltos, jars y zips (en cualquier carpeta)."""
    pila = [juego]
    while pila:
        carpeta = pila.pop()
        try:
            hijos = sorted(carpeta.iterdir())
        except OSError:
            continue
        for p in hijos:
            if not p.is_dir():
                yield from _archivo_suelto(juego, p)
                continue
            en_mundo = "saves" in p.relative_to(juego).parts[:-1]
            if p.name.lower() in SALTAR or p.is_symlink() or (en_mundo and p.name in SALTAR_EN_MUNDOS):
                continue
            pila.append(p)


def carpeta_juego(ruta: Path) -> Path:
    for sub in ("minecraft", ".minecraft"):
        if (ruta / sub).is_dir():
            return ruta / sub
    return ruta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instancia", type=Path)
    ap.add_argument("--salida", type=Path, required=True)
    args = ap.parse_args()
    juego = carpeta_juego(args.instancia)
    args.salida.mkdir(parents=True, exist_ok=True)
    por_patron: Counter[str] = Counter()
    lang = total = 0
    with (args.salida / "inventario.jsonl").open("w", encoding="utf-8") as f:
        for t in recorrer(juego):
            f.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")
            total += 1
            if t.clase == "lang":
                lang += 1
            else:
                por_patron[t.patron] += 1
    resumen = {"juego": str(juego), "textos": total, "lang": lang, "por_patron": dict(por_patron.most_common())}
    (args.salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.buffer.write(f"{total} textos ({lang} de archivos de idioma en inglés)\n".encode())
    for patron, n in por_patron.most_common(30):
        sys.stdout.buffer.write(f"  {n:>6}  {patron}\n".encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

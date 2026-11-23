"""Fuzzing por mutación de los parsers de formatos, con semillas reales del corpus y de tests/datos.

Para cada parser: toma semillas, las muta al azar (bits, truncado, duplicado, inserción de caracteres peligrosos,
anidamiento profundo) y llama al parser. Es fallo cualquier excepción que no sea la controlada (ValueError y sus
subclases, KeyError en lecturas de jar), un RecursionError, o una entrada que tarde más de 5 s también al
repetirla (la primera vez puede haber sido una suspensión del PC). Los tres primeros casos de cada firma se
guardan en FUZZ_SALIDA (por defecto .auditoria/fuzz/<parser>/).

Semillas: los archivos de tests/, de .descargas/ (scripts/descargar_corpus.py) y de las carpetas que diga
FUZZ_SEMILLAS (separadas por «;»). Sale con 1 si algún parser tuvo fallos (el workflow «Fuzzing» lo corre 1 h por
parser en GitHub Actions).

Uso: uv run python scripts/auditoria/fuzz_parsers.py <minutos por parser> [parser …]
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import sys
import tempfile
import time
import traceback
import zipfile
from collections.abc import Callable
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = Path(os.environ.get("FUZZ_SALIDA") or RAIZ / ".auditoria" / "fuzz")
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))
from descargar_corpus import RAIZ as DESCARGAS  # noqa: E402  (la .descargas compartida entre worktrees)

BASES = [RAIZ / "tests", DESCARGAS, *(Path(p) for p in os.environ.get("FUZZ_SEMILLAS", "").split(";") if p)]
sys.setrecursionlimit(3000)

from tests import fabrica  # noqa: E402

from traductor_es.formatos import (  # noqa: E402
    comandos,
    componente,
    javascript,
    json_cadenas,
    json_texto,
    lang_json,
    lang_json5,
    lang_legacy,
    markdown,
    nbt,
    propiedades,
    snbt,
)
from traductor_es.fuentes import opciones as opciones_fuente  # noqa: E402
from traductor_es.fuentes.contenedores import Zip, abrir_zip  # noqa: E402
from traductor_es.fuentes.version import Version, formato_desde_jar  # noqa: E402
from traductor_es.salida import opciones as opciones_salida  # noqa: E402

PELIGROSOS = [
    b'"', b"'", b"`", b"\\", b"{", b"}", b"[", b"]", b"(", b")", b":", b",", b"\n", b"\r", b"\x00", b"\xff",
    b"\xef\xbb\xbf", b"${", b"/*", b"*/", b"//", b"\xe2\x80\xa8", b"\xc0\x80", b"%s", b"\xed\xa0\x80", b"=", b"#",
    b"<", b">", b"$(", b"\t",
]  # fmt: skip


def _texto(f: Callable[[str], object]) -> Callable[[bytes], object]:
    return lambda b: f(b.decode("utf-8", errors="replace"))


def _snbt_ida_vuelta(src: str) -> None:
    cadenas = snbt.escanear(src)
    assert snbt.reemplazar(src, cadenas, {c.inicio: c.texto for c in cadenas}) == src, "ida y vuelta SNBT"
    snbt.reemplazar(src, cadenas, {c.inicio: c.texto + '"\\\n' for c in cadenas})


def _js_ida_vuelta(src: str) -> None:
    cadenas = javascript.escanear(src)
    assert javascript.reemplazar(src, cadenas, {c.inicio: c.texto for c in cadenas}) == src, "ida y vuelta JS"


def _json_ida_vuelta(src: str) -> None:
    cadenas = json_cadenas.escanear(src)
    assert json_cadenas.reemplazar(src, cadenas, {c.inicio: c.texto for c in cadenas}) == src, "ida y vuelta JSON"


def _json5_ida_vuelta(b: bytes) -> None:
    datos = lang_json5.leer(b)
    assert lang_json5.leer(lang_json5.escribir(datos)) == datos, "ida y vuelta JSON5"


def _nbt(b: bytes) -> None:
    raiz, compresion = nbt.leer(b)
    list(nbt.cadenas(raiz))
    nbt.escribir(raiz, compresion)


def _md(src: str) -> None:
    lineas, segs = markdown.segmentar(src)
    markdown.reconstruir(lineas, segs, {s.texto: s.texto for s in segs})


def _opciones(b: bytes) -> None:
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / "options.txt").write_bytes(b)
        opciones_fuente.leer(Path(t))
        opciones_salida.activar(Path(t), "Traduccion_ES", "es_mx", con_prefijo=None)


def _version(b: bytes) -> None:
    texto = b.decode("utf-8", errors="replace")[:40]
    with contextlib.suppress(ValueError):
        Version.de(texto)
    formato_desde_jar(b, "resource")


def _zip(b: bytes) -> None:
    try:
        zf = abrir_zip(io.BytesIO(b), "f.jar")  # como la app (H-035): no zipfile.ZipFile directo
    except (zipfile.BadZipFile, ValueError, OSError):  # EntradaIlegible es BadZipFile y ValueError
        return
    z = Zip("f.jar", zf)
    for n in z.nombres()[:20]:
        with contextlib.suppress(zipfile.BadZipFile, KeyError, OSError, NotImplementedError, EOFError, ValueError):
            z.leer(n)


PARSERS: dict[str, tuple[Callable[[bytes], object], tuple[str, ...]]] = {
    "snbt": (_texto(_snbt_ida_vuelta), ("*.snbt",)),
    "nbt": (_nbt, ("*.nbt", "*.dat")),
    "json_cadenas": (_texto(_json_ida_vuelta), ("*.json",)),
    "json_texto": (_texto(json_texto.extraer), ("*.json",)),
    "lang_json": (lang_json.leer, ("en_us.json",)),
    "lang_json5": (_json5_ida_vuelta, ("*.json5", "en_us.json")),
    "lang_legacy": (lang_legacy.leer, ("en_US.lang", "en_us.lang")),
    "javascript": (_texto(_js_ida_vuelta), ("*.js",)),
    "comandos": (_texto(lambda s: [comandos.analizar(x) for x in s.splitlines()[:200]]), ("*.mcfunction",)),
    "componente": (_texto(componente.unidades), ("*.json",)),
    "markdown": (_texto(_md), ("*.md",)),
    "propiedades": (_texto(propiedades.leer), ("*.properties",)),
    "options": (_opciones, ("options.txt",)),
    "version": (_version, ("version.json", "mmc-pack.json")),
    "zip": (_zip, ("*.zip",)),
}
CONTROLADAS = (ValueError, KeyError, zipfile.BadZipFile)


def _semillas_propias() -> dict[str, list[bytes]]:
    """Semillas binarias generadas, por si no hay archivos de ese tipo (en el CI no está el corpus de jars)."""
    lang = fabrica.lang("m", "en_us", {"item.m.gear": "Gear", "tip.m.a": "%s gave %s"})
    jar = fabrica.zip_en_memoria({**lang, "pack.mcmeta": '{"pack": {"pack_format": 15}}', "a/b.txt": "x" * 200})
    display = nbt.Compuesto()
    display.hijos["Name"] = (nbt.STRING, '{"text":"Shiny"}')
    display.hijos["Lore"] = (nbt.LISTA, nbt.Lista(nbt.STRING, ["Line one", "Line two"]))
    quest = nbt.Compuesto()
    quest.hijos["title"] = (nbt.STRING, "Getting Started")
    quest.hijos["text"] = (nbt.LISTA, nbt.Lista(nbt.STRING, ["Hello", "", "World"]))
    quest.hijos["display"] = (nbt.COMPUESTO, display)
    arbol = nbt.Raiz(nbt.COMPUESTO, "", quest)
    return {
        "zip": [jar],
        "nbt": [nbt.escribir(arbol, "gzip"), nbt.escribir(arbol, "ninguna"), nbt.escribir(arbol, "zlib")],
    }


def semillas(
    patrones: tuple[str, ...], azar: random.Random, n: int = 40, propias: list[bytes] | None = None
) -> list[bytes]:
    encontradas: list[Path] = []
    for p in patrones:
        for base in BASES:
            if not base.is_dir():
                continue
            for ruta in base.rglob(p):
                if ruta.is_file() and ruta.stat().st_size < 400_000:
                    encontradas.append(ruta)
                if len(encontradas) > 2000:
                    break
    azar.shuffle(encontradas)
    datos = [r.read_bytes() for r in encontradas[:n]] + list(propias or [])
    return datos or [b"{}", b'{"a": "b"}', b"a=b\n"]


def mutar(b: bytes, azar: random.Random) -> bytes:
    datos = bytearray(b)
    for _ in range(azar.randint(1, 8)):
        op = azar.randrange(7)
        pos = azar.randint(0, len(datos)) if datos else 0
        if op == 0 and datos:
            datos[min(pos, len(datos) - 1)] ^= 1 << azar.randrange(8)
        elif op == 1:
            datos[pos:pos] = azar.choice(PELIGROSOS)
        elif op == 2 and datos:
            del datos[pos : pos + azar.randint(1, 16)]
        elif op == 3 and datos:
            datos = datos[: azar.randint(0, len(datos))]  # truncado
        elif op == 4 and datos:
            inicio = azar.randint(0, len(datos) - 1)
            datos[pos:pos] = datos[inicio : inicio + azar.randint(1, 64)]
        elif op == 5:
            abrir, cerrar = azar.choice([(b"{", b"}"), (b"[", b"]"), (b"(", b")")])
            k = azar.choice([10, 200, 2500])
            datos[pos:pos] = abrir * k + cerrar * azar.choice([0, k])
        else:
            datos[pos:pos] = bytes(azar.randrange(256) for _ in range(azar.randint(1, 8)))
    return bytes(datos)


def fuzz(nombre: str, minutos: float, semilla: int = 0) -> dict[str, object]:
    funcion, patrones = PARSERS[nombre]
    azar = random.Random(semilla)
    base = semillas(patrones, azar, propias=_semillas_propias().get(nombre))
    fin = time.monotonic() + minutos * 60
    casos = 0
    fallos: dict[str, int] = {}
    carpeta = SALIDA / nombre
    lento_max = 0.0
    while time.monotonic() < fin:
        entrada = mutar(azar.choice(base), azar)
        casos += 1
        inicio = time.perf_counter()
        firma = None
        try:
            funcion(entrada)
        except CONTROLADAS:
            pass
        except RecursionError:
            firma = "RecursionError"
        except AssertionError as e:
            firma = f"AssertionError {e}"
        except Exception as e:  # justo lo que busca el fuzzing
            ultimo = traceback.extract_tb(e.__traceback__)[-1]
            firma = f"{type(e).__name__} en {Path(ultimo.filename).name}:{ultimo.lineno}"
        segundos = time.perf_counter() - inicio
        lento_max = max(lento_max, segundos)
        if segundos > 5 and firma is None:
            # Se repite para descartar que el PC se haya suspendido a mitad del caso (el reloj sigue contando)
            inicio = time.perf_counter()
            with contextlib.suppress(Exception):  # solo se mide el tiempo
                funcion(entrada)
            if time.perf_counter() - inicio > 5:
                firma = "lento >5 s"
        if firma:
            fallos[firma] = fallos.get(firma, 0) + 1
            if fallos[firma] <= 3:
                carpeta.mkdir(parents=True, exist_ok=True)
                (carpeta / f"{len(fallos):02d}_{fallos[firma]}.bin").write_bytes(entrada[:200_000])
                (carpeta / f"{len(fallos):02d}_{fallos[firma]}.txt").write_text(firma, encoding="utf-8")
    return {
        "parser": nombre,
        "casos": casos,
        "semillas": len(base),
        "mas_lento_s": round(lento_max, 2),
        "fallos": fallos,
    }


def main() -> int:
    minutos = float(sys.argv[1])
    nombres = sys.argv[2:] or list(PARSERS)
    con_fallos = False
    for nombre in nombres:
        r = fuzz(nombre, minutos)
        con_fallos |= bool(r["fallos"])
        print(json.dumps(r, ensure_ascii=False), flush=True)
    return 1 if con_fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())

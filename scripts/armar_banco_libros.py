"""Arma un banco de libros (Patchouli) con traducciones humanas, para medir la calidad en textos largos.

Usa los libros que bajó `scripts/descargar_lang.py` de mods de licencia libre (.descargas/<pack>/langs/<jar>/…):
cada archivo en inglés se empareja con su versión en español del mismo mod, campo por campo
(`paquete.emparejar_libro`), y se descartan las referencias a medias (inglés y español mezclados). El banco va a
`.descargas/banco/libros.json`, solo para uso local (ver docs/datos-de-terceros.md).

Uso:  uv run python scripts/armar_banco_libros.py [--textos 150] [--salida RUTA]
Y luego:  uv run python scripts/medir_calidad.py --banco .descargas/banco/libros.json --vanilla .descargas/vanilla
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import armar_banco_local as abl
import descargar_corpus as dc

from traductor_es.salida.paquete import emparejar_libro

#: …/langs/<jar>/assets/<espacio>/patchouli_books/<libro>/en_us/<resto>.json
_EN_INGLES = re.compile(r"langs/([^/]+)/assets/([^/]+)/patchouli_books/([^/]+)/en_us/(.+\.json)$")
#: Variantes de español en el orden en que se prefieren como referencia.
_PREFERIDAS = ("es_mx", "es_es")
#: Desde Patchouli 1.20 casi todos los libros usan claves de idioma (`"i18n": true`): su texto vive en `lang/`.
#: Una clave de libro tiene uno de estos tramos («mysticalagriculture.guide.entry…», «occultism.book.…»).
_CLAVE_DE_LIBRO = re.compile(r"(^|[._])(book|books|guide|guidebook|lexicon|codex|journal|manual)([._]|$)", re.I)
_NO_ES_LIBRO = ("options.", "config.", "modernfix.")
#: Largo mínimo de un texto de libro sacado de `lang/` (los títulos cortos ya los mide el banco de interfaz).
_MINIMO_LANG = 60
#: Tope de textos por mod, para que un mod con un libro enorme no ocupe medio banco.
_MAXIMO_POR_MOD = 25


@dataclass(frozen=True, slots=True)
class ParLibro:
    jar: str
    libro: str
    ingles: str
    castellano: str


def pares_de_libros(raiz: Path) -> list[ParLibro]:
    """Los textos de libros que existen en inglés y en español en el mismo mod, sin referencias a medias."""
    salida: list[ParLibro] = []
    for ingles in sorted(raiz.glob("*/langs/*/assets/*/patchouli_books/*/en_us/**/*.json")):
        m = _EN_INGLES.search(ingles.as_posix())
        if m is None:
            continue
        jar, espacio, libro, resto = m.groups()
        base = ingles.parents[len(Path(resto).parts) - 1]  # …/patchouli_books/<libro>/en_us
        variantes = sorted(p.name for p in base.parent.iterdir() if p.is_dir() and p.name.startswith("es_"))
        orden = [v for v in _PREFERIDAS if v in variantes] + [v for v in variantes if v not in _PREFERIDAS]
        espanol = next((base.parent / v / resto for v in orden if (base.parent / v / resto).is_file()), None)
        if espanol is None:
            continue
        for en, es in emparejar_libro(ingles.read_bytes(), espanol.read_bytes()).items():
            if abl.referencia_limpia(en, es):
                salida.append(ParLibro(jar, f"{espacio}:{libro}", en, es))
    return salida


def pares_de_libros_en_lang(pares: list[abl.Par]) -> list[ParLibro]:
    """Textos largos de libros que vienen en los archivos de idioma, por su clave."""
    return [
        ParLibro(p.jar, f"{p.namespace}:lang", p.ingles, p.castellano)
        for p in pares
        if _CLAVE_DE_LIBRO.search(p.clave)
        and not p.clave.startswith(_NO_ES_LIBRO)
        and len(p.ingles) >= _MINIMO_LANG
        and abl.referencia_limpia(p.ingles, p.castellano)
    ]


def armar(raiz: Path, textos: int, semilla: int = 7, pares_lang: list[abl.Par] | None = None) -> dict[str, Any]:
    """El banco: una muestra fija de textos de libros, con el glosario que sacaría la app de los demás mods.

    Junta los libros en JSON y los que vienen en `lang/`, con un tope por mod.
    """
    lang = abl.pares() if pares_lang is None else pares_lang
    todos = sorted(
        set(pares_de_libros(raiz)) | set(pares_de_libros_en_lang(lang)), key=lambda p: (p.jar, p.libro, p.ingles)
    )
    unicos = list({p.ingles: p for p in todos}.values())  # un texto repetido cuenta una vez
    azar = random.Random(semilla)
    azar.shuffle(unicos)
    por_mod: dict[str, int] = {}
    elegidos: list[ParLibro] = []
    for p in unicos:
        if len(elegidos) >= textos or por_mod.get(p.jar, 0) >= _MAXIMO_POR_MOD:
            continue
        por_mod[p.jar] = por_mod.get(p.jar, 0) + 1
        elegidos.append(p)
    medir = {p.jar for p in elegidos}
    glosario = abl.glosario_del_banco(lang, medir, ingenuo=False) if (raiz / "vanilla").is_dir() else {}
    return {
        "descripcion": "Textos reales de libros (Patchouli) de mods libres, en inglés y español. Solo uso local.",
        "dialecto": "es_mx",
        "glosario": glosario,
        "textos": [
            {"ambito": "libro", "original": p.ingles, "referencia": p.castellano, "jar": p.jar, "pista": "libro: text"}
            for p in elegidos
        ],
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--textos", type=int, default=150)
    ap.add_argument("--salida", type=Path, default=None, help="por defecto .descargas/banco/libros.json")
    args = ap.parse_args(argv)
    banco = armar(dc.RAIZ, args.textos)
    if not banco["textos"]:
        print("No hay libros con traducción al español: baja antes el corpus con scripts/descargar_lang.py.")
        return 1
    destino = args.salida or dc.RAIZ / "banco" / "libros.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(banco, indent=1, ensure_ascii=False), encoding="utf-8")
    libros = {t["jar"] for t in banco["textos"]}
    print(f"Banco de libros: {len(banco['textos'])} textos de {len(libros)} mods → {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

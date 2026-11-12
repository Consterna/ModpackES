"""Arma un banco de calidad con pares inglés/castellano reales de mods libres (salida SOLO local).

Lee .descargas/*/langs (scripts/descargar_lang.py), junta los textos que existen en ambos idiomas y los
guarda en .descargas/banco/referencia_real.json con el mismo formato que tests/datos/referencia_es.json,
para `scripts/medir_calidad.py --banco`. Ese archivo es de terceros: no va al repo (docs/datos-de-terceros.md).
También informa cuántos términos del glosario saldrían de esos jars.

Cada texto lleva su «pista» (mod, clave y tipo, como la manda la app) y el banco trae «ejemplos»: pares de
OTROS mods (la mitad de los jars sirve para medir y la otra mitad para los ejemplos, así ningún texto medido
se usa como ejemplo de sí mismo ni de su mod). `medir_calidad.py --sin-contexto` mide sin pistas ni ejemplos.

Uso:  uv run python scripts/armar_banco_local.py [--frases 150] [--nombres 100]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

import descargar_corpus as dc

from traductor_es.formatos import lang_json, lang_legacy
from traductor_es.modulos.mods import Mods, es_nombre
from traductor_es.nucleo import terminos
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import es_traducible

PREFERIDOS = ("es_mx", "es_es", "es_ar", "es_uy", "es_ve", "es_cl")


class Par(NamedTuple):
    jar: str
    namespace: str
    clave: str
    ingles: str
    castellano: str


def _leer(ruta: Path) -> dict[str, str]:
    modulo = lang_json if ruta.suffix == ".json" else lang_legacy
    try:
        return modulo.leer(ruta.read_bytes())
    except (ValueError, OSError):
        return {}


def pares() -> list[Par]:
    """Los textos de cada carpeta lang que existen en inglés y en castellano."""
    salida: list[Par] = []
    for ingles in sorted(dc.RAIZ.glob("*/langs/*/assets/*/lang/en_[uU][sS].*")):
        castellano = next(
            (
                c
                for p in PREFERIDOS
                for c in ingles.parent.glob("*")
                if c.stem.lower() == p and c.suffix == ingles.suffix
            ),
            None,
        )
        if castellano is None:
            continue
        en, es = _leer(ingles), _leer(castellano)
        for clave, valor_en in en.items():
            valor_es = es.get(clave)
            if valor_es and valor_en.strip() != valor_es.strip() and es_traducible(valor_en):
                salida.append(Par(ingles.parts[-5], ingles.parts[-3], clave, valor_en.strip(), valor_es.strip()))
    return salida


def glosario_del_banco(todos: list[Par], medir: set[str], ingenuo: bool) -> dict[str, str]:
    """Los nombres que la app sacaría del español de los mods instalados (la mitad de los jars que no se mide).

    Como en la app: primero los nombres del juego (es_mx antes que es_es) y después los de cada mod; si dos mods
    traducen distinto el mismo término, no se usa ninguno. Con `ingenuo` se hace como antes: lo primero que aparece.
    """
    g = Glosario()
    vanilla = dc.RAIZ / "vanilla"
    if not ingenuo and (vanilla / "en_us.json").is_file():
        ingles: dict[str, str] = json.loads((vanilla / "en_us.json").read_text(encoding="utf-8"))
        nombres = {k: v for k, v in ingles.items() if es_nombre(k)}
        for variante in ("es_mx", "es_es"):
            traducido: dict[str, str] = json.loads((vanilla / f"{variante}.json").read_text(encoding="utf-8"))
            g.agregar_pares(nombres, traducido, fuente="minecraft", oficial=True)
    for jar in sorted({p.jar for p in todos if p.jar not in medir}):
        propios = [p for p in todos if p.jar == jar and es_nombre(p.clave)]
        g.agregar_pares(
            {f"{p.namespace}:{p.clave}": p.ingles for p in propios},
            {f"{p.namespace}:{p.clave}": p.castellano for p in propios},
            fuente="" if ingenuo else jar,
        )
    if not ingenuo:
        print(f"Glosario del banco: {len(g.todos())} términos ({len(g.en_conflicto)} descartados por contradicción)")
    return g.todos()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frases", type=int, default=150)
    ap.add_argument("--nombres", type=int, default=100)
    ap.add_argument("--familias", type=int, default=25, help="términos repetidos cuyos nombres se agregan completos")
    ap.add_argument("--glosario-ingenuo", action="store_true", help="glosario como antes: sin juego y sin descartar")
    ap.add_argument(
        "--salida", type=Path, default=None, help="dónde guardar (por defecto .descargas/banco/referencia_real.json)"
    )
    args = ap.parse_args()
    todos = sorted(set(pares()))
    jars = sorted({p.jar for p in todos})
    print(f"{len(todos)} pares en/es distintos de {len(jars)} jars")
    g = Glosario()
    g.agregar_pares({p.ingles: p.ingles for p in todos}, {p.ingles: p.castellano for p in todos})
    print(f"Glosario que saldría de ellos: {len(g)} términos")
    medir = set(jars[::2])  # la mitad de los mods se mide; los pares de la otra mitad son los ejemplos
    candidatos = [p for p in todos if p.jar in medir]
    azar = random.Random(7)
    frases = [p for p in candidatos if len(p.ingles.split()) >= 5 and len(p.ingles) <= 220]
    nombres = [p for p in candidatos if len(p.ingles.split()) <= 3 and 3 <= len(p.ingles) <= 32]
    elegidos = azar.sample(frases, min(args.frases, len(frases))) + azar.sample(
        nombres, min(args.nombres, len(nombres))
    )
    # Familias de nombres que comparten un término («Moon Berries Pie», «… Jam»): miden la consistencia
    vistos = {p.ingles for p in elegidos}
    solo_nombres = [p for p in candidatos if len(p.ingles) <= 40]
    for termino in terminos.repetidos((p.ingles for p in solo_nombres), minimo=4, maximo=args.familias):
        patron = re.compile(r"(?<![^\W_])" + re.escape(termino) + r"(?![^\W_])")
        miembros = [p for p in solo_nombres if patron.search(p.ingles) and p.ingles not in vistos]
        for p in azar.sample(miembros, min(6, len(miembros))):
            elegidos.append(p)
            vistos.add(p.ingles)
    en_el_banco = {p.ingles for p in elegidos}
    ejemplos = {p.ingles: p.castellano for p in todos if p.jar not in medir and p.ingles not in en_el_banco}
    glosario = glosario_del_banco(todos, medir, args.glosario_ingenuo)
    banco: dict[str, Any] = {
        "descripcion": "Pares reales en/es de mods libres, solo para uso local (no se publica).",
        "dialecto": "es_mx",
        "glosario": glosario,
        "textos": [
            {
                "ambito": "ui",
                "original": p.ingles,
                "referencia": p.castellano,
                "jar": p.jar,
                "pista": Mods.pista(p.namespace, p.clave),
            }
            for p in elegidos
        ],
        "ejemplos": ejemplos,
    }
    destino = args.salida or dc.RAIZ / "banco" / "referencia_real.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(banco, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(elegidos)} textos y {len(ejemplos)} ejemplos de otros mods en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

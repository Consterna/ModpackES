"""Arma un banco de calidad con pares inglés/castellano reales de mods libres (salida SOLO local).

Lee .descargas/*/langs (scripts/descargar_lang.py), junta los textos que existen en ambos idiomas y los
guarda en .descargas/banco/referencia_real.json con el mismo formato que tests/datos/referencia_es.json,
para `scripts/medir_calidad.py --banco`. Ese archivo es de terceros: no va al repo (docs/datos-de-terceros.md).
También informa cuántos términos del glosario saldrían de esos jars.

Uso:  uv run python scripts/armar_banco_local.py [--frases 150] [--nombres 100]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

import descargar_corpus as dc

from traductor_es.formatos import lang_json, lang_legacy
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import es_traducible

PREFERIDOS = ("es_mx", "es_es", "es_ar", "es_uy", "es_ve", "es_cl")


def _leer(ruta: Path) -> dict[str, str]:
    modulo = lang_json if ruta.suffix == ".json" else lang_legacy
    try:
        return modulo.leer(ruta.read_bytes())
    except (ValueError, OSError):
        return {}


def pares() -> list[tuple[str, str, str]]:
    """[(jar, inglés, castellano)] de cada carpeta lang con las dos lenguas."""
    salida: list[tuple[str, str, str]] = []
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
                salida.append((ingles.parts[-5], valor_en.strip(), valor_es.strip()))
    return salida


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frases", type=int, default=150)
    ap.add_argument("--nombres", type=int, default=100)
    args = ap.parse_args()
    todos = sorted(set(pares()))
    print(f"{len(todos)} pares en/es distintos de {len({j for j, _, _ in todos})} jars")
    g = Glosario()
    g.agregar_pares({e: e for _, e, _ in todos}, {e: s for _, e, s in todos})
    print(f"Glosario que saldría de ellos: {len(g)} términos")
    azar = random.Random(7)
    frases = [t for t in todos if len(t[1].split()) >= 5 and len(t[1]) <= 220]
    nombres = [t for t in todos if len(t[1].split()) <= 3 and 3 <= len(t[1]) <= 32]
    elegidos = azar.sample(frases, min(args.frases, len(frases))) + azar.sample(
        nombres, min(args.nombres, len(nombres))
    )
    banco: dict[str, Any] = {
        "descripcion": "Pares reales en/es de mods libres, solo para uso local (no se publica).",
        "dialecto": "es_mx",
        "glosario": {},
        "textos": [{"ambito": "ui", "original": e, "referencia": s, "jar": j} for j, e, s in elegidos],
    }
    destino = dc.RAIZ / "banco" / "referencia_real.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(banco, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(elegidos)} textos en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

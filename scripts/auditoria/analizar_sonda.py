"""Analiza lo que volcó la sonda del juego (`<juego>/modpackes-sonda/`) en una instancia traducida con `--simular`.

Con el simulador, todo lo que la app tradujo empieza con «ES». Así, lo que se ve en inglés salta a la vista:
- **Idioma cargado** (`idioma.json`): claves cuyo valor sigue igual al inglés y es una frase. Se separan las que no
  están en ningún archivo de idioma de la instancia (las crea un mod mientras el juego corre: KubeJS, ARRP…).
- **Texto dibujado** (`textos-dibujados.json`): lo que pasó por la fuente del juego sin «ES» y en inglés, por pantalla.
- **Claves crudas en pantalla** (`a.b.c` dibujado tal cual): una traducción rota o una clave que falta.

Uso:
    uv run python scripts/auditoria/analizar_sonda.py RUTA_DE_LA_INSTANCIA [--salida build/auditoria/juego-<pack>.json]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventario import es_frase_inglesa, sin_codigos

MARCA = "«ES»"
_CLAVE_CRUDA = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_\-]+){2,}$")


def _juego(ruta: Path) -> Path:
    for sub in ("minecraft", ".minecraft"):
        if (ruta / sub).is_dir():
            return ruta / sub
    return ruta


def claves_en_archivos(juego: Path) -> set[str]:
    """Todas las claves de los `en_us.json` de los jars, zips y carpetas de la instancia (lo que se ve sin jugar)."""
    claves: set[str] = set()
    patron = re.compile(r"(^|/)assets/[^/]+/lang/en_us\.json$")

    def de_zip(z: zipfile.ZipFile, profundidad: int = 0) -> None:
        for n in z.namelist():
            try:
                if patron.search(n):
                    datos: object = json.loads(z.read(n).decode("utf-8-sig", "replace"))
                    if isinstance(datos, dict):
                        claves.update(cast(dict[str, Any], datos))
                elif n.endswith(".jar") and profundidad < 3:
                    with zipfile.ZipFile(io.BytesIO(z.read(n))) as interno:
                        de_zip(interno, profundidad + 1)
            except (ValueError, zipfile.BadZipFile, OSError):
                continue

    for p in juego.rglob("*"):
        try:
            if p.suffix.lower() in (".jar", ".zip") and p.is_file():
                with zipfile.ZipFile(p) as z:
                    de_zip(z)
            elif p.is_file() and patron.search(p.as_posix()):
                datos = json.loads(p.read_text(encoding="utf-8-sig", errors="replace"))
                if isinstance(datos, dict):
                    claves.update(cast(dict[str, Any], datos))
        except (ValueError, zipfile.BadZipFile, OSError):
            continue
    return claves


def analizar(instancia: Path) -> dict[str, Any]:
    juego = _juego(instancia)
    carpeta = juego / "modpackes-sonda"
    idioma: dict[str, Any] = json.loads((carpeta / "idioma.json").read_text(encoding="utf-8"))
    entradas = cast(dict[str, Any], idioma.get("claves") or idioma.get("entradas") or {})
    if isinstance(entradas, list):
        entradas = {str(e.get("clave")): e for e in cast(list[dict[str, Any]], entradas)}
    en_archivos = claves_en_archivos(juego)
    en_ingles: list[dict[str, str]] = []
    de_ejecucion: list[dict[str, str]] = []
    traducidas = 0
    for clave, e in entradas.items():
        valor = str(e.get("valor", ""))
        if MARCA in valor or not e.get("igual"):
            traducidas += 1 if MARCA in valor else 0
            continue
        if not es_frase_inglesa(valor, "text"):
            continue
        fila = {"clave": clave, "valor": valor[:160]}
        (en_ingles if clave in en_archivos else de_ejecucion).append(fila)
    resultado: dict[str, Any] = {
        "idioma_del_juego": idioma.get("idioma"),
        "claves_cargadas": len(entradas),
        "con_marca_de_traduccion": traducidas,
        "en_ingles_de_archivos": len(en_ingles),
        "en_ingles_creadas_al_jugar": len(de_ejecucion),
        "por_espacio_de_archivos": Counter(f["clave"].split(".")[1] if f["clave"].count(".") else "?"
                                           for f in en_ingles).most_common(25),
        "ejemplos_de_archivos": en_ingles[:40],
        "ejemplos_creadas_al_jugar": de_ejecucion[:60],
    }  # fmt: skip
    dibujados = carpeta / "textos-dibujados.json"
    if dibujados.is_file():
        datos: dict[str, Any] = json.loads(dibujados.read_text(encoding="utf-8"))
        lista = cast(list[dict[str, Any]], datos.get("textos") or datos.get("entradas") or [])
        sin_marca: Counter[str] = Counter()
        crudas: Counter[str] = Counter()
        ejemplos: dict[str, list[str]] = {}
        for t in lista:
            texto = sin_codigos(str(t.get("texto", ""))).strip()
            pantallas = cast(list[str], t.get("pantallas") or [t.get("pantalla", "")])
            pantalla = str(pantallas[0]) if pantallas else ""
            if _CLAVE_CRUDA.match(texto):
                crudas[texto] += 1
            elif MARCA not in texto and es_frase_inglesa(texto, "text"):
                sin_marca[pantalla] += 1
                ejemplos.setdefault(pantalla, [])
                if len(ejemplos[pantalla]) < 8:
                    ejemplos[pantalla].append(texto[:120])
        resultado["dibujados"] = {
            "total": len(lista),
            "en_ingles_por_pantalla": sin_marca.most_common(30),
            "ejemplos": ejemplos,
            "claves_crudas": crudas.most_common(40),
        }
    return resultado


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instancia", type=Path)
    ap.add_argument("--salida", type=Path)
    args = ap.parse_args()
    r = analizar(args.instancia)
    texto = json.dumps(r, ensure_ascii=False, indent=2)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto, encoding="utf-8")
    sys.stdout.buffer.write(texto[:6000].encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

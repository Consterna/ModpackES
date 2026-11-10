"""Baja solo los archivos de idioma (lang) de los mods de licencia libre de los packs del corpus.

Para cada mod del índice cuya licencia (según Modrinth) sea libre, lee el directorio del jar con peticiones
por rangos y baja solo `assets/*/lang/` en inglés y español. Lo deja en .descargas/<pack>/langs/<jar>/ para
medir el glosario y la calidad (ver docs/datos-de-terceros.md). No baja jars completos ni mods con
licencia reservada o dudosa.

Uso:  uv run python scripts/descargar_lang.py [pack ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import descargar_corpus as dc
from auditar_licencias import mods_por_hash

LANG = re.compile(r"^assets/[^/]+/lang/(en_us\.json|en_US\.lang|es_[a-z]{2}\.(json|lang)|es_[A-Z]{2}\.lang)$")
LIMITE_POR_PACK = 30 * 1024 * 1024


def bajar_langs(pack: Path) -> dict[str, Any]:
    indice: Any = json.loads((pack / "modrinth.index.json").read_text(encoding="utf-8"))
    archivos = [f for f in indice.get("files", []) if str(f.get("path", "")).startswith("mods/")]
    licencias = mods_por_hash([f["hashes"]["sha1"] for f in archivos if "sha1" in f.get("hashes", {})])
    resumen: dict[str, Any] = {"bajados": [], "omitidos": []}
    total = 0
    for f in archivos:
        info = licencias.get(f.get("hashes", {}).get("sha1", ""))
        nombre = Path(f["path"]).name
        if info is None or info["clase"] != "libre":
            resumen["omitidos"].append({"jar": nombre, "motivo": info["licencia"] if info else "desconocido"})
            continue
        url = f["downloads"][0]
        try:
            entradas = [e for e in dc.directorio_central(url, dc.tamano(url)) if LANG.match(e.nombre)]
        except (OSError, RuntimeError) as e:
            resumen["omitidos"].append({"jar": nombre, "motivo": f"error: {e}"})
            continue
        total += sum(e.comprimido for e in entradas)
        if total > LIMITE_POR_PACK:
            resumen["omitidos"].append({"jar": nombre, "motivo": "límite del pack"})
            break
        for e in entradas:
            ruta = pack / "langs" / nombre / e.nombre
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(dc.bajar(url, e))
        if entradas:
            resumen["bajados"].append({"jar": nombre, "licencia": info["licencia"], "archivos": len(entradas)})
    (pack / "langs").mkdir(exist_ok=True)
    (pack / "langs" / "_licencias.json").write_text(json.dumps(resumen, indent=1, ensure_ascii=False), encoding="utf-8")
    return resumen


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    elegidos = sys.argv[1:] or [p.name for p in sorted(dc.RAIZ.iterdir()) if (p / "modrinth.index.json").is_file()]
    for slug in elegidos:
        r = bajar_langs(dc.RAIZ / slug)
        print(f"{slug}: {len(r['bajados'])} mods con idioma, {len(r['omitidos'])} omitidos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

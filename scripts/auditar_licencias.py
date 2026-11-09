"""Anota la licencia de cada pack del corpus y de sus mods, con solo metadatos públicos de Modrinth.

Lee .descargas/<pack>/modrinth.index.json, pregunta a la API de Modrinth por el proyecto del pack y por los
hashes SHA-1 de sus mods (no se sube ningún archivo) y escribe .descargas/licencias.json.

Uso:  uv run python scripts/auditar_licencias.py [pack ...]
Ver docs/datos-de-terceros.md para qué se puede hacer con cada licencia.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

from descargar_corpus import AGENTE, PACKS, RAIZ

API = "https://api.modrinth.com/v2"
#: Licencias que permiten guardar una copia local de pruebas sin pedir permiso (identificadores SPDX de Modrinth).
LIBRES = re.compile(r"^(MIT|Apache-2\.0|BSD|ISC|MPL-2\.0|Unlicense|CC0|CC-BY|CC-BY-SA|LGPL|GPL|AGPL|Zlib)", re.I)


def _api(ruta: str, cuerpo: Any = None) -> Any:
    datos = None if cuerpo is None else json.dumps(cuerpo).encode()
    cab = {"User-Agent": AGENTE, "Content-Type": "application/json"}
    req = urllib.request.Request(f"{API}{ruta}", data=datos, headers=cab)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _id_proyecto(url: str) -> str:
    m = re.search(r"/data/([^/]+)/versions/", url)
    if not m:
        raise ValueError(f"No encuentro el proyecto en {url}")
    return m.group(1)


def _clase(licencia: dict[str, Any]) -> str:
    spdx = str(licencia.get("id", ""))
    if spdx.startswith("LicenseRef-All-Rights-Reserved"):
        return "reservada"
    return "libre" if LIBRES.match(spdx) else "revisar"


def mods_por_hash(hashes: list[str]) -> dict[str, dict[str, str]]:
    """{sha1: {slug, licencia, clase}} de los mods que Modrinth reconoce."""
    if not hashes:
        return {}
    versiones: dict[str, Any] = _api("/version_files", {"hashes": hashes, "algorithm": "sha1"})
    ids = sorted({v["project_id"] for v in versiones.values()})
    proyectos: dict[str, Any] = {}
    for i in range(0, len(ids), 200):
        lote = urllib.parse.quote(json.dumps(ids[i : i + 200], separators=(",", ":")))
        proyectos.update({x["id"]: x for x in _api("/projects?ids=" + lote)})
    salida: dict[str, dict[str, str]] = {}
    for h, v in versiones.items():
        x = proyectos[v["project_id"]]
        lic = x.get("license") or {}
        salida[h] = {"slug": x["slug"], "licencia": str(lic.get("id", "?")), "clase": _clase(lic)}
    return salida


def auditar(slug: str) -> dict[str, Any]:
    indice = json.loads((RAIZ / slug / "modrinth.index.json").read_text(encoding="utf-8"))
    p = _api(f"/project/{_id_proyecto(PACKS[slug])}")
    hashes = [f["hashes"]["sha1"] for f in indice.get("files", []) if "sha1" in f.get("hashes", {})]
    mods = mods_por_hash(hashes)
    por_proyecto = {m["slug"]: m for m in mods.values()}
    por_clase: Counter[str] = Counter(m["clase"] for m in por_proyecto.values())
    return {
        "pack": {"titulo": p["title"], "licencia": p.get("license"), "clase": _clase(p.get("license") or {})},
        "mods_en_indice": len(hashes),
        "mods_identificados": len(por_proyecto),
        "mods_por_clase": dict(por_clase),
        "mods_licencia_a_revisar": sorted(
            f"{m['slug']} ({m['licencia']})" for m in por_proyecto.values() if m["clase"] == "revisar"
        ),
    }


def main() -> int:
    elegidos = sys.argv[1:] or list(PACKS)
    informe: dict[str, Any] = {}
    for slug in elegidos:
        try:
            informe[slug] = auditar(slug)
        except (OSError, ValueError, KeyError) as e:
            informe[slug] = {"error": str(e)}
        r = informe[slug]
        print(f"{slug}: {r.get('pack', r)}")
        if "mods_por_clase" in r:
            print(f"   mods: {r['mods_por_clase']}")
    (RAIZ / "licencias.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Escrito {RAIZ / 'licencias.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

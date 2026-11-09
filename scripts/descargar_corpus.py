"""Baja SOLO las partes útiles (índice, configs de misiones, KubeJS) de modpacks públicos de Modrinth.

Usa peticiones HTTP por rangos: lee el directorio central del .mrpack y después solo los archivos elegidos,
sin descargar el pack entero. Lo deja en .descargas/<slug>/ (excluido de git) para las pruebas.

Uso:  uv run python scripts/descargar_corpus.py
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _raiz_descargas() -> Path:
    """TRADUCTOR_ES_DESCARGAS, o .descargas del checkout principal (los worktrees comparten la misma)."""
    propia = os.environ.get("TRADUCTOR_ES_DESCARGAS")
    if propia:
        return Path(propia)
    aqui = Path(__file__).resolve().parent.parent
    try:
        comun = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=aqui,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        principal = Path(comun).parent
        if (principal / ".descargas").is_dir():
            return principal / ".descargas"
    except (OSError, subprocess.CalledProcessError):
        pass
    return aqui / ".descargas"


RAIZ = _raiz_descargas()
AGENTE = "ModpackES/2.0 (corpus de pruebas local)"

PACKS = {
    "better-mc-neoforge-bmc5": "https://cdn.modrinth.com/data/B37WQ89b/versions/Mo8ro6Ra/Better%20MC%20%5BNEOFORGE%5D%20BMC5%20v31.mrpack",
    "technical-electrical": "https://cdn.modrinth.com/data/PmwWNPV6/versions/mkpGUYy6/Technical%20Electrical%20Temporal%20Totality-26.1.8.mrpack",
    "supernova-empires-2": "https://cdn.modrinth.com/data/Or9UFKR8/versions/ndm0obMO/Supernova%20Empires%202%207.0.3.mrpack",
    "prominence-2-fabric": "https://cdn.modrinth.com/data/EGs3lC8D/versions/ga7DDH29/Prominence%E2%84%A2%20II%20Hasturian%20Era%20v4.1.6.mrpack",
    # Licencia libre (MIT o GPL), elegidos para cubrir 1.7.10, 1.12.2, Forge 1.19.2 y Forge 1.20.1.
    "heroes-1-7-10": "https://cdn.modrinth.com/data/NX36rCuV/versions/kSbNmDiW/Heroes%201.0.0.mrpack",
    "chaseters-spoopy-1-12-2": "https://cdn.modrinth.com/data/V5Po0cpt/versions/Ud6pjxUz/Chaseter%27s%20Spoopy%20Modpack%201.0.0.mrpack",
    "fundino-forge-1-20-1": "https://cdn.modrinth.com/data/AlEkX559/versions/iVJ2tGVM/FunDinoModpack%20Forge%201.20.1%203.1.0.mrpack",
    "horrors-in-the-fog-1-19-2": "https://cdn.modrinth.com/data/uPkIzDYf/versions/e5sVUHuu/the%20horrors%20in%20the%20fog%20%281.19.2%29%201.1.9.mrpack",
}

#: Qué se baja de cada pack (rutas dentro del .mrpack).
EXACTOS = {"modrinth.index.json", "overrides/options.txt"}
PREFIJOS = (
    "overrides/config/ftbquests/",
    "overrides/config/betterquesting/",
    "overrides/config/hqm/",
    "overrides/config/heracles/",
    "overrides/config/odyssey/",
    "overrides/config/questlog/",
    "overrides/kubejs/client_scripts/",
    "overrides/kubejs/server_scripts/",
    "overrides/kubejs/startup_scripts/",
    "overrides/patchouli_books/",
)
EXTENSIONES_KUBEJS_ASSETS = ("/lang/",)  # de kubejs/assets solo los idiomas
LIMITE_POR_PACK = 40 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Entrada:
    nombre: str
    metodo: int
    comprimido: int
    desplazamiento: int


def _rango(url: str, inicio: int, fin: int) -> bytes:
    req = urllib.request.Request(url, headers={"Range": f"bytes={inicio}-{fin}", "User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=120) as r:
        if r.status != 206:
            raise RuntimeError(f"El servidor no aceptó la descarga parcial (HTTP {r.status})")
        return r.read()


def tamano(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


def directorio_central(url: str, tamano: int) -> list[Entrada]:
    cola = _rango(url, max(0, tamano - 65_557), tamano - 1)
    pos = cola.rfind(b"PK\x05\x06")
    if pos < 0:
        raise RuntimeError("No encontré el final del zip")
    _, _, _, _, total, tam_cd, ini_cd, _ = struct.unpack("<IHHHHIIH", cola[pos : pos + 22])
    if ini_cd == 0xFFFFFFFF or total == 0xFFFF:  # ZIP64
        loc = cola.rfind(b"PK\x06\x07")
        (ini_eocd64,) = struct.unpack("<Q", cola[loc + 8 : loc + 16])
        eocd64 = _rango(url, ini_eocd64, ini_eocd64 + 55)
        total, tam_cd, ini_cd = struct.unpack("<QQQ", eocd64[32:56])
    cd = _rango(url, ini_cd, ini_cd + tam_cd - 1)
    entradas: list[Entrada] = []
    i = 0
    for _ in range(total):
        (firma, _, _, _, metodo, _, _, _, comp, _, ln, le, lc, _, _, _, desp) = struct.unpack(
            "<IHHHHHHIIIHHHHHII", cd[i : i + 46]
        )
        if firma != 0x02014B50:
            raise RuntimeError("Directorio central dañado")
        nombre = cd[i + 46 : i + 46 + ln].decode("utf-8", errors="replace")
        extra = cd[i + 46 + ln : i + 46 + ln + le]
        if comp == 0xFFFFFFFF or desp == 0xFFFFFFFF:
            j = 0
            while j < len(extra):
                ident, largo = struct.unpack("<HH", extra[j : j + 4])
                if ident == 1:
                    valores = list(struct.unpack(f"<{largo // 8}Q", extra[j + 4 : j + 4 + largo]))
                    if comp == 0xFFFFFFFF:
                        valores.pop(0)  # tamaño sin comprimir
                        comp = valores.pop(0)
                    if desp == 0xFFFFFFFF:
                        desp = valores.pop(0)
                j += 4 + largo
        entradas.append(Entrada(nombre, metodo, comp, desp))
        i += 46 + ln + le + lc
    return entradas


def _elegida(nombre: str) -> bool:
    if nombre.endswith("/"):
        return False
    if nombre in EXACTOS or nombre.startswith(PREFIJOS):
        return True
    return nombre.startswith("overrides/kubejs/assets/") and any(x in nombre for x in EXTENSIONES_KUBEJS_ASSETS)


def bajar(url: str, e: Entrada) -> bytes:
    cabecera = _rango(url, e.desplazamiento, e.desplazamiento + 29)
    ln, le = struct.unpack("<HH", cabecera[26:30])
    inicio = e.desplazamiento + 30 + ln + le
    datos = _rango(url, inicio, inicio + e.comprimido - 1) if e.comprimido else b""
    if e.metodo == 0:
        return datos
    if e.metodo == 8:
        return zlib.decompress(datos, -15)
    raise RuntimeError(f"Compresión no soportada ({e.metodo}) en {e.nombre}")


def bajar_pack(slug: str, url: str) -> None:
    destino = RAIZ / slug
    entradas = [e for e in directorio_central(url, tamano(url)) if _elegida(e.nombre)]
    total = sum(e.comprimido for e in entradas)
    print(f"{slug}: {len(entradas)} archivos, {total / 1e6:.1f} MB comprimidos")
    if total > LIMITE_POR_PACK:
        raise RuntimeError(f"{slug} pide más de {LIMITE_POR_PACK // 1_000_000} MB: no se baja")
    for e in entradas:
        relativa = e.nombre.removeprefix("overrides/")
        if ".." in relativa.split("/"):
            continue
        ruta = destino / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(bajar(url, e))
    indice: Any = json.loads((destino / "modrinth.index.json").read_text(encoding="utf-8"))
    deps = indice.get("dependencies", {})
    mods = [f["path"] for f in indice.get("files", []) if str(f.get("path", "")).startswith("mods/")]
    (destino / "resumen.json").write_text(
        json.dumps({"dependencias": deps, "mods": sorted(mods)}, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"   {deps} · {len(mods)} mods en el índice")


def main() -> int:
    elegidos = sys.argv[1:] or list(PACKS)
    for slug in elegidos:
        bajar_pack(slug, PACKS[slug])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

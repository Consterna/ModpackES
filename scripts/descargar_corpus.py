"""Baja SOLO las partes útiles (índice, configs de misiones, KubeJS) de modpacks públicos de Modrinth.

Usa peticiones HTTP por rangos: lee el directorio central del .mrpack y después solo los archivos elegidos,
sin descargar el pack entero. Lo deja en .descargas/<slug>/ (excluido de git) para las pruebas.

Uso:  uv run python scripts/descargar_corpus.py
"""

from __future__ import annotations

import json
import struct
import sys
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent / ".descargas"
AGENTE = "ModpackES/2.0 (corpus de pruebas local)"

PACKS = {
    "better-mc-neoforge-bmc5": "https://cdn.modrinth.com/data/B37WQ89b/versions/Mo8ro6Ra/Better%20MC%20%5BNEOFORGE%5D%20BMC5%20v31.mrpack",
    "technical-electrical": "https://cdn.modrinth.com/data/PmwWNPV6/versions/mkpGUYy6/Technical%20Electrical%20Temporal%20Totality-26.1.8.mrpack",
    "supernova-empires-2": "https://cdn.modrinth.com/data/Or9UFKR8/versions/ndm0obMO/Supernova%20Empires%202%207.0.3.mrpack",
    "prominence-2-fabric": "https://cdn.modrinth.com/data/EGs3lC8D/versions/ga7DDH29/Prominence%E2%84%A2%20II%20Hasturian%20Era%20v4.1.6.mrpack",
    # Packs con datapacks, funciones, logros y scripts propios (para probar los datos de texto). Elegidos
    # mirando el índice del .mrpack: el contenido de cada uno está en el comentario.
    # 1.20.1 fabric · funciones, logros, datapacks .zip
    "animatecraft-lankeren": "https://cdn.modrinth.com/data/rqoNUSYX/versions/iRG9ktbA/Lankeren%201.1.5-fixed.mrpack",
    # 1.20.1 neoforge · kubejs y kubejs/data
    "slimecrew": "https://cdn.modrinth.com/data/u3eBhKdv/versions/VHuCfVgS/SlimeCrew%20Frontier%201.3.0.mrpack",
    # 1.20.1 forge · kubejs/data
    "omnicraft-modpack": "https://cdn.modrinth.com/data/hcyfOf6Q/versions/Zh2npQSZ/Omnicraft%202.0.mrpack",
    # 1.20.1 forge · kubejs y kubejs/data
    "stormforge": "https://cdn.modrinth.com/data/Mclf6Juw/versions/Q1Znj0cU/Stormforge%202.1.7.mrpack",
    # 1.21.1 neoforge · kubejs
    "create-cobblemon-season-1": "https://cdn.modrinth.com/data/Mo3YEbmr/versions/KFjm9wO7/Create%20Cobblemon%20Season%201%201.0.2.mrpack",
    # 1.20.1 fabric · logros, datapacks .zip
    "prominence-2-chinese": "https://cdn.modrinth.com/data/2Vp3Sdd5/versions/ttpetMlI/Prominence%20II%20Hasturian%20Era%20CN%203.9.2.mrpack",
    # 1.20.1 forge · funciones
    "battlearmorytacz": "https://cdn.modrinth.com/data/rQiXwLhB/versions/TX0XBjIG/BattleArmory%20TACZ%2026.0.5.mrpack",
    # 1.20.1 forge · datapacks .zip
    "better-mc-forge-bmc4": "https://cdn.modrinth.com/data/4BV47HRn/versions/bdRIjRgs/Better%20MC%20%5BFORGE%5D%201.20.1%201.20.1%20v59.mrpack",
    # 1.20.1 fabric · kubejs, datapacks .zip
    "landscapes-reimagined-genesis": "https://cdn.modrinth.com/data/MdznSbKA/versions/pBrfi38A/Landscapes%20Reimagined%20Genesis%203.2.mrpack",
    # Más versiones y loaders (1.16.5, 1.18.2, 1.19.2 Quilt, 1.20.1, 1.21.11 y 26.x): SNBT y formatos viejos
    # 1.19.2 quilt · kubejs 171 / data 1297 / funciones 9 / logros 130 / zips 0
    "taidumcraft": "https://cdn.modrinth.com/data/qH6Phyax/versions/dmDeTjMb/TaidumCraft.mrpack",
    # 26.1.2 fabric · kubejs 0 / data 0 / funciones 5 / logros 176 / zips 0
    "legacies": "https://cdn.modrinth.com/data/nWCaRO9f/versions/x4WpILDH/Legacies%2026-v4.1.mrpack",
    # 1.16.5 forge · kubejs 125 / data 5 / funciones 0 / logros 0 / zips 0
    "techblock-skytech-3": "https://cdn.modrinth.com/data/jRXzxVGA/versions/IHN5lWsY/TechBlock%20-%20SkyTech%203%201.2.1.mrpack",
    # 1.18.2 forge · kubejs 7 / data 0 / funciones 0 / logros 0 / zips 0
    "adventures-of-berk": "https://cdn.modrinth.com/data/zTK0MLqP/versions/yIog8kuK/Adventures%20of%20Berk%200.0.1.mrpack",
    # 1.20.1 fabric · kubejs 3 / data 258 / funciones 0 / logros 123 / zips 0
    "spectral-creation": "https://cdn.modrinth.com/data/eqbP6Ycz/versions/iJhfeFZL/Spectral%20Creation%201.20.1-7.1.1.mrpack",
    # 1.18.2 forge · kubejs 0 / data 0 / funciones 0 / logros 0 / zips 16
    "kings-dragons-of-berk": "https://cdn.modrinth.com/data/UmIII5vC/versions/b82038X3/Kings_dragon%201.0.0.mrpack",
    # 1.21.11 fabric · kubejs 0 / data 0 / funciones 0 / logros 0 / zips 6
    "better-adventures-plus-plus": "https://cdn.modrinth.com/data/23niDfW7/versions/e18PwvTU/Better%20Adventures%2B%2B%201.3.mrpack",
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
    # Datos de texto que ve el jugador: funciones, logros y datapacks, vengan de donde vengan
    "overrides/kubejs/data/",
    "overrides/global_packs/",
    "overrides/datapacks/",
    "overrides/config/openloader/",
    "overrides/config/paxi/",
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


def _tamano(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


def _directorio_central(url: str, tamano: int) -> list[Entrada]:
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
    if nombre.startswith(("overrides/kubejs/assets/", "overrides/resourcepacks/")) and nombre.endswith(".json"):
        return any(x in nombre for x in (*EXTENSIONES_KUBEJS_ASSETS, "/tips/"))
    return False


def _bajar(url: str, e: Entrada) -> bytes:
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
    entradas = [e for e in _directorio_central(url, _tamano(url)) if _elegida(e.nombre)]
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
        ruta.write_bytes(_bajar(url, e))
    indice: Any = json.loads((destino / "modrinth.index.json").read_text(encoding="utf-8"))
    deps = indice.get("dependencies", {})
    mods = [f["path"] for f in indice.get("files", []) if str(f.get("path", "")).startswith("mods/")]
    (destino / "resumen.json").write_text(
        json.dumps({"dependencias": deps, "mods": sorted(mods)}, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"   {deps} · {len(mods)} mods en el índice")


def main() -> int:
    elegidos = sys.argv[1:] or list(PACKS)
    fallos = 0
    for slug in elegidos:
        try:
            bajar_pack(slug, PACKS[slug])
        except (RuntimeError, OSError) as e:  # un pack que no se puede bajar no detiene a los demás
            print(f"{slug}: no se bajó ({e})")
            fallos += 1
    return 1 if fallos == len(elegidos) else 0


if __name__ == "__main__":
    raise SystemExit(main())

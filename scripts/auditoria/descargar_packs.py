"""Corpus completo para la auditoría de cobertura: modpacks enteros (con todos sus mods) listos para la app.

A diferencia de `scripts/descargar_corpus.py`, que baja solo las carpetas que la app ya conoce, este baja el pack
entero: el `.mrpack` o la versión de FTB y cada archivo de su índice (verificado con su hash). Así el inventario de la
auditoría ve también lo que la app no busca. Cada pack queda como una instancia de Prism que la app reconoce:

    <corpus>/<fuente>-<slug>/mmc-pack.json      versión de Minecraft y loader
    <corpus>/<fuente>-<slug>/minecraft/…        mods/, config/, kubejs/, resourcepacks/…
    <corpus>/<fuente>-<slug>/_estado.json       qué se bajó, qué faltó y por qué

Lo descargado es un dato: no se ejecuta ni se descomprime nada salvo los `overrides` del propio pack, con rutas
comprobadas. El corpus no se publica (ver docs/datos-de-terceros.md).

Uso:
    uv run python scripts/auditoria/descargar_packs.py buscar --por-version 6 > candidatos.json
    uv run python scripts/auditoria/descargar_packs.py bajar modrinth:prominence-2-fabric ftb:125
    uv run python scripts/auditoria/descargar_packs.py bajar --lista seleccion.txt
    uv run python scripts/auditoria/descargar_packs.py estado
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, cast

AGENTE = "ModpackES/2.0 (corpus de pruebas local)"
CORPUS = Path(os.environ.get("MODPACKES_CORPUS", r"C:\dev\corpus-modpacks"))
MODRINTH = "https://api.modrinth.com/v2"
FTB = "https://api.feed-the-beast.com/v1/modpacks/public/modpack"
#: Sitios de los que un pack puede pedir archivos: los del formato .mrpack, más el CDN de CurseForge que usa FTB.
SITIOS = frozenset({
    "cdn.modrinth.com", "github.com", "raw.githubusercontent.com", "gitlab.com",
    "edge.forgecdn.net", "mediafilez.forgecdn.net", "dist.creeper.host",
    "files.feed-the-beast.com", "cdn.feed-the-beast.com",
})  # fmt: skip
#: Topes de disco (GB): no se baja nada si quedan menos libres o si el corpus ya ocupa más.
LIBRE_MINIMO_GB = 50
CORPUS_MAXIMO_GB = 150
UIDS = {
    "minecraft": "net.minecraft",
    "forge": "net.minecraftforge",
    "neoforge": "net.neoforged",
    "fabric-loader": "net.fabricmc.fabric-loader",
    "quilt-loader": "org.quiltmc.quilt-loader",
}
VERSIONES = ("1.7.10", "1.12.2", "1.16.5", "1.18.2", "1.19.2", "1.20.1", "1.21.1")
LOADERS = ("forge", "neoforge", "fabric", "quilt")


@dataclass(slots=True)
class Archivo:
    ruta: str  #: relativa a la carpeta del juego, con «/»
    urls: list[str]
    tamano: int
    hashes: dict[str, str]  #: «sha512» o «sha1»


@dataclass(slots=True)
class Pack:
    clave: str  #: «modrinth-<slug>» o «ftb-<id>»
    nombre: str
    version: str
    dependencias: dict[str, str]  #: «minecraft», «forge», «fabric-loader»…
    archivos: list[Archivo]
    overrides: bytes | None = None  #: el .mrpack (sus carpetas overrides/), o None
    faltantes: list[dict[str, str]] = field(default_factory=lambda: [])


# ------------------------------------------------------------------------- red


def _pedir(url: str, intentos: int = 4) -> bytes:
    """GET con reintentos. Solo https y solo los sitios permitidos (o las API de Modrinth y FTB)."""
    partes = urllib.parse.urlparse(url)
    if partes.scheme != "https" or partes.hostname not in SITIOS | {"api.modrinth.com", "api.feed-the-beast.com"}:
        raise ValueError(f"sitio no permitido: {url}")
    # Algunas URL traen espacios u otros caracteres sin codificar («Binnie Patcher 1.8.jar»)
    url = partes._replace(path=urllib.parse.quote(partes.path, safe="/%+@!$&'()*,;=:~-._")).geturl()
    ultimo: Exception | None = None
    for intento in range(intentos):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(pedido, timeout=120) as respuesta:  # https y sitio comprobados arriba
                return cast(bytes, respuesta.read())
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                raise
            ultimo = e
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "10")))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            ultimo = e
        time.sleep(2 * (intento + 1))
    raise RuntimeError(f"no se pudo bajar {url}: {ultimo}")


def _json(url: str) -> Any:
    return json.loads(_pedir(url))


# ---------------------------------------------------------------------- rutas


def ruta_segura(base: Path, relativa: str) -> Path:
    """`base/relativa` si queda dentro de `base`; si no (`..`, absoluta, unidad), ValueError."""
    limpia = relativa.replace("\\", "/")
    while limpia.startswith("./"):
        limpia = limpia[2:]
    p = PurePosixPath(limpia)
    if not limpia or p.is_absolute() or ".." in p.parts or ":" in limpia:
        raise ValueError(f"ruta peligrosa: {relativa!r}")
    destino = (base / Path(*p.parts)).resolve()
    if not destino.is_relative_to(base.resolve()):
        raise ValueError(f"ruta peligrosa: {relativa!r}")
    return destino


def _tamano_gb(carpeta: Path) -> float:
    return sum(f.stat().st_size for f in carpeta.rglob("*") if f.is_file()) / 1e9 if carpeta.exists() else 0.0


def comprobar_disco(corpus: Path) -> None:
    libre = shutil.disk_usage(corpus if corpus.exists() else corpus.anchor).free / 1e9
    if libre < LIBRE_MINIMO_GB:
        raise SystemExit(f"Quedan {libre:.0f} GB libres (mínimo {LIBRE_MINIMO_GB}): no se baja más.")
    if (usado := _tamano_gb(corpus)) > CORPUS_MAXIMO_GB:
        raise SystemExit(f"El corpus ya ocupa {usado:.0f} GB (tope {CORPUS_MAXIMO_GB}): no se baja más.")


# ------------------------------------------------------------------- fuentes


def pack_de_modrinth(slug: str, version: str | None = None) -> Pack:
    """El .mrpack de una versión (la más nueva si no se dice) y los archivos de su índice."""
    if version:
        datos = _json(f"{MODRINTH}/project/{slug}/version/{version}")
    else:
        versiones = cast(list[dict[str, Any]], _json(f"{MODRINTH}/project/{slug}/version"))
        if not versiones:
            raise ValueError(f"{slug} no tiene versiones")
        datos = versiones[0]
    archivos = cast(list[dict[str, Any]], datos["files"])
    principal = next((a for a in archivos if a.get("primary")), archivos[0])
    mrpack = _pedir(str(principal["url"]))
    with zipfile.ZipFile(io.BytesIO(mrpack)) as z:
        indice = cast(dict[str, Any], json.loads(z.read("modrinth.index.json").decode("utf-8")))
    lista: list[Archivo] = []
    for f in cast(list[dict[str, Any]], indice.get("files", [])):
        entorno = cast(dict[str, str], f.get("env") or {})
        if entorno.get("client") == "unsupported":  # solo servidor: el jugador no lo ve
            continue
        lista.append(Archivo(str(f["path"]), [str(u) for u in f.get("downloads", [])], int(f.get("fileSize", 0)),
                             {k: str(v) for k, v in cast(dict[str, Any], f.get("hashes", {})).items()}))  # fmt: skip
    return Pack(f"modrinth-{slug}", str(indice.get("name", slug)), str(indice.get("versionId", datos["id"])),
                {str(k): str(v) for k, v in cast(dict[str, Any], indice.get("dependencies", {})).items()},
                lista, overrides=mrpack)  # fmt: skip


def pack_de_ftb(ident: int, version: int | None = None) -> Pack:
    """Una versión de un pack de FTB (la más nueva si no se dice). Los archivos sin url (de CurseForge) faltan."""
    datos = cast(dict[str, Any], _json(f"{FTB}/{ident}"))
    versiones = cast(list[dict[str, Any]], datos.get("versions", []))
    if version is None:
        publicas = [v for v in versiones if v.get("type") == "release" and not v.get("private")] or versiones
        version = int(max(publicas, key=lambda v: int(v.get("released", 0)))["id"])
    detalle = cast(dict[str, Any], _json(f"{FTB}/{ident}/{version}"))
    deps: dict[str, str] = {}
    for t in cast(list[dict[str, Any]], detalle.get("targets", [])):
        nombre = str(t.get("name"))
        if nombre == "minecraft":
            deps["minecraft"] = str(t.get("version"))
        elif nombre in ("forge", "neoforge"):
            deps[nombre] = str(t.get("version"))
        elif nombre in ("fabric", "quilt"):
            deps[f"{nombre}-loader"] = str(t.get("version"))
    pack = Pack(f"ftb-{ident}", str(datos.get("name", ident)), str(detalle.get("name", version)), deps, [])
    for f in cast(list[dict[str, Any]], detalle.get("files", [])):
        if f.get("serveronly"):
            continue
        ruta = f"{str(f.get('path', './')).rstrip('/')}/{f.get('name')}"
        hashes = {k: str(v) for k, v in cast(dict[str, Any], f.get("hashes") or {}).items() if k in ("sha1", "sha512")}
        if not hashes and f.get("sha1"):
            hashes = {"sha1": str(f["sha1"])}
        if not f.get("url"):
            pack.faltantes.append({"ruta": ruta, "motivo": "sin url (CurseForge sin permiso de distribución)"})
            continue
        pack.archivos.append(Archivo(ruta, [str(f["url"])], int(f.get("size", 0)), hashes))
    return pack


# --------------------------------------------------------------- descargar


def _hash_correcto(datos: bytes, hashes: dict[str, str]) -> bool:
    if "sha512" in hashes:
        return hashlib.sha512(datos).hexdigest() == hashes["sha512"].lower()
    if "sha1" in hashes:
        return hashlib.sha1(datos, usedforsecurity=False).hexdigest() == hashes["sha1"].lower()
    return False  # sin hash no se acepta


def _ya_esta(destino: Path, a: Archivo) -> bool:
    return destino.is_file() and (a.tamano == 0 or destino.stat().st_size == a.tamano) \
        and _hash_correcto(destino.read_bytes(), a.hashes)  # fmt: skip


def _bajar_archivo(juego: Path, a: Archivo) -> dict[str, str] | None:
    """Baja un archivo y lo verifica. Devuelve el motivo si falló, o None."""
    try:
        destino = ruta_segura(juego, a.ruta)
    except ValueError as e:
        return {"ruta": a.ruta, "motivo": str(e)}
    if _ya_esta(destino, a):
        return None
    errores: list[str] = []
    for url in a.urls:
        if urllib.parse.urlparse(url).hostname not in SITIOS:
            errores.append(f"sitio no permitido: {url}")
            continue
        try:
            datos = _pedir(url)
        except Exception as e:  # un archivo que falla se anota; no tumba el pack entero
            errores.append(f"{type(e).__name__}: {e}")
            continue
        if not _hash_correcto(datos, a.hashes):
            errores.append(f"hash distinto: {url}")
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_name(destino.name + ".parcial")
        temporal.write_bytes(datos)
        temporal.replace(destino)
        return None
    return {"ruta": a.ruta, "motivo": "; ".join(errores) or "sin urls"}


def _copiar_overrides(mrpack: bytes, juego: Path) -> int:
    """Copia `overrides/` y después `client-overrides/` (que manda) en la carpeta del juego. Devuelve cuántos."""
    copiados = 0
    with zipfile.ZipFile(io.BytesIO(mrpack)) as z:
        for prefijo in ("overrides/", "client-overrides/"):
            for info in z.infolist():
                if info.is_dir() or not info.filename.startswith(prefijo):
                    continue
                destino = ruta_segura(juego, info.filename[len(prefijo) :])
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(z.read(info))
                copiados += 1
    return copiados


def escribir_mmc_pack(carpeta: Path, dependencias: dict[str, str]) -> None:
    """El `mmc-pack.json` de Prism con la versión del juego y el loader, que es de donde la app los lee primero."""
    componentes = [{"uid": UIDS[k], "version": v} for k, v in dependencias.items() if k in UIDS]
    (carpeta / "mmc-pack.json").write_text(json.dumps({"components": componentes, "formatVersion": 1}, indent=2),
                                           encoding="utf-8")  # fmt: skip


def bajar_pack(pack: Pack, corpus: Path, hilos: int = 8) -> dict[str, Any]:
    comprobar_disco(corpus)
    carpeta = corpus / pack.clave
    juego = carpeta / "minecraft"
    juego.mkdir(parents=True, exist_ok=True)
    escribir_mmc_pack(carpeta, pack.dependencias)
    copiados = _copiar_overrides(pack.overrides, juego) if pack.overrides else 0
    with ThreadPoolExecutor(max_workers=hilos) as ejecutor:
        fallos = [r for r in ejecutor.map(_bajar_archivo, [juego] * len(pack.archivos), pack.archivos) if r]
    estado: dict[str, Any] = {
        "clave": pack.clave,
        "nombre": pack.nombre,
        "version": pack.version,
        "dependencias": pack.dependencias,
        "archivos_indice": len(pack.archivos),
        "overrides": copiados,
        "fallidos": fallos,
        "faltantes": pack.faltantes,
        "gb": round(_tamano_gb(carpeta), 3),
        "fecha": time.strftime("%Y-%m-%d %H:%M"),
    }
    (carpeta / "_estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    return estado


def resolver(texto: str) -> Pack:
    """«modrinth:slug[@versión]» o «ftb:id[@versión]»."""
    fuente, _, resto = texto.partition(":")
    nombre, _, version = resto.partition("@")
    if fuente == "modrinth" and nombre:
        return pack_de_modrinth(nombre, version or None)
    if fuente == "ftb" and nombre.isdigit():
        return pack_de_ftb(int(nombre), int(version) if version.isdigit() else None)
    raise ValueError(f"no entiendo «{texto}»: usa modrinth:slug[@versión] o ftb:id[@versión]")


# --------------------------------------------------------------------- buscar


#: Categorías de Modrinth sin texto propio que valga la pena auditar (packs de rendimiento).
SIN_CONTENIDO = ("optimization", "lightweight")


def buscar(
    por_version: int, versiones: Iterable[str], loaders: Iterable[str], categoria: str | None = None
) -> list[dict[str, Any]]:
    """Los packs de contenido más descargados de Modrinth de cada versión y loader (sin repetir)."""
    vistos: set[str] = set()
    salida: list[dict[str, Any]] = []
    for version in versiones:
        for loader in loaders:
            grupos = [["project_type:modpack"], [f"versions:{version}"], [f"categories:{loader}"]]
            grupos += [[f"categories!={c}"] for c in SIN_CONTENIDO]
            if categoria:
                grupos.append([f"categories:{categoria}"])
            facetas = json.dumps(grupos)
            consulta = urllib.parse.urlencode({"facets": facetas, "index": "downloads", "limit": por_version})
            for h in cast(list[dict[str, Any]], _json(f"{MODRINTH}/search?{consulta}").get("hits", [])):
                if (slug := str(h["slug"])) in vistos:
                    continue
                vistos.add(slug)
                salida.append({"pack": f"modrinth:{slug}", "titulo": h.get("title"), "version": version,
                               "loader": loader, "descargas": h.get("downloads")})  # fmt: skip
    return salida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    sub = ap.add_subparsers(dest="orden", required=True)
    b = sub.add_parser("buscar", help="candidatos de Modrinth por versión y loader (JSON a la salida)")
    b.add_argument("--por-version", type=int, default=5)
    b.add_argument("--versiones", nargs="*", default=list(VERSIONES))
    b.add_argument("--loaders", nargs="*", default=list(LOADERS))
    b.add_argument("--categoria", help="solo packs de esta categoría de Modrinth (quests, adventure, technology…)")
    b.add_argument("--salida", type=Path, help="archivo JSON (UTF-8); sin esto, a la salida estándar")
    d = sub.add_parser("bajar", help="bajar packs completos")
    d.add_argument("packs", nargs="*")
    d.add_argument("--lista", type=Path, help="archivo con un pack por línea (# comenta)")
    d.add_argument("--hilos", type=int, default=8)
    sub.add_parser("estado", help="resumen de lo bajado")
    args = ap.parse_args()
    corpus: Path = args.corpus
    if args.orden == "buscar":
        hallados = buscar(args.por_version, args.versiones, args.loaders, args.categoria)
        texto = json.dumps(hallados, ensure_ascii=False, indent=2)
        if args.salida:
            args.salida.write_text(texto, encoding="utf-8")
        else:
            sys.stdout.buffer.write(texto.encode("utf-8"))
        return 0
    if args.orden == "estado":
        for e in sorted(corpus.glob("*/_estado.json")):
            d_ = cast(dict[str, Any], json.loads(e.read_text(encoding="utf-8")))
            deps = d_["dependencias"]
            print(f"{d_['clave']:<45} {deps.get('minecraft', '?'):<8} {d_['gb']:>7.2f} GB  "
                  f"{d_['archivos_indice']:>4} archivos  {len(d_['fallidos'])} fallidos  "
                  f"{len(d_['faltantes'])} faltantes")  # fmt: skip
        print(f"Total: {_tamano_gb(corpus):.1f} GB")
        return 0
    pedidos: list[str] = list(args.packs)
    if args.lista:
        pedidos += [ln.split("#")[0].strip() for ln in args.lista.read_text(encoding="utf-8").splitlines()]
    errores = 0
    for texto in (p for p in pedidos if p):
        try:
            estado = bajar_pack(resolver(texto), corpus, args.hilos)
        except SystemExit:
            raise  # tope de disco
        except Exception as e:  # un pack que falla se informa y se sigue con el siguiente
            errores += 1
            print(f"✗ {texto}: {type(e).__name__}: {e}", flush=True)
            continue
        print(f"✓ {texto}: {estado['gb']} GB, {estado['archivos_indice']} archivos, "
              f"{len(estado['fallidos'])} fallidos, {len(estado['faltantes'])} faltantes", flush=True)  # fmt: skip
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Completa la caché de un Prism Launcher portátil cuando la red corta las descargas grandes.

Lee la metadata que Prism ya bajó (`meta/<uid>/<versión>.json`) y, para cada librería que falta en `libraries/` (o que
no coincide con su sha1), la baja con paciencia: tiempo de espera largo, varios intentos y reanudación por rangos. Si
el DNS del sistema no resuelve un host, usa la IP de `.herramientas/hosts-java.txt` con el nombre del host para TLS
(el certificado se sigue verificando). No toca el DNS ni el archivo hosts del sistema.

Uso:
    uv run python scripts/auditoria/completar_prism.py RAIZ_DE_PRISM net.neoforged/21.1.250 net.minecraft/1.21.1
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import socket
import ssl
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, cast

HOSTS = Path(r"C:\dev\proyectos\traducir-modpacks\.herramientas\hosts-java.txt")
AGENTE = "ModpackES/2.0 (corpus de pruebas local)"


def _ips() -> dict[str, list[str]]:
    salida: dict[str, list[str]] = {}
    if HOSTS.is_file():
        for linea in HOSTS.read_text(encoding="utf-8").splitlines():
            partes = linea.split()
            if len(partes) == 2:
                salida.setdefault(partes[1], []).append(partes[0])
    return salida


class _Conexion(http.client.HTTPSConnection):
    """HTTPS a una IP fija, con el nombre del host para SNI y para verificar el certificado."""

    def __init__(self, host: str, ip: str, timeout: float) -> None:
        self._contexto = ssl.create_default_context()
        super().__init__(host, timeout=timeout, context=self._contexto)
        self._ip = ip

    def connect(self) -> None:
        crudo = socket.create_connection((self._ip, self.port or 443), self.timeout)
        self.sock = self._contexto.wrap_socket(crudo, server_hostname=self.host)


def _bajar(url: str, destino: Path, sha1: str | None, intentos: int = 8) -> bool:
    partes = urllib.parse.urlparse(url)
    host = partes.hostname or ""
    ruta = partes.path + (f"?{partes.query}" if partes.query else "")
    ips = [None, *_ips().get(host, [])]
    temporal = destino.with_name(destino.name + ".parcial")
    destino.parent.mkdir(parents=True, exist_ok=True)
    for intento in range(intentos):
        ip = ips[intento % len(ips)]
        ya = temporal.stat().st_size if temporal.exists() else 0
        try:
            conexion = _Conexion(host, ip, 60) if ip else http.client.HTTPSConnection(host, timeout=60)
            cabeceras = {"User-Agent": AGENTE, **({"Range": f"bytes={ya}-"} if ya else {})}
            conexion.request("GET", ruta, headers=cabeceras)
            r = conexion.getresponse()
            if r.status not in (200, 206):
                print(f"  {r.status} en {url}", flush=True)
                time.sleep(3)
                continue
            modo = "ab" if r.status == 206 else "wb"
            with temporal.open(modo) as f:
                while bloque := r.read(1 << 16):
                    f.write(bloque)
            conexion.close()
        except (OSError, http.client.HTTPException) as e:
            print(f"  intento {intento + 1} ({'IP ' + ip if ip else 'DNS'}): {type(e).__name__} {e}", flush=True)
            time.sleep(3)
            continue
        datos = temporal.read_bytes()
        if sha1 and hashlib.sha1(datos, usedforsecurity=False).hexdigest() != sha1:
            print(f"  sha1 distinto, de nuevo: {url}", flush=True)
            temporal.unlink()
            continue
        temporal.replace(destino)
        return True
    return False


def _artefactos(meta: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    """(url, ruta en libraries/, sha1) de cada librería de una metadata de Prism (incluidas las nativas)."""
    salida: list[tuple[str, str, str | None]] = []
    for lib in cast(list[dict[str, Any]], [*meta.get("libraries", []), *meta.get("mavenFiles", []),
                                           *([meta["mainJar"]] if "mainJar" in meta else [])]):  # fmt: skip
        descargas = cast(dict[str, Any], lib.get("downloads", {}))
        candidatos: list[object] = [
            descargas.get("artifact"),
            *cast(dict[str, Any], descargas.get("classifiers", {})).values(),
        ]
        for art in candidatos:
            if not isinstance(art, dict):
                continue
            a = cast(dict[str, Any], art)
            if a.get("url"):
                ruta = a.get("path") or _ruta_maven(str(lib.get("name", "")), str(a["url"]))
                sha1 = a.get("sha1")
                salida.append((str(a["url"]), str(ruta), str(sha1) if sha1 else None))
    return salida


def _ruta_maven(nombre: str, url: str) -> str:
    grupo, artefacto, version, *clasificador = nombre.split(":")
    extra = f"-{clasificador[0]}" if clasificador else ""
    extension = url.rsplit(".", 1)[-1]
    return f"{grupo.replace('.', '/')}/{artefacto}/{version}/{artefacto}-{version}{extra}.{extension}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prism", type=Path)
    ap.add_argument("componentes", nargs="+", help="uid/versión, p. ej. net.neoforged/21.1.250")
    args = ap.parse_args()
    faltan = 0
    for comp in args.componentes:
        meta = json.loads((args.prism / "meta" / f"{comp}.json").read_text(encoding="utf-8"))
        for url, ruta, sha1 in _artefactos(meta):
            destino = args.prism / "libraries" / ruta
            if destino.is_file() and (
                not sha1 or hashlib.sha1(destino.read_bytes(), usedforsecurity=False).hexdigest() == sha1
            ):
                continue
            print(f"bajando {ruta}", flush=True)
            if not _bajar(url, destino, sha1):
                faltan += 1
                print(f"✗ no se pudo: {url}", flush=True)
    print("listo" if not faltan else f"faltan {faltan}", flush=True)
    return 1 if faltan else 0


if __name__ == "__main__":
    salida_estandar = cast(io.TextIOWrapper, sys.stdout)
    if hasattr(salida_estandar, "reconfigure"):
        salida_estandar.reconfigure(encoding="utf-8")
    raise SystemExit(main())

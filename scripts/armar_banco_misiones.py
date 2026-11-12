"""Arma un banco de misiones reales (solo inglés, sin referencias) con los packs del corpus (salida SOLO local).

Pasa las misiones de FTB Quests de .descargas/*/config/ftbquests por el módulo de misiones de la app, así que
cada texto trae la misma «pista» que recibiría el motor (título bajo el que está y línea anterior). No hay
traducciones humanas de misiones en el corpus: este banco se juzga comparando dos traducciones con
`scripts/preferencia_pareada.py`, no con chrF. Queda en .descargas/banco/misiones.json (de terceros: no va al repo).

Uso:  uv run python scripts/armar_banco_misiones.py [--textos 120]
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import descargar_corpus as dc

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, Pieza
from traductor_es.modulos.misiones import FTBQuests
from traductor_es.salida.copias import Respaldo

LOADERS = {"forge": "net.minecraftforge", "neoforge": "net.neoforged", "fabric-loader": "net.fabricmc.fabric-loader"}


def _instancia_falsa(base: Path, version: str, loader: str) -> Path:
    """Una carpeta con el aspecto de una instancia de Prism, para que la app lea las misiones como siempre."""
    carpeta = base / "Pack"
    juego = carpeta / "minecraft"
    (juego / "mods").mkdir(parents=True)
    (carpeta / "instance.cfg").write_text("name=Pack\n", encoding="utf-8")
    componentes = [{"uid": "net.minecraft", "version": version}, {"uid": LOADERS[loader], "version": "1.0"}]
    (carpeta / "mmc-pack.json").write_text(json.dumps({"components": componentes}), encoding="utf-8")
    return juego


def piezas_del_pack(pack: Path) -> list[Pieza]:
    resumen: dict[str, Any] = json.loads((pack / "resumen.json").read_text(encoding="utf-8"))
    deps: dict[str, str] = resumen["dependencias"]
    loader = next((k for k in LOADERS if k in deps), "forge")
    with tempfile.TemporaryDirectory() as tmp:
        juego = _instancia_falsa(Path(tmp), deps["minecraft"], loader)
        shutil.copytree(pack / "config" / "ftbquests", juego / "config" / "ftbquests")
        with Instancia(juego) as inst:
            modulo = FTBQuests(Contexto(inst, Respaldo(juego)))
            return modulo.recolectar() if modulo.detectar() else []


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--textos", type=int, default=120)
    args = ap.parse_args()
    por_pack: dict[str, list[Pieza]] = {}
    for pack in sorted(dc.RAIZ.iterdir()):
        if (pack / "config" / "ftbquests").is_dir() and (pack / "resumen.json").is_file():
            piezas = [p for p in piezas_del_pack(pack) if not p.pista.endswith("title") and len(p.texto.split()) >= 6]
            vistos: set[str] = set()
            por_pack[pack.name] = [p for p in piezas if not (p.texto in vistos or vistos.add(p.texto))]
            print(f"{pack.name}: {len(por_pack[pack.name])} descripciones")
    if not por_pack:
        print("No hay packs con misiones en el corpus (scripts/descargar_corpus.py).")
        return 1
    azar = random.Random(11)
    barajadas = {nombre: azar.sample(lista, len(lista)) for nombre, lista in por_pack.items()}
    elegidas: list[Pieza] = []
    while len(elegidas) < args.textos and any(barajadas.values()):  # un texto de cada pack por vuelta
        for lista in barajadas.values():
            if lista and len(elegidas) < args.textos:
                elegidas.append(lista.pop())
    banco: dict[str, Any] = {
        "descripcion": "Misiones reales de FTB Quests, sin referencias; solo uso local (no se publica).",
        "dialecto": "es_mx",
        "glosario": {},
        "textos": [{"ambito": "mision", "original": p.texto, "referencia": "", "pista": p.pista} for p in elegidas],
    }
    destino = dc.RAIZ / "banco" / "misiones.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(banco, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(elegidas)} textos en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

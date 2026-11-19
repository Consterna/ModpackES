"""Foto de lo que escribe la app en cada pack del corpus, con el motor simulado (gratis), y prueba de que restaurar deja
los bytes originales.

Es la mitad de la puerta de regresión que mira el corpus (la otra, `puerta_calidad.py`, mira los bancos de calidad):
- `--guardar`: para cada pack, traduce con `--simular`, guarda el hash de cada archivo que cambió o apareció y restaura.
- sin `--guardar`: hace lo mismo y compara con la foto. Un archivo que ya existía en la foto tiene que salir idéntico;
  los archivos nuevos se permiten (son fuentes nuevas) y se listan aparte.
En los dos casos comprueba que, después de `restaurar`, la instancia vuelve a ser byte por byte la del principio.

Uso:
    uv run python scripts/auditoria/foto_corpus.py --guardar [packs…]
    uv run python scripts/auditoria/foto_corpus.py [packs…]          # sale con 1 si algo cambió
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent.parent
CORPUS = Path(r"C:\dev\corpus-modpacks")
FOTOS = RAIZ / "build" / "base_corpus"
#: La app nunca toca los jars de mods: con su tamaño y fecha basta (leerlos todos tardaría minutos por pack).
SOLO_FECHA = (".jar",)
#: Lo que escribe la app y que restaurar no tiene por qué borrar (su índice, la marca, los informes).
PROPIO_DE_LA_APP = ("traductor_es/",)


def huellas(juego: Path) -> dict[str, str]:
    salida: dict[str, str] = {}
    for p in juego.rglob("*"):
        if not p.is_file():
            continue
        relativa = p.relative_to(juego).as_posix()
        if p.suffix.lower() in SOLO_FECHA and relativa.startswith("mods/"):
            e = p.stat()
            salida[relativa] = f"{e.st_size}:{e.st_mtime_ns}"
        else:
            salida[relativa] = hashlib.blake2b(p.read_bytes(), digest_size=16).hexdigest()
    return salida


#: Carpeta `src` del código de la app con que se traduce (otra copia, p. ej. la del commit base, para la foto «antes»).
CODIGO: list[Path] = []


def _modpackes(*args: str) -> None:
    orden = [sys.executable, "-m", "traductor_es", *args]
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if CODIGO:
        entorno["PYTHONPATH"] = str(CODIGO[0])  # va antes que la instalación editable de esta copia
    hecho = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           check=False, env=entorno)  # fmt: skip
    if hecho.returncode != 0:
        raise RuntimeError(f"modpackes {' '.join(args[:1])} falló:\n{hecho.stdout[-1500:]}\n{hecho.stderr[-1500:]}")


def juego_de(pack: Path) -> Path:
    return pack / "minecraft" if (pack / "minecraft").is_dir() else pack


def foto(pack: Path) -> dict[str, Any]:
    """Traduce con el simulador, anota lo que cambió, restaura y comprueba que todo volvió a su estado."""
    juego = juego_de(pack)
    antes = huellas(juego)
    _modpackes("traducir", str(pack), "--simular")
    despues = huellas(juego)
    escritos = {k: v for k, v in despues.items() if antes.get(k) != v}
    _modpackes("restaurar", str(pack))
    final = huellas(juego)
    distintos = sorted(
        k for k in set(antes) | set(final)
        if antes.get(k) != final.get(k) and not k.startswith(PROPIO_DE_LA_APP)
    )  # fmt: skip
    return {"pack": pack.name, "escritos": escritos, "no_restaurados": distintos}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packs", nargs="*", type=Path)
    ap.add_argument("--guardar", action="store_true")
    ap.add_argument("--codigo", type=Path, help="carpeta `src` de otra copia de la app (p. ej. la del commit base)")
    args = ap.parse_args()
    if args.codigo:
        CODIGO.append(args.codigo.resolve())
    packs: list[Path] = list(args.packs) or [p for p in sorted(CORPUS.iterdir()) if (p / "_estado.json").is_file()]
    FOTOS.mkdir(parents=True, exist_ok=True)
    fallos = 0
    for pack in packs:
        try:
            r = foto(pack)
        except (RuntimeError, OSError) as e:
            fallos += 1
            sys.stdout.buffer.write(f"✗ {pack.name}: {e}\n".encode())
            continue
        problemas: list[str] = []
        if r["no_restaurados"]:
            problemas.append(f"{len(r['no_restaurados'])} archivos no volvieron a su estado: {r['no_restaurados'][:5]}")
        destino = FOTOS / f"{pack.name}.json"
        if args.guardar:
            destino.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        elif destino.is_file():
            base: dict[str, str] = json.loads(destino.read_text(encoding="utf-8"))["escritos"]
            cambiados = sorted(k for k in base if r["escritos"].get(k) != base[k])
            nuevos = sorted(set(r["escritos"]) - set(base))
            if cambiados:
                problemas.append(f"{len(cambiados)} archivos que ya escribía salen distintos: {cambiados[:5]}")
            if nuevos:
                sys.stdout.buffer.write(
                    f"  {pack.name}: {len(nuevos)} archivos nuevos (fuentes nuevas): {nuevos[:5]}\n".encode()
                )
        else:
            problemas.append("no hay foto guardada (corre con --guardar)")
        fallos += bool(problemas)
        marca = "✗" if problemas else "✓"
        detalle = "; ".join(problemas) or f"{len(r['escritos'])} archivos escritos, restaurado byte por byte"
        sys.stdout.buffer.write(f"{marca} {pack.name}: {detalle}\n".encode())
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())

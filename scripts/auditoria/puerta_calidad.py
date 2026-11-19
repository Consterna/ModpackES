"""Puerta de regresión de la calidad: los bancos medidos con respuestas grabadas deben dar exactamente lo mismo.

Mide los bancos `ui_final_contexto`, `libros` y `misiones` con `medir_calidad.py --solo-grabado` (no llama a la API) y
compara cada resultado con la línea base: las traducciones, las métricas, los rechazos y lo que quedó sin grabar. Solo
se ignoran los tiempos. Si un cambio toca algo que llega al motor (máscara, pistas, lotes, glosario), los pedidos ya no
coinciden con la grabación y la puerta lo dice.

Uso:
    uv run python scripts/auditoria/puerta_calidad.py --guardar   # crea la línea base (build/base_calidad/)
    uv run python scripts/auditoria/puerta_calidad.py             # compara con ella; sale con 1 si algo cambió
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

from descargar_corpus import RAIZ as DESCARGAS  # noqa: E402

BANCOS = ("ui_final_contexto", "libros", "misiones")
#: Campos que cambian entre dos corridas idénticas (tiempo de reloj).
VOLATILES = frozenset({"segundos", "descanso"})


def medir(banco: str, salida: Path) -> None:
    """Mide un banco solo con lo grabado (gratis) y deja el detalle en `salida`."""
    orden = [
        sys.executable,
        str(RAIZ / "scripts" / "medir_calidad.py"),
        "--banco", str(DESCARGAS / "banco" / f"{banco}.json"),
        "--vanilla", str(DESCARGAS / "vanilla"),
        "--grabacion", str(DESCARGAS / "banco" / "grabaciones" / f"{banco}_juez.sqlite"),
        "--solo-grabado",
        "--salida", str(salida),
    ]  # fmt: skip
    hecho = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", check=False)
    if hecho.returncode != 0 or not salida.is_file():
        raise SystemExit(f"medir_calidad.py falló con {banco}:\n{hecho.stdout[-2000:]}\n{hecho.stderr[-2000:]}")


def estable(ruta: Path) -> list[dict[str, Any]]:
    """El resultado sin los campos de tiempo."""
    datos: list[dict[str, Any]] = json.loads(ruta.read_text(encoding="utf-8"))
    return [{k: v for k, v in r.items() if k not in VOLATILES} for r in datos]


def _por_original(lista: list[Any]) -> dict[str, Any]:
    """Las traducciones del detalle indexadas por su ámbito y su original."""
    salida: dict[str, Any] = {}
    for t in lista:
        if isinstance(t, dict):
            fila = cast("dict[str, Any]", t)
            salida[f"{fila.get('ambito')}|{fila.get('original')}"] = fila
    return salida


def _corto(valor: Any) -> str:
    texto = json.dumps(valor, ensure_ascii=False) if valor is not None else "—"
    return texto[:160]


def diferencias(base: list[dict[str, Any]], nueva: list[dict[str, Any]]) -> list[str]:
    """Qué cambió, en pocas líneas: los campos y hasta 5 traducciones distintas."""
    if len(base) != len(nueva):
        return [f"cantidad de resultados {len(base)} → {len(nueva)}"]
    salida: list[str] = []
    for a, b in zip(base, nueva, strict=True):
        for campo in sorted(set(a) | set(b)):
            if a.get(campo) == b.get(campo):
                continue
            if campo == "traducciones" and isinstance(a.get(campo), list) and isinstance(b.get(campo), list):
                ta, tb = _por_original(a[campo]), _por_original(b[campo])
                distintas = [k for k in sorted(set(ta) | set(tb)) if ta.get(k) != tb.get(k)]
                salida.append(f"traducciones: {len(distintas)} distintas")
                salida += [f"  «{k[:70]}»: {_corto(ta.get(k))} → {_corto(tb.get(k))}" for k in distintas[:5]]
            else:
                salida.append(f"{campo}: {json.dumps(a.get(campo), ensure_ascii=False)[:120]} → "
                              f"{json.dumps(b.get(campo), ensure_ascii=False)[:120]}")  # fmt: skip
    return salida


def main() -> int:
    salida = cast(io.TextIOWrapper, sys.stdout)
    if hasattr(salida, "reconfigure"):
        salida.reconfigure(encoding="utf-8")  # «✓» y tildes, aunque la consola sea cp1252
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guardar", action="store_true", help="medir y guardar como línea base")
    ap.add_argument("--carpeta", type=Path, default=RAIZ / "build" / "base_calidad")
    args = ap.parse_args()
    args.carpeta.mkdir(parents=True, exist_ok=True)
    fallos = 0
    for banco in BANCOS:
        base = args.carpeta / f"{banco}.json"
        if args.guardar:
            medir(banco, base)
            print(f"{banco}: línea base guardada en {base}")
            continue
        if not base.is_file():
            raise SystemExit(f"No hay línea base de {banco}: corre primero con --guardar")
        nueva = args.carpeta / f"{banco}.actual.json"
        medir(banco, nueva)
        cambios = diferencias(estable(base), estable(nueva))
        if cambios:
            fallos += 1
            print(f"✗ {banco}: cambió")
            print("\n".join(f"    {c}" for c in cambios))
        else:
            print(f"✓ {banco}: idéntico a la línea base")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())

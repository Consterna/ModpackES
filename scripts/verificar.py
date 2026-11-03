"""Puerta de calidad: corre todas las verificaciones en orden y dice si pasaron.

Uso:  uv run python scripts/verificar.py [--rapido]
  --rapido  se salta las pruebas que usan Java y el corpus real.
"""

from __future__ import annotations

import subprocess
import sys
import time

PASOS: list[tuple[str, list[str]]] = [
    ("ruff check", ["ruff", "check"]),
    ("ruff format", ["ruff", "format", "--check"]),
    ("pyright estricto", ["pyright"]),
    ("compileall", [sys.executable, "-m", "compileall", "-q", "src"]),
    (
        "pytest",
        [sys.executable, "-m", "pytest", "--cov", "--cov-report=term-missing:skip-covered", "-p", "no:cacheprovider"],
    ),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    rapido = "--rapido" in sys.argv
    fallos: list[str] = []
    for nombre, base in PASOS:
        comando = [*base, "-m", "not java and not corpus"] if rapido and nombre == "pytest" else base
        inicio = time.perf_counter()
        proc = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        segundos = time.perf_counter() - inicio
        estado = "OK " if proc.returncode == 0 else "FALLA"
        print(f"[{estado}] {nombre} ({segundos:.1f} s)")
        if proc.returncode != 0:
            fallos.append(nombre)
            print((proc.stdout + proc.stderr)[-4000:])
        elif nombre == "pytest":
            print("\n".join(linea for linea in proc.stdout.splitlines() if "TOTAL" in linea or "passed" in linea))
    print("\nRESULTADO:", "TODO BIEN" if not fallos else "FALLAS EN " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())

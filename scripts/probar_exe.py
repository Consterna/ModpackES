"""Prueba el .exe ya construido: arranca sin pantalla, analiza un modpack fabricado y revisa el resultado.

Uso:  uv run python scripts/probar_exe.py [dist/ModpackES.exe]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import fabrica  # noqa: E402

from traductor_es import NOMBRE, __version__  # noqa: E402


def main() -> int:
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "dist" / f"{NOMBRE}.exe"
    with tempfile.TemporaryDirectory() as tmp:
        juego = fabrica.prism(Path(tmp), "1.20.1")
        fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench"}))
        capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
        capitulo.parent.mkdir(parents=True)
        capitulo.write_text('{ title: "Getting Started" }', encoding="utf-8")
        salida = Path(tmp) / "autoprueba.json"
        proc = subprocess.run(
            [str(exe), "--autoprueba", str(juego), str(salida)],
            env={**os.environ, "TRADUCTOR_ES_DATOS": str(Path(tmp) / "datos"), "QT_QPA_PLATFORM": "offscreen"},
            timeout=300,
            check=False,
        )  # fmt: skip
        if proc.returncode != 0 or not salida.is_file():
            print(f"FALLA: el .exe terminó con código {proc.returncode}")
            return 1
        datos = json.loads(salida.read_text("utf-8"))
    esperado = {"version_app": __version__, "minecraft": "1.20.1", "loader": "forge", "icono": True}
    distintos = {k: datos.get(k) for k, v in esperado.items() if datos.get(k) != v}
    grupos = {m["grupo"] for m in datos["modulos"]}
    if distintos or grupos != {"mods", "misiones"}:
        print(f"FALLA: {distintos or grupos}")
        return 1
    print(f"OK: {exe.name} {datos['version_app']} analizó Minecraft {datos['minecraft']} ({', '.join(sorted(grupos))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

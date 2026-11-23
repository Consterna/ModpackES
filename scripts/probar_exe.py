"""Prueba el programa ya construido: arranca sin pantalla, analiza un modpack fabricado y revisa el resultado.

Uso:  uv run python scripts/probar_exe.py [dist/ModpackES-portable.zip | carpeta/ModpackES.exe]
      uv run python scripts/probar_exe.py --instalador [dist/ModpackES-instalador.exe]
El zip se extrae en una carpeta temporal y se prueba el programa de dentro, también con una `dwmapi.dll` falsa al
lado (H-016: tiene que seguir usando la de System32). Con --instalador lo instala en silencio en una carpeta
temporal, prueba el programa instalado y lo desinstala.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import fabrica  # noqa: E402

from traductor_es import NOMBRE, __version__  # noqa: E402


def probar(exe: Path) -> int:
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
    esperado = {"version_app": __version__, "minecraft": "1.20.1", "loader": "forge", "icono": True, "registro": True}
    distintos = {k: datos.get(k) for k, v in esperado.items() if datos.get(k) != v}
    dwmapi, sistema = Path(str(datos.get("dwmapi", ""))), str(datos.get("system32", ""))
    # La precarga de lanzador_ventana.py (H-016); Windows no distingue mayúsculas en las rutas
    if not sistema or str(dwmapi.parent).casefold() != str(Path(sistema)).casefold():
        distintos["dwmapi"] = str(dwmapi)
    if int(datos.get("iconos", 0)) < 30:  # los SVG de la interfaz tienen que ir dentro del .exe
        distintos["iconos"] = datos.get("iconos")
    grupos = {m["grupo"] for m in datos["modulos"]}
    if distintos or grupos != {"mods", "misiones"}:
        print(f"FALLA: {distintos or grupos}")
        return 1
    print(f"OK: {exe.name} {datos['version_app']} analizó Minecraft {datos['minecraft']} ({', '.join(sorted(grupos))})")
    return 0


def probar_portable(paquete: Path) -> int:
    """Extrae el zip, comprueba que trae una sola carpeta ModpackES/ y prueba el programa, con y sin DLL falsa."""
    with zipfile.ZipFile(paquete) as z:
        raices = {PurePosixPath(n).parts[0] for n in z.namelist()}
        if raices != {NOMBRE} or f"{NOMBRE}/{NOMBRE}.exe" not in z.namelist():
            print(f"FALLA: el zip tiene que traer solo la carpeta {NOMBRE}/ con {NOMBRE}.exe (trae {sorted(raices)})")
            return 1
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            z.extractall(tmp)
            exe = Path(tmp) / NOMBRE / f"{NOMBRE}.exe"
            codigo = probar(exe)
            if codigo:
                return codigo
            (exe.parent / "dwmapi.dll").write_bytes(b"MZ\x00\x00\xde\xad\xbe\xef")  # una DLL plantada
            if probar(exe):
                print("FALLA: con una dwmapi.dll falsa junto al programa, la cargó")
                return 1
    print(f"OK: {paquete.name} trae la carpeta {NOMBRE}/ y una DLL plantada no se carga")
    return 0


def probar_instalador(instalador: Path) -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # el desinstalador puede tardar en soltarla
        destino = Path(tmp) / "ModpackES"
        silencio = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        proc = subprocess.run(
            [str(instalador), *silencio, "/CURRENTUSER", f"/DIR={destino}", "/TASKS="], timeout=300, check=False
        )
        exe = destino / f"{NOMBRE}.exe"
        if proc.returncode != 0 or not exe.is_file():
            print(f"FALLA: el instalador terminó con código {proc.returncode} y no dejó {exe.name}")
            return 1
        codigo = probar(exe)
        desinstalador = destino / "unins000.exe"
        quitar = subprocess.run([str(desinstalador), *silencio], timeout=300, check=False)
        # El desinstalador de Inno Setup sigue desde una copia temporal: se le da un rato para terminar de borrar
        limite = time.monotonic() + 60
        while exe.exists() and time.monotonic() < limite:
            time.sleep(0.5)
        if quitar.returncode != 0 or exe.exists():
            print(f"FALLA: el desinstalador terminó con código {quitar.returncode} o dejó el programa")
            return 1
        if codigo == 0:
            print(f"OK: {instalador.name} instala, el programa funciona y se desinstala")
        return codigo


def main(argv: list[str]) -> int:
    if argv[:1] == ["--instalador"]:
        ruta = Path(argv[1]) if len(argv) > 1 else RAIZ / "dist" / f"{NOMBRE}-instalador.exe"
        return probar_instalador(ruta)
    ruta = Path(argv[0]) if argv else RAIZ / "dist" / f"{NOMBRE}-portable.zip"
    return probar_portable(ruta) if ruta.suffix.lower() == ".zip" else probar(ruta)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

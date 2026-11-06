"""Casos límite de la salida: options.txt, copias de seguridad, exportación y la línea de comandos real."""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from traductor_es.salida import exportar, opciones
from traductor_es.salida.copias import Respaldo

from . import fabrica

RAIZ = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ options.txt
def _opts(tmp_path: Path, crudo: bytes) -> Path:
    (tmp_path / "options.txt").write_bytes(crudo)
    return tmp_path


def test_activar_conserva_crlf_y_otras_lineas_y_es_idempotente(tmp_path: Path) -> None:
    crudo = (
        'fov:0.5\r\nlang:en_us\r\nresourcePacks:["vanilla","file/Otro"]\r\n'
        'incompatibleResourcePacks:["file/Traduccion_ES"]\r\n'
    )
    _opts(tmp_path, crudo.encode())
    cambios = opciones.activar(tmp_path, "Traduccion_ES", "es_mx")
    nuevo = (tmp_path / "options.txt").read_bytes().decode()
    assert cambios and nuevo.count("\r\n") == nuevo.count("\n") and "fov:0.5\r\n" in nuevo
    assert 'resourcePacks:["vanilla","file/Otro","file/Traduccion_ES"]' in nuevo and "lang:es_mx" in nuevo
    assert "incompatibleResourcePacks:[]" in nuevo
    assert opciones.activar(tmp_path, "Traduccion_ES", "es_mx") == []  # ya está: no cambia nada
    assert (tmp_path / "options.txt").read_bytes().decode() == nuevo


def test_activar_sin_options_no_crea_nada_y_con_lista_danada_no_toca(tmp_path: Path) -> None:
    assert opciones.activar(tmp_path, "Traduccion_ES", "es_mx") == [] and not (tmp_path / "options.txt").exists()
    crudo = b"lang:en_us\nresourcePacks:[esto no es json\n"
    _opts(tmp_path, crudo)
    with pytest.raises(ValueError, match="lista de resource packs"):
        opciones.activar(tmp_path, "Traduccion_ES", "es_mx")
    assert (tmp_path / "options.txt").read_bytes() == crudo


def test_activar_conserva_bytes_que_no_son_utf8_y_nombres_con_ene(tmp_path: Path) -> None:
    crudo = b'lastServer:caf\xe9\nresourcePacks:["vanilla","file/\xc3\x91and\xc3\xba"]\n'
    _opts(tmp_path, crudo)
    opciones.activar(tmp_path, "Traduccion_ES", None)
    nuevo = (tmp_path / "options.txt").read_bytes()
    assert b"lastServer:caf\xe9\n" in nuevo  # el byte raro sigue igual
    assert '"file/Ñandú","file/Traduccion_ES"'.encode() in nuevo


# ------------------------------------------------------------------ copias de seguridad
def test_respaldo_restaura_cuando_el_archivo_cambio_o_se_borro(tmp_path: Path) -> None:
    juego = tmp_path / "juego"
    ruta = juego / "kubejs" / "ñandú ¡x!.js"
    ruta.parent.mkdir(parents=True)
    ruta.write_bytes(b"original")
    r = Respaldo(juego)
    r.escribir(ruta, b"traducido")
    assert r.original(ruta) == b"original"
    ruta.unlink()  # el usuario borró el archivo
    assert r.restaurar() == [ruta] and ruta.read_bytes() == b"original"
    ruta.write_bytes(b"actualizado por el modpack")  # y luego lo actualizó otra versión del modpack
    assert r.original(ruta) == b"actualizado por el modpack"


def test_respaldo_con_registro_corrupto_empieza_de_cero(tmp_path: Path) -> None:
    juego = tmp_path / "juego"
    (juego / "traductor_es").mkdir(parents=True)
    (juego / "traductor_es" / "registro.json").write_bytes(b"{no es json")
    ruta = juego / "a.js"
    ruta.write_bytes(b"x")
    r = Respaldo(juego)
    r.escribir(ruta, b"y")
    assert json.loads((juego / "traductor_es" / "registro.json").read_text("utf-8"))


def test_respaldo_rechaza_rutas_fuera_de_la_instancia(tmp_path: Path) -> None:
    juego = tmp_path / "juego"
    juego.mkdir()
    fuera = tmp_path / "fuera.txt"
    fuera.write_bytes(b"x")
    with pytest.raises(ValueError):
        Respaldo(juego).escribir(fuera, b"y")
    assert fuera.read_bytes() == b"x"


# ------------------------------------------------------------------ exportar
def test_exportar_kit_y_pack(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    pack = juego / "resourcepacks" / "Traduccion_ES"
    (pack / "assets" / "m" / "lang").mkdir(parents=True)
    (pack / "pack.mcmeta").write_text("{}", encoding="utf-8")
    (pack / "assets" / "m" / "lang" / "es_mx.json").write_text('{"a": "Ñandú"}', encoding="utf-8")
    script = juego / "kubejs" / "server_scripts" / "s.js"
    script.parent.mkdir(parents=True)
    script.write_text("x", encoding="utf-8")
    Respaldo(juego).escribir(script, b"traducido")
    destino = tmp_path / "salida" / "kit.zip"
    assert exportar.exportar_kit_servidor(juego, destino) >= 2
    with zipfile.ZipFile(destino) as z:
        assert z.testzip() is None and "kubejs/server_scripts/s.js" in z.namelist()
    assert exportar.exportar_pack(juego, tmp_path / "salida" / "pack.zip") == 2
    with pytest.raises(ValueError, match="traduce primero"):
        exportar.exportar_pack(tmp_path / "otro", tmp_path / "x.zip")


# ------------------------------------------------------------------ línea de comandos real
def _cli(*args: str, datos: Path) -> subprocess.CompletedProcess[str]:
    entorno = {**os.environ, "TRADUCTOR_ES_DATOS": str(datos), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", "traductor_es", *args], capture_output=True, text=True, encoding="utf-8",
        env=entorno, cwd=RAIZ, timeout=120, check=False,
    )  # fmt: skip


def test_cli_ayuda_version_y_argumentos_invalidos(tmp_path: Path) -> None:
    assert _cli("--version", datos=tmp_path).returncode == 0
    assert "traducir" in _cli("--help", datos=tmp_path).stdout
    malo = _cli("traducir", datos=tmp_path)  # falta la carpeta
    assert malo.returncode != 0 and "carpeta" in malo.stderr
    assert _cli("analizar", "x", "--dialecto", "klingon", datos=tmp_path).returncode != 0


def test_cli_carpeta_que_no_existe_da_un_error_claro_sin_traza(tmp_path: Path) -> None:
    r = _cli("analizar", str(tmp_path / "no_existe"), datos=tmp_path)
    assert r.returncode != 0 and "Traceback" not in r.stderr + r.stdout


def test_cli_analiza_traduce_simulado_restaura_y_cobertura(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    script = juego / "kubejs" / "server_scripts" / "s.js"
    script.parent.mkdir(parents=True)
    original = "PlayerEvents.chat(e => { e.player.tell('Welcome to the pack ñ') })\n"
    script.write_text(original, encoding="utf-8")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.a": "Iron Plate ñ"}))
    datos = tmp_path / "datos"
    carpeta = str(juego.parent)
    a = _cli("analizar", carpeta, datos=datos)
    assert a.returncode == 0 and "Traceback" not in a.stderr and script.read_text("utf-8") == original  # solo lee
    t = _cli("traducir", carpeta, "--simular", "--no-activar", "--no-idioma", datos=datos)
    assert t.returncode == 0, t.stderr
    assert "«ES» Welcome to the pack ñ" in script.read_text("utf-8")
    assert json.loads((juego / "resourcepacks" / "Traduccion_ES" / "assets" / "m" / "lang" / "es_mx.json").read_bytes())
    c = _cli("cobertura", carpeta, datos=datos)
    assert c.returncode == 0 and "Traceback" not in c.stderr
    r = _cli("restaurar", carpeta, datos=datos)
    assert r.returncode == 0 and script.read_text("utf-8") == original

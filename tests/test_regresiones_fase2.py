"""Pruebas de los hallazgos de la revisión de la fase 2."""

import json
import os
import time
from pathlib import Path

import pytest

from traductor_es.formatos import lang_json
from traductor_es.fuentes import deteccion, vanilla
from traductor_es.fuentes.contenedores import Carpeta
from traductor_es.fuentes.instancia import Instancia
from traductor_es.fuentes.recursos import PRIORIDAD_MOD, PRIORIDAD_VANILLA, TablaIdiomas
from traductor_es.fuentes.version import Version
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.salida import opciones
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica


def test_las_claves_viejas_no_tapan_traducciones_nuevas(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    with Instancia(juego) as inst:
        pack = PackSalida(inst)
        pack.preparar()
        viejo = pack.escribir_lang("m", "es_mx", {"a": "Máquina", "b": "Vieja"})
        otro = pack.escribir_lang("x", "es_mx", {"c": "Ya no hace falta"})
    with Instancia(juego) as inst:  # segunda ejecución: «b» y todo «x» ya los trae el mod
        pack = PackSalida(inst)
        pack.preparar()
        pack.escribir_lang("m", "es_mx", {"a": "Máquina"})
        vaciados = pack.vaciar_idiomas_viejos()
    assert lang_json.leer(viejo.read_bytes()) == {"a": "Máquina"}
    assert vaciados == [otro] and lang_json.leer(otro.read_bytes()) == {}


def test_sin_espanol_oficial_no_se_tocan_claves_del_juego() -> None:
    tabla = TablaIdiomas()
    tabla.agregar("minecraft", "en_us", {"block.stone": "Stone", "mod.key": "Mod text"}, PRIORIDAD_VANILLA, "v")
    tabla.agregar("minecraft", "en_us", {"block.stone": "Stone", "mod.key": "Mod text"}, PRIORIDAD_MOD, "mod")
    tabla.agregar("minecraft", "en_us", {"mod.solo": "Only in mod"}, PRIORIDAD_MOD, "mod")
    tabla.vanilla_sin_espanol = True
    claves = {p.clave for p in tabla.pendientes(VARIANTES)}
    assert claves == {"mod.solo"}
    tabla.vanilla_sin_espanol = False
    assert {p.clave for p in tabla.pendientes(VARIANTES)} == {"block.stone", "mod.key", "mod.solo"}


@pytest.mark.parametrize("mala", ["assets/..\\..\\x/lang/es_mx.json", "assets/C:x/lang/a.json", "a/b\x01/c", "a//b"])
def test_rutas_trucadas_de_windows(tmp_path: Path, mala: str) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    with Instancia(juego) as inst, pytest.raises(ValueError):
        PackSalida(inst).escribir(mala, b"x")


def test_vanilla_no_usa_el_indice_de_otra_version(tmp_path: Path) -> None:
    raiz = tmp_path / "launcher"
    fabrica.jar(raiz / "versions" / "1.20.1" / "1.20.1.jar", {"assets/minecraft/lang/en_us.json": {"a": "A"}})
    (raiz / "versions" / "1.20.1" / "1.20.1.json").write_text('{"assetIndex": {"id": "5"}}', encoding="utf-8")
    (raiz / "assets" / "indexes").mkdir(parents=True)
    (raiz / "assets" / "objects" / "ab").mkdir(parents=True)
    (raiz / "assets" / "objects" / "ab" / "abcd").write_text('{"a": "Otra versión"}', encoding="utf-8")
    objetos = {"objects": {"minecraft/lang/es_mx.json": {"hash": "abcd"}}}
    (raiz / "assets" / "indexes" / "29.json").write_text(json.dumps(objetos), encoding="utf-8")
    v = vanilla.cargar(Version.de("1.20.1"), ["en_us", "es_mx"], [raiz])
    assert "es_mx" not in v.textos and v.textos["en_us"] == {"a": "A"}


def test_versiones_de_loader_no_cuentan_como_minecraft(tmp_path: Path) -> None:
    jars = [tmp_path / "neoforge-20.4.237.jar", tmp_path / "lib-20.4.1.jar", tmp_path / "x-mc26.1.jar"]
    d = deteccion.detectar(tmp_path, jars)
    assert str(d.version) == "26.1"


def test_log_viejo_que_no_coincide_con_los_mods(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    log = tmp_path / "logs" / "latest.log"
    log.write_text("Loading Minecraft 1.20.1 with Fabric Loader 0.15", encoding="utf-8")
    viejo = time.time() - 3600
    os.utime(log, (viejo, viejo))
    meta = {"fabric.mod.json": json.dumps({"depends": {"minecraft": ">=1.21.1"}})}
    jars = [fabrica.jar(tmp_path / f"m{i}.jar", meta) for i in range(2)]
    assert str(deteccion.detectar(tmp_path, jars).version) == "1.21.1"
    # Si coincide en la versión mayor, el log (más preciso) sigue mandando
    meta = {"fabric.mod.json": json.dumps({"depends": {"minecraft": ">=1.20"}})}
    jars = [fabrica.jar(tmp_path / f"n{i}.jar", meta) for i in range(2)]
    assert str(deteccion.detectar(tmp_path, jars).version) == "1.20.1"


def test_options_danado_avisa_y_no_toca(tmp_path: Path) -> None:
    ruta = tmp_path / "options.txt"
    ruta.write_text('resourcePacks:["vanilla",\nlang:en_us\n', encoding="utf-8")
    with pytest.raises(ValueError, match="resource packs"):
        opciones.activar(tmp_path, "P", "es_mx")
    assert ruta.read_text(encoding="utf-8") == 'resourcePacks:["vanilla",\nlang:en_us\n'


def test_carpetas_no_recorren_texturas(tmp_path: Path) -> None:
    for rel in ("assets/m/lang/en_us.json", "assets/m/textures/a.png", "assets/m/patchouli_books/b/x.json"):
        (tmp_path / "pack" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "pack" / rel).write_text("{}", encoding="utf-8")
    assert Carpeta(tmp_path / "pack").nombres() == ["assets/m/lang/en_us.json", "assets/m/patchouli_books/b/x.json"]
    kubejs = Carpeta(tmp_path / "pack" / "assets", prefijo="assets/")
    assert kubejs.nombres() == ["assets/m/lang/en_us.json", "assets/m/patchouli_books/b/x.json"]

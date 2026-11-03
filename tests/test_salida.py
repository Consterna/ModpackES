import json
from pathlib import Path

import pytest

from traductor_es.formatos import lang_json, lang_legacy
from traductor_es.fuentes.instancia import Instancia
from traductor_es.fuentes.recursos import MARCA
from traductor_es.salida import opciones
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica


def test_pack_moderno(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.21.11", "neoforge")
    with Instancia(juego) as inst:
        pack = PackSalida(inst)
        pack.preparar()
        pack.escribir_lang("m", "es_mx", {"b": "Bé", "a": "A"})
        ruta = pack.escribir_lang("m", "es_mx", {"c": "Ce"})
    assert ruta == juego / "resourcepacks" / "Traduccion_ES" / "assets" / "m" / "lang" / "es_mx.json"
    assert lang_json.leer(ruta.read_bytes()) == {"c": "Ce"}  # cada escritura reemplaza el archivo completo
    meta = json.loads((pack.raiz / "pack.mcmeta").read_text(encoding="utf-8"))
    assert meta["pack"]["min_format"] == 75 and "pack_format" not in meta["pack"]
    assert json.loads((pack.raiz / MARCA).read_text(encoding="utf-8"))["app"] == "ModpackES"


@pytest.mark.parametrize(("version", "archivo"), [("1.12.2", "es_es.lang"), ("1.10.2", "es_ES.lang")])
def test_pack_legacy(tmp_path: Path, version: str, archivo: str) -> None:
    juego = fabrica.prism(tmp_path, version)
    with Instancia(juego) as inst:
        pack = PackSalida(inst)
        pack.preparar()
        ruta = pack.escribir_lang("m", "es_es", {"a": "Hola"})
    assert ruta.name == archivo
    assert lang_legacy.leer(ruta.read_bytes()) == {"a": "Hola"}
    meta = json.loads((pack.raiz / "pack.mcmeta").read_text(encoding="utf-8"))
    assert meta["pack"]["pack_format"] in (2, 3)


def test_no_se_escribe_fuera_del_pack(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    with Instancia(juego) as inst:
        pack = PackSalida(inst)
        for mala in ("../fuera.txt", "/abs.txt", "", "a/../../b"):
            with pytest.raises(ValueError):
                pack.escribir(mala, b"x")


def test_activar_respeta_estilo_y_saltos(tmp_path: Path) -> None:
    ruta = tmp_path / "options.txt"
    ruta.write_bytes(
        b'version:1\r\nresourcePacks:["vanilla","file/A.zip","file/Traduccion_ES"]\r\n'
        b'incompatibleResourcePacks:["file/Traduccion_ES"]\r\nlang:en_us\r\n'
    )
    cambios = opciones.activar(tmp_path, "Traduccion_ES", "es_mx")
    texto = ruta.read_bytes()
    assert b'resourcePacks:["vanilla","file/A.zip","file/Traduccion_ES"]\r\n' in texto
    assert b"incompatibleResourcePacks:[]\r\n" in texto
    assert b"lang:es_mx\r\n" in texto
    assert cambios == ["idioma del juego: es_mx"]
    assert opciones.activar(tmp_path, "Traduccion_ES", "es_mx") == []  # segunda vez: nada que cambiar


def test_activar_sin_prefijo_lo_mueve_arriba(tmp_path: Path) -> None:
    fabrica.opciones(tmp_path, ["vanilla", "Traduccion_ES", "Otro"])
    assert opciones.activar(tmp_path, "Traduccion_ES", None) == ["pack activado arriba del todo"]
    assert 'resourcePacks:["vanilla","Otro","Traduccion_ES"]' in (tmp_path / "options.txt").read_text("utf-8")


def test_activar_agrega_lineas_que_faltan_y_sin_options_no_crea(tmp_path: Path) -> None:
    assert opciones.activar(tmp_path, "P", "es_mx") == []
    assert not (tmp_path / "options.txt").exists()
    (tmp_path / "options.txt").write_text("version:1\n", encoding="utf-8")
    assert opciones.activar(tmp_path, "P", "es_es") == ["pack activado", "idioma del juego: es_es"]
    assert (tmp_path / "options.txt").read_text("utf-8").endswith('resourcePacks:["vanilla","file/P"]\nlang:es_es\n')


def test_resumen_y_conteos_en_singular_y_plural() -> None:
    from traductor_es.modulos.base import Resumen, contar

    assert contar(1, "mod") == "1 mod" and contar(0, "script") == "0 scripts"
    assert str(Resumen([Path("a")], 1)) == "1 archivo escrito, 1 texto traducido"
    assert str(Resumen([Path("a"), Path("b")], 5, 1)) == "2 archivos escritos, 5 textos traducidos, 1 sigue en inglés"

"""Casos límite de las fuentes: instancias rotas o vacías, jars dañados, options.txt raro y versiones inesperadas."""

import json
import zipfile
from pathlib import Path

import pytest

from traductor_es.fuentes import opciones
from traductor_es.fuentes.contenedores import Carpeta, Zip, abrir_mod
from traductor_es.fuentes.deteccion import detectar
from traductor_es.fuentes.instancia import Instancia, resolver_carpeta_juego
from traductor_es.fuentes.version import Version, formato_datos, formato_recursos

from . import fabrica


# ------------------------------------------------------------------ versiones
@pytest.mark.parametrize(
    ("texto", "partes"),
    [
        ("1.20.1", (1, 20, 1)),
        ("1.20", (1, 20, 0)),
        ("1.12.2-forge", (1, 12, 2)),
        (" 26.1 ", (26, 1, 0)),
        ("1.21.11", (1, 21, 11)),
    ],
)
def test_version_se_lee_de_formas_distintas(texto: str, partes: tuple[int, ...]) -> None:
    assert Version.de(texto).partes == partes


@pytest.mark.parametrize("texto", ["", "abc", "1", "v1.2", "..", "latest"])
def test_version_invalida_falla_con_valueerror(texto: str) -> None:
    with pytest.raises(ValueError, match="no reconocida"):
        Version.de(texto)


def test_formatos_de_pack_son_monotonos_y_cubren_todo() -> None:
    versiones = [
        "1.6",
        "1.9",
        "1.11",
        "1.13",
        "1.16.2",
        "1.18",
        "1.19.4",
        "1.20",
        "1.20.5",
        "1.21",
        "1.21.5",
        "26.1",
        "26.3",
    ]
    previos = [formato_recursos(Version.de(v)) for v in versiones]
    assert previos == sorted(previos)  # el formato nunca baja al subir la versión
    assert formato_recursos(Version.de("1.5")) == (1, 0)  # versiones muy viejas: valor por defecto
    assert formato_datos(Version.de("1.12")) is None and formato_datos(Version.de("1.13")) == (4, 0)


# ------------------------------------------------------------------ carpetas y detección
def test_carpeta_que_no_existe_o_vacia(tmp_path: Path) -> None:
    assert resolver_carpeta_juego(tmp_path / "no_existe") is None
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    with pytest.raises(ValueError):
        Instancia(vacia)


def test_resolver_carpeta_acepta_la_instancia_o_su_minecraft(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    assert resolver_carpeta_juego(juego) == juego
    assert resolver_carpeta_juego(juego.parent) == juego


def test_deteccion_con_archivos_de_configuracion_rotos(tmp_path: Path) -> None:
    juego = tmp_path / "Pack" / "minecraft"
    juego.mkdir(parents=True)
    (juego.parent / "mmc-pack.json").write_text("{esto no es json", encoding="utf-8")
    (juego / "minecraftinstance.json").write_bytes(b"\xff\xfe\x00basura")
    (juego / "mods").mkdir()
    (juego / "mods" / "roto.jar").write_bytes(b"no es un zip")
    with pytest.raises(ValueError):
        Instancia(juego)  # sin versión: dice que no la pudo detectar, no revienta con otro error


def test_deteccion_ignora_lo_que_no_es_cadena(tmp_path: Path) -> None:
    juego = tmp_path / "Pack" / "minecraft"
    (juego / "mods").mkdir(parents=True)
    (juego.parent / "mmc-pack.json").write_text(
        json.dumps({"components": [None, 5, {"uid": 3}, {"uid": "net.minecraft"}]})
    )
    d = detectar(juego, [])  # no revienta: simplemente no encuentra la versión
    assert d.version is None and d.origen == "no se pudo detectar"


# ------------------------------------------------------------------ options.txt
@pytest.mark.parametrize(
    ("contenido", "idioma", "packs"),
    [
        ('lang:es_mx\nresourcePacks:["vanilla","file/Mi Pack","mod_resources"]\n', "es_mx", ("Mi Pack",)),
        ("lang:\n", None, ()),
        ("resourcePacks:esto no es json\n", None, ()),
        ('resourcePacks:{"a": 1}\n', None, ()),  # JSON válido pero no es una lista
        ('lang:EN_US\r\nresourcePacks:["file/Ñandú ¡pack!"]\r\n', "en_us", ("Ñandú ¡pack!",)),
        ("", None, ()),
    ],
)
def test_options_txt(tmp_path: Path, contenido: str, idioma: str | None, packs: tuple[str, ...]) -> None:
    (tmp_path / "options.txt").write_text(contenido, encoding="utf-8", newline="")
    o = opciones.leer(tmp_path)
    assert o.idioma == idioma and o.packs == packs


def test_options_txt_inexistente_o_con_bytes_invalidos(tmp_path: Path) -> None:
    assert opciones.leer(tmp_path) == opciones.Opciones()
    (tmp_path / "options.txt").write_bytes(b"lang:es_mx\n\xff\xfe\x00 basura \x80\n")
    assert opciones.leer(tmp_path).idioma == "es_mx"


# ------------------------------------------------------------------ contenedores y jars
def test_jar_danado_no_detiene_la_lectura(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    (juego / "mods" / "roto.jar").write_bytes(b"PK\x03\x04 truncado")
    fabrica.jar(juego / "mods" / "bueno.jar", fabrica.lang("m", "en_us", {"item.m.a": "Iron Plate"}))
    with Instancia(juego) as inst:
        tabla = inst.tabla_idiomas()
        assert tabla.textos("m", "en_us")["item.m.a"] == "Iron Plate"


def test_jar_con_nombres_unicode_y_lang_con_ene(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "Ñandú ¡mod! 日本.jar", fabrica.lang("ñ", "en_us", {"item.a": "Plátano ñ"}))
    with Instancia(juego) as inst:
        assert [c.nombre for c in inst.contenedores_mods()] == ["Ñandú ¡mod! 日本.jar"]


def test_zip_con_entradas_peligrosas_no_se_extrae(tmp_path: Path) -> None:
    ruta = tmp_path / "m.jar"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("../../fuera.txt", "x")
        z.writestr("assets/m/lang/en_us.json", '{"a": "b"}')
    contenedores = list(abrir_mod(ruta))
    try:
        assert contenedores and contenedores[0].leer("assets/m/lang/en_us.json") == b'{"a": "b"}'
    finally:
        for c in contenedores:
            c.cerrar()
    assert not (tmp_path.parent / "fuera.txt").exists()  # solo se lee en memoria: nada se escribe en disco


def test_jars_anidados_con_limite_de_profundidad(tmp_path: Path) -> None:
    interior = fabrica.zip_en_memoria(fabrica.lang("m", "en_us", {"a": "Hello there"}))
    for _ in range(6):  # un jar dentro de un jar dentro de otro…
        interior = fabrica.zip_en_memoria({"META-INF/jarjar/x.jar": interior})
    ruta = tmp_path / "profundo.jar"
    ruta.write_bytes(interior)
    contenedores = list(abrir_mod(ruta))  # no debe colgarse ni lanzar
    for c in contenedores:
        c.cerrar()
    assert len(contenedores) >= 1


def test_carpeta_como_contenedor_ignora_lo_que_sale_de_la_raiz(tmp_path: Path) -> None:
    (tmp_path / "pack" / "assets" / "m" / "lang").mkdir(parents=True)
    (tmp_path / "pack" / "assets" / "m" / "lang" / "en_us.json").write_text('{"a": "b"}', encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")
    c = Carpeta(tmp_path / "pack")
    assert "assets/m/lang/en_us.json" in c.nombres()
    for fuera in ("../secreto.txt", "assets/../../secreto.txt", str(tmp_path / "secreto.txt")):
        with pytest.raises(KeyError):
            c.leer(fuera)
    assert c.leer("assets/m/lang/en_us.json") == b'{"a": "b"}'


def test_zip_abrir_un_archivo_que_no_es_zip(tmp_path: Path) -> None:
    ruta = tmp_path / "x.zip"
    ruta.write_bytes(b"nada")
    with pytest.raises(zipfile.BadZipFile):
        Zip.abrir(ruta)

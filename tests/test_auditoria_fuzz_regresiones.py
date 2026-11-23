"""Casos que encontró el fuzzing de los parsers (H-021 y H-022), reducidos a lo mínimo.

Un archivo dañado o con miles de niveles de anidamiento dentro de un modpack no debe tumbar el análisis entero:
se salta ese archivo como si estuviera roto, se avisa y lo demás se traduce.
"""

from __future__ import annotations

import importlib.util
import io
import types
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from traductor_es.formatos import json_cadenas, json_texto, lang_json
from traductor_es.fuentes import contenedores, vanilla
from traductor_es.fuentes.contenedores import EntradaIlegible, Zip, leer_entrada
from traductor_es.fuentes.version import formato_desde_jar
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

from . import fabrica

PROFUNDO = "[" * 5000 + "]" * 5000


@pytest.fixture(autouse=True)
def _limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
    contenedores.DANADAS.clear()
    contenedores.DESCARTADAS.clear()


# --- JSON con miles de niveles (RecursionError) ---------------------------------------------------------------------


def test_json_cadenas_profundo_es_un_json_roto() -> None:
    with pytest.raises(ValueError, match="anidamiento"):
        json_cadenas.escanear('{"pages": ' + PROFUNDO + "}")


def test_json_texto_profundo_no_es_un_componente() -> None:
    assert json_texto.cargar(PROFUNDO) is None


def test_lang_json_profundo_es_un_archivo_roto() -> None:
    with pytest.raises(ValueError, match="anidamiento"):
        lang_json.leer(('{"a": ' + PROFUNDO + "}").encode())


def test_version_json_profundo_no_da_formato() -> None:
    assert formato_desde_jar(('{"pack_version": ' + PROFUNDO + "}").encode(), "resource") is None


# --- entradas de jar que no se pueden descomprimir ------------------------------------------------------------------


def _zip(datos: bytes, compresion: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compresion) as z:
        z.writestr("assets/m/lang/en_us.json", datos)
    return buffer.getvalue()


def _deflate_roto() -> bytes:
    crudo = bytearray(_zip(b'{"item.m.x": "Broken thing"}' * 50))
    inicio = crudo.index(b"en_us.json") + len(b"en_us.json")
    for i in range(inicio + 2, inicio + 30):
        crudo[i] ^= 0x5A
    return bytes(crudo)


def _cifrado() -> bytes:
    crudo = bytearray(_zip(b'{"a": "b"}', zipfile.ZIP_STORED))
    for firma in (b"PK\x03\x04", b"PK\x01\x02"):  # bit 0 de las banderas en la cabecera local y en la central
        pos = crudo.index(firma)
        desplazamiento = 6 if firma == b"PK\x03\x04" else 8
        crudo[pos + desplazamiento] |= 0x01
    return bytes(crudo)


def _metodo_raro() -> bytes:
    crudo = bytearray(_zip(b'{"a": "b"}', zipfile.ZIP_STORED))
    for firma, desplazamiento in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
        pos = crudo.index(firma)
        crudo[pos + desplazamiento : pos + desplazamiento + 2] = (77).to_bytes(2, "little")
    return bytes(crudo)


@pytest.mark.parametrize("fabricar", [_deflate_roto, _cifrado, _metodo_raro], ids=["crc", "cifrado", "metodo"])
def test_entrada_que_no_se_puede_descomprimir_es_ilegible(fabricar: Callable[[], bytes]) -> None:
    with zipfile.ZipFile(io.BytesIO(fabricar())) as z, pytest.raises(EntradaIlegible):
        leer_entrada(z, "assets/m/lang/en_us.json", "roto.jar")
    assert {"roto.jar!/assets/m/lang/en_us.json"} == contenedores.DANADAS


def test_entrada_ilegible_la_saltan_quienes_esperan_badzipfile_o_valueerror(tmp_path: Path) -> None:
    ruta = tmp_path / "roto.jar"
    ruta.write_bytes(_deflate_roto())
    z = Zip.abrir(ruta)
    try:
        for esperada in (zipfile.BadZipFile, ValueError):
            with pytest.raises(esperada):
                z.leer("assets/m/lang/en_us.json")
    finally:
        z.cerrar()


# --- de punta a punta: el análisis sigue y avisa --------------------------------------------------------------------


@pytest.mark.parametrize("caso", ["jar roto", "libro profundo", "mision profunda"])
def test_un_archivo_hostil_no_tumba_el_analisis(tmp_path: Path, caso: str) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "bueno.jar", fabrica.lang("bueno", "en_us", {"item.bueno.x": "Iron Plate"}))
    if caso == "jar roto":
        (juego / "mods" / "roto.jar").write_bytes(_deflate_roto())
    elif caso == "libro profundo":
        entrada = juego / "patchouli_books" / "guia" / "en_us" / "entries" / "e.json"
        entrada.parent.mkdir(parents=True)
        entrada.write_text('{"name": "Intro", "pages": ' + PROFUNDO + "}", encoding="utf-8")
        (juego / "patchouli_books" / "guia" / "book.json").write_text('{"name": "Guide"}', encoding="utf-8")
    else:
        q = juego / "config" / "betterquesting" / "DefaultQuests.json"
        q.parent.mkdir(parents=True)
        q.write_text('{"questDatabase:9": ' + PROFUNDO + "}", encoding="utf-8")
    with Memoria(":memory:") as m, Proceso(juego, Simulador(), memoria=m) as p:
        analisis = p.analizar()
        informe = p.ejecutar()
    assert analisis.a_traducir >= 1
    lang = juego / "resourcepacks" / "Traduccion_ES" / "assets" / "bueno" / "lang" / "es_mx.json"
    assert "«ES» Iron Plate" in lang.read_text(encoding="utf-8")
    if caso == "jar roto":
        assert any("archivos dañados" in a and "roto.jar!/" in a and ":\\" not in a for a in informe.avisos)


# --- NBT con una cadena cortada a mitad de un carácter (IndexError) -------------------------------------------------


@pytest.mark.parametrize(
    "hexadecimal",
    [
        "8f00023eec9a609396b875321f8b0800000002",
        "00000800000000000000e300000000e362606066e04a492d48",
        "00000400445ddd6c00",
    ],
)
def test_nbt_con_un_caracter_cortado_es_un_archivo_roto(hexadecimal: str) -> None:
    from traductor_es.formatos import nbt

    with pytest.raises(ValueError, match="cortada"):
        nbt.leer(bytes.fromhex(hexadecimal))


@pytest.mark.parametrize("datos", [b"\xc3", b"ab\xe2\x82", b"\xe2"])
def test_utf8_modificado_cortado(datos: bytes) -> None:
    from traductor_es.formatos import nbt

    with pytest.raises(ValueError):
        nbt.mutf8_decodificar(datos)


# --- zip con una «versión necesaria para extraer» que Python no admite (NotImplementedError al abrir) -------------


def _version_rara(ruta: Path) -> Path:
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("assets/raro/lang/en_us.json", '{"item.raro.x": "Odd thing"}')
    datos = bytearray(ruta.read_bytes())
    datos[datos.index(b"PK\x01\x02") + 6] = 84  # versión 8.4 en el directorio central (Java la abre igual)
    ruta.write_bytes(bytes(datos))
    return ruta


def test_zip_con_version_rara_se_abre_como_ilegible(tmp_path: Path) -> None:
    from traductor_es.fuentes.contenedores import abrir_zip

    with pytest.raises(EntradaIlegible):
        abrir_zip(_version_rara(tmp_path / "raro.jar"))
    assert "raro.jar" in contenedores.DANADAS


def test_jar_con_version_rara_no_tumba_el_analisis(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "bueno.jar", fabrica.lang("bueno", "en_us", {"item.bueno.x": "Iron Plate"}))
    _version_rara(juego / "mods" / "raro.jar")
    with Memoria(":memory:") as m, Proceso(juego, Simulador(), memoria=m) as p:
        analisis = p.analizar()
    assert analisis.a_traducir >= 1
    assert any("raro.jar" in a for a in analisis.avisos)


def _arnes() -> types.ModuleType:
    ruta = Path(__file__).resolve().parent.parent / "scripts" / "auditoria" / "fuzz_parsers.py"
    spec = importlib.util.spec_from_file_location("fuzz_parsers", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize("parser", sorted(_arnes().PARSERS))
def test_el_arnes_de_fuzzing_corre_cada_parser(parser: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """El workflow «Fuzzing» corre este arnés 1 h por parser: aquí, una fracción de segundo para que no se rompa."""
    arnes = _arnes()
    monkeypatch.setattr(arnes, "SALIDA", tmp_path)
    resultado = arnes.fuzz(parser, 0.003)
    assert resultado["casos"] > 0 and resultado["fallos"] == {}

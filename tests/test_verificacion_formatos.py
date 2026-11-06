"""Casos límite de los formatos: idioma JSON y .lang, JSON/SNBT/JS/NBT/markdown con entradas raras, y UTF-8."""

import contextlib
import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from traductor_es.formatos import (
    comandos,
    componente,
    javascript,
    json_cadenas,
    json_texto,
    lang_json,
    lang_legacy,
    markdown,
    nbt,
    snbt,
)

TEXTO = st.text(st.characters(blacklist_categories=("Cs",)), max_size=40)
SEPARADORES = "\r\n\x85" + chr(0x2028) + chr(0x2029) + chr(0xFEFF)  # saltos de línea y BOM
SIN_SALTOS = st.text(st.characters(blacklist_categories=("Cs",), blacklist_characters=SEPARADORES), max_size=40)
SUAVE = settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)


# ------------------------------------------------------------------ lang JSON
@SUAVE
@given(st.dictionaries(TEXTO, TEXTO, max_size=8))
def test_lang_json_ida_y_vuelta_y_utf8(textos: dict[str, str]) -> None:
    datos = lang_json.escribir(textos)
    assert lang_json.leer(datos) == textos
    assert json.loads(datos.decode("utf-8")) == textos  # es JSON válido y UTF-8 puro
    assert not datos.startswith(b"\xef\xbb\xbf")  # sin BOM: el juego no lo quiere


def test_lang_json_guarda_tildes_y_ene_sin_escapar() -> None:
    datos = lang_json.escribir({"a": "¡Ñandú, canción y pingüino!"})
    assert "¡Ñandú, canción y pingüino!".encode() in datos and b"\\u" not in datos


@pytest.mark.parametrize(
    "crudo",
    [
        b'\xef\xbb\xbf{"a": "b"}',  # con BOM
        b'{"a": "b",}',  # coma final
        b'{"a": "b" /* comentario */}',
        b"{'a': 'b'}",  # comillas simples
        b'{"a": "b", "n": 5, "l": [1], "o": {"x": "y"}, "z": null}',  # solo se conservan los textos
    ],
)
def test_lang_json_tolerante(crudo: bytes) -> None:
    assert lang_json.leer(crudo)["a"] == "b"


@pytest.mark.parametrize("crudo", [b"[1, 2]", b'"texto"', b"5"])
def test_lang_json_que_no_es_objeto_falla_con_valueerror(crudo: bytes) -> None:
    with pytest.raises(ValueError, match="no es un objeto"):
        lang_json.leer(crudo)


@pytest.mark.parametrize("crudo", [b"", b"{", b'{"a": ', b"no es json", b"\xff\xfe\x00\x00"])
def test_lang_json_roto_falla_con_valueerror(crudo: bytes) -> None:
    with pytest.raises(ValueError):
        lang_json.leer(crudo)


# ------------------------------------------------------------------ .lang antiguo
@SUAVE
@given(
    st.dictionaries(SIN_SALTOS.filter(lambda k: "=" not in k and not k.startswith("#") and k), SIN_SALTOS, max_size=8)
)
def test_lang_legacy_ida_y_vuelta(textos: dict[str, str]) -> None:
    datos = lang_legacy.escribir(textos)
    assert lang_legacy.leer(datos) == textos
    datos.decode("utf-8")


def test_lang_legacy_detalles() -> None:
    crudo = "﻿# comentario\r\nitem.a=Espada §a%s\r\n\r\nsin_igual\r\nitem.b=a=b=c\nitem.c=\n".encode()
    assert lang_legacy.leer(crudo) == {"item.a": "Espada §a%s", "item.b": "a=b=c", "item.c": ""}
    with pytest.raises(ValueError, match="salto de línea"):
        lang_legacy.escribir({"k": "dos\nlíneas"})
    with pytest.raises(ValueError, match="salto de línea"):
        lang_legacy.escribir({"k=v": "x"})


# ------------------------------------------------------------------ escáneres: nunca fallan con otra cosa que ValueError
@SUAVE
@given(st.text(max_size=120))
def test_escaneres_solo_lanzan_valueerror(texto: str) -> None:
    for escaner in (javascript.escanear, snbt.escanear, json_cadenas.escanear):
        try:
            cadenas = escaner(texto)
        except ValueError:
            continue
        assert isinstance(cadenas, list)


@SUAVE
@given(st.text(alphabet="{}[]\"':,/\\ ab1\n`$()+-*=", max_size=80))
def test_escaneres_con_sintaxis_hostil(texto: str) -> None:
    for escaner in (javascript.escanear, snbt.escanear, json_cadenas.escanear):
        with contextlib.suppress(ValueError):
            escaner(texto)


@SUAVE
@given(st.text(max_size=100))
def test_componentes_y_comandos_no_fallan(texto: str) -> None:
    json_texto.cargar(texto)
    componente.unidades(texto)
    assert componente.reconstruir(texto, {}) == texto  # sin traducciones no cambia nada
    comandos.analizar(texto)
    comandos.analizar("tellraw @a " + texto)
    comandos.analizar("execute as @a run say " + texto)


def test_json_cadenas_unicode_y_escapes() -> None:
    src = '{"a": "ca\\u00f1\\u00f3n \\"x\\" \\n fin", "b": ["\\ud83d\\ude00", "plano"]}'
    cadenas = json_cadenas.escanear(src)
    assert [c.texto for c in cadenas] == ['cañón "x" \n fin', "😀", "plano"]
    nuevo = json_cadenas.reemplazar(src, cadenas, {cadenas[2].inicio: "llano ñ"})
    assert json.loads(nuevo)["b"][1] == "llano ñ" and json.loads(nuevo)["a"] == json.loads(src)["a"]


@SUAVE
@given(TEXTO)
def test_json_cadenas_reemplazo_arbitrario_es_json_valido(texto: str) -> None:
    src = '{"k": "valor", "l": ["x"]}'
    cadenas = json_cadenas.escanear(src)
    nuevo = json_cadenas.reemplazar(src, cadenas, {cadenas[0].inicio: texto, cadenas[1].inicio: texto})
    assert json.loads(nuevo) == {"k": texto, "l": [texto]}


# ------------------------------------------------------------------ JavaScript
@SUAVE
@given(TEXTO, st.sampled_from("'\"`"))
def test_js_escapar_ida_y_vuelta_con_especiales(texto: str, comilla: str) -> None:
    if comilla == "`" and "${" in texto:
        return
    src = f"x.tell({comilla}{javascript.escapar(texto, comilla)}{comilla})\n"
    assert [c.texto for c in javascript.escanear(src)] == [texto]


@pytest.mark.parametrize(
    "src",
    ["x.tell('sin cerrar", 'x.tell("sin cerrar\n")', "x.tell(`sin ${cerrar`)"],
)
def test_js_cadena_sin_cerrar_es_valueerror(src: str) -> None:
    with pytest.raises(ValueError, match="sin cerrar"):
        javascript.escanear(src)


def test_js_crlf_comentarios_regex_y_division() -> None:
    src = "let a = 10 / 2 / 5\r\n// 'no'\r\nlet r = /'x'/g; /* \"no\" */ x.tell('sí ñ')\r\n"
    assert [c.texto for c in javascript.escanear(src)] == ["sí ñ"]


# ------------------------------------------------------------------ SNBT / NBT
def test_snbt_escapes_y_unicode() -> None:
    src = r'{title: "Hola \"mundo\" ñ\n", list: ["a", "b"]}'
    cadenas = snbt.escanear(src)
    nuevo = snbt.reemplazar(src, cadenas, {cadenas[0].inicio: 'Adiós "mundo" ¡ñ!'})
    assert next(c.texto for c in snbt.escanear(nuevo)) == 'Adiós "mundo" ¡ñ!' and '"a", "b"' in nuevo


@pytest.mark.parametrize(
    "datos", [b"", b"\x00", b"\x0a\x00", b"\x1f\x8b\x08garbage", b"\x0a\x00\x00\x08\x00\x01a\xff\xff"]
)
def test_nbt_basura_falla_con_valueerror(datos: bytes) -> None:
    with pytest.raises(ValueError):
        nbt.leer(datos)


@SUAVE
@given(st.binary(max_size=60))
def test_nbt_bytes_cualesquiera_no_revientan(datos: bytes) -> None:
    with contextlib.suppress(ValueError):
        nbt.leer(datos)


@SUAVE
@given(TEXTO)
def test_mutf8_ida_y_vuelta(texto: str) -> None:
    assert nbt.mutf8_decodificar(nbt.mutf8_codificar(texto)) == texto


# ------------------------------------------------------------------ markdown
@SUAVE
@given(st.text(alphabet="abc ñ#-*>`~!\n\r\t[]()$<>=", max_size=120))
def test_markdown_sin_traducir_no_cambia_nada(md: str) -> None:
    lineas, segs = markdown.segmentar(md)
    assert markdown.reconstruir(lineas, segs, {}) == md


def test_markdown_traduce_sin_tocar_codigo_ni_crlf() -> None:
    md = "# Title here\r\n\r\nSome text about iron.\r\n\r\n```\r\ncode stays\r\n```\r\n- list item here\r\n"
    lineas, segs = markdown.segmentar(md)
    trad = {s.texto: "«ES» " + s.texto for s in segs}
    salida = markdown.reconstruir(lineas, segs, trad)
    assert "code stays" in salida and "«ES» Some text about iron." in salida
    assert salida.count("\r\n") == md.count("\r\n")

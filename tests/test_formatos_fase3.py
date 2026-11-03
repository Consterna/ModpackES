import gzip
import io
import json
from pathlib import Path
from typing import Any

import nbtlib  # pyright: ignore[reportMissingTypeStubs]
import pytest
from hypothesis import given
from hypothesis import strategies as st

from traductor_es.formatos import json_cadenas, json_texto, nbt

_TEXTO = st.text(st.characters(blacklist_categories=("Cs",)), max_size=20)
_JSON: Any = st.recursive(
    st.none() | st.booleans() | st.integers() | _TEXTO,
    lambda hijos: st.lists(hijos, max_size=4) | st.dictionaries(_TEXTO, hijos, max_size=4),
    max_leaves=12,
)


@given(_JSON, st.sampled_from([None, 2, 4]))
def test_json_identidad_y_reemplazo(datos: Any, sangria: int | None) -> None:
    src = json.dumps(datos, indent=sangria, ensure_ascii=sangria is None)
    cadenas = json_cadenas.escanear(src)
    assert json_cadenas.reemplazar(src, cadenas, {c.inicio: c.texto for c in cadenas}) == src
    nuevo = json_cadenas.reemplazar(src, cadenas, {c.inicio: "T" + c.texto for c in cadenas})

    def marcar(x: Any) -> Any:
        if isinstance(x, str):
            return "T" + x
        if isinstance(x, list):
            return [marcar(v) for v in x]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(x, dict):
            return {k: marcar(v) for k, v in x.items()}  # pyright: ignore[reportUnknownVariableType]
        return x

    assert json.loads(nuevo) == marcar(datos)


def test_json_rutas() -> None:
    src = '{"display": {"title": "\\"Hola\\"", "description": ["a", "b"]}, "rewards": {"x": {"title": "R"}}}'
    rutas = {c.ruta: c.texto for c in json_cadenas.escanear(src)}
    assert rutas == {
        ("display", "title"): '"Hola"',
        ("display", "description", 0): "a",
        ("display", "description", 1): "b",
        ("rewards", "x", "title"): "R",
    }
    with pytest.raises(ValueError):
        json_cadenas.escanear('{"a": ')


def test_componente_como_cadena_json() -> None:
    assert json_texto.extraer('"Getting Started"', literal=True) == ["Getting Started"]
    assert json_texto.reconstruir('"Getting Started"', {"Getting Started": "Primeros pasos"}, literal=True) == (
        '"Primeros pasos"'
    )
    assert json_texto.extraer('"Una cita"') is None  # sin literal (FTB Quests) es texto normal


# ---------------------------------------------------------------- NBT


@given(st.text(st.characters(blacklist_categories=("Cs",)), max_size=40))
def test_mutf8_ida_y_vuelta(texto: str) -> None:
    assert nbt.mutf8_decodificar(nbt.mutf8_codificar(texto)) == texto


def test_mutf8_como_java() -> None:
    assert nbt.mutf8_codificar("\x00") == b"\xc0\x80"
    assert nbt.mutf8_codificar("😀") == b"\xed\xa0\xbd\xed\xb8\x80"  # dos sustitutos de 3 bytes
    assert nbt.mutf8_codificar("ñ") == "ñ".encode()


def _nbt_de_prueba() -> bytes:
    raiz = nbtlib.File(  # pyright: ignore[reportUnknownMemberType]
        {
            "title": nbtlib.String("Find Redstone"),
            "x": nbtlib.Double(1.5),
            "id": nbtlib.Int(-7),
            "text": nbtlib.List[nbtlib.String](["Line one", "Line two"]),
            "tasks": nbtlib.List[nbtlib.Compound]([nbtlib.Compound({"item": nbtlib.String("minecraft:stone")})]),
            "arr": nbtlib.IntArray([1, 2, 3]),
        }
    )
    buffer = io.BytesIO()
    raiz.write(buffer)  # pyright: ignore[reportUnknownMemberType]
    return gzip.compress(buffer.getvalue(), mtime=0)


def test_nbt_identidad_y_cambios_que_nbtlib_lee() -> None:
    datos = _nbt_de_prueba()
    raiz, compresion = nbt.leer(datos)
    assert compresion == "gzip"
    assert nbt.descomprimir(nbt.escribir(raiz))[0] == nbt.descomprimir(datos)[0]
    textos = {(c.campo, c.texto) for c in nbt.cadenas(raiz)}
    assert ("title", "Find Redstone") in textos and ("text", "Line two") in textos
    for c in list(nbt.cadenas(raiz)):
        if c.campo in ("title", "text"):
            nbt.poner(c, "«ES» " + c.texto + " ñ")  # nbtlib usa UTF-8 normal: los emojis se prueban aparte
    leido: Any = nbtlib.File.parse(io.BytesIO(nbt.descomprimir(nbt.escribir(raiz))[0]))  # pyright: ignore[reportUnknownMemberType]
    assert str(leido["title"]) == "«ES» Find Redstone ñ"
    assert [str(x) for x in leido["text"]] == ["«ES» Line one ñ", "«ES» Line two ñ"]
    assert float(leido["x"]) == 1.5 and int(leido["id"]) == -7 and list(leido["arr"]) == [1, 2, 3]
    assert str(leido["tasks"][0]["item"]) == "minecraft:stone"


def test_nbt_danado() -> None:
    with pytest.raises(ValueError):
        nbt.leer(b"\x0a\x00\x00\x08\x00\x05tit")


CORPUS_112 = Path(__file__).resolve().parent.parent / ".descargas" / "supernova-empires-2" / "config" / "ftbquests"


@pytest.mark.corpus
@pytest.mark.skipif(not CORPUS_112.is_dir(), reason="Falta el corpus descargado")
def test_nbt_real_de_112_coincide_con_nbtlib() -> None:
    for ruta in sorted(CORPUS_112.rglob("*.nbt")):
        datos = ruta.read_bytes()
        raiz, _ = nbt.leer(datos)
        crudo = nbt.descomprimir(datos)[0]
        assert nbt.escribir(raiz, "ninguna") == crudo
        propio: Any = nbtlib.File.parse(io.BytesIO(nbt.escribir(raiz, "ninguna")))  # pyright: ignore[reportUnknownMemberType]
        ajeno: Any = nbtlib.File.parse(io.BytesIO(crudo))  # pyright: ignore[reportUnknownMemberType]
        assert propio == ajeno, ruta.name

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from traductor_es.formatos import json_texto, lang_json, lang_legacy


def test_lang_json_con_comentarios_bom_y_no_textos() -> None:
    crudo = (lang_legacy.BOM + '{\n  // comentario\n  "a": "Hola",\n  "b": 3,\n  "c": "Adiós",\n}').encode()
    assert lang_json.leer(crudo) == {"a": "Hola", "c": "Adiós"}


def test_lang_json_no_objeto() -> None:
    with pytest.raises(ValueError):
        lang_json.leer(b"[1,2]")


_SIN_SUSTITUTOS = st.characters(blacklist_categories=("Cs",))


@given(st.dictionaries(st.text(_SIN_SUSTITUTOS, min_size=1), st.text(_SIN_SUSTITUTOS)))
def test_lang_json_ida_y_vuelta(textos: dict[str, str]) -> None:
    assert lang_json.leer(lang_json.escribir(textos)) == textos


def test_lang_legacy() -> None:
    crudo = b"# comentario\nitem.a.name=Iron Plate\n\nmenu.b=Valor=con igual\nbasura\n"
    assert lang_legacy.leer(crudo) == {"item.a.name": "Iron Plate", "menu.b": "Valor=con igual"}


@given(
    st.dictionaries(
        st.from_regex(r"[a-z][a-z0-9_.]{0,20}", fullmatch=True),
        st.text(alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=(chr(13), chr(10)))),
    )
)
def test_lang_legacy_ida_y_vuelta(textos: dict[str, str]) -> None:
    assert lang_legacy.leer(lang_legacy.escribir(textos)) == textos


def test_lang_legacy_rechaza_saltos() -> None:
    with pytest.raises(ValueError):
        lang_legacy.escribir({"a": "dos\nlíneas"})


def test_componente_json() -> None:
    texto = json.dumps(["", {"text": "Hello", "color": "red", "extra": [{"text": "World"}]}, "plain"])
    assert json_texto.extraer(texto) == ["Hello", "World", "plain"]
    nuevo = json_texto.reconstruir(texto, {"Hello": "Hola", "World": "Mundo"})
    assert json.loads(nuevo) == ["", {"text": "Hola", "color": "red", "extra": [{"text": "Mundo"}]}, "plain"]


def test_no_componentes() -> None:
    for t in ["Hola", "{image:a:b.png}", "{@pagebreak}", "[no json", "{clave.x}"]:
        assert json_texto.extraer(t) is None
        assert json_texto.reconstruir(t, {t: "X"}) == "X"


def test_componente_sin_cambios_queda_identico() -> None:
    texto = '["",{"text":"Hello"}]'
    assert json_texto.reconstruir(texto, {}) == texto

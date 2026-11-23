"""Una traducción hostil no puede salir de su cadena: lo que no es texto queda igual byte a byte.

El motor de traducción es un tercero (o un servidor comprometido): su respuesta puede traer comillas, barras,
saltos de línea, `${…}`, cierres de comentario o de objeto. Al escribirla en SNBT, JSON, JS o .lang, el archivo
resultante debe tener las mismas cadenas en el mismo sitio, con exactamente el texto pedido.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from traductor_es.formatos import javascript, json_cadenas, lang_json, lang_legacy, snbt

#: Piezas que suelen romper un formato si no se escapan.
_PELIGROSAS = [
    '"', "'", "`", "\\", "\n", "\r", "\r\n", "\t", "${", "}", "{", "]", "[", ",", ":", ";", "//", "/*", "*/",
    "\\u0041", "\\n", " ", " ", "\x00", "\x1b", "§", "%s", "$(l)", "</script>", "\\'", '\\"',
]  # fmt: skip
_HOSTIL = st.lists(st.one_of(st.sampled_from(_PELIGROSAS), st.text(max_size=4)), max_size=8).map("".join)
_AJUSTES = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def _sin_cadenas(src: str, tramos: list[tuple[int, int]]) -> str:
    """El código con cada cadena cambiada por un hueco: lo que no es texto."""
    partes: list[str] = []
    ultimo = 0
    for inicio, fin in sorted(tramos):
        partes += [src[ultimo:inicio], "\x00"]
        ultimo = fin
    return "".join([*partes, src[ultimo:]])


# --- SNBT (misiones de FTB Quests) ---------------------------------------------------------------------------------

_SNBT = '{\n\ttitle: "Hola"\n\tdescription: ["Linea uno", "Linea dos"]\n\tsubtitle: \'Sub\'\n\tid: "0A1B"\n}\n'


@_AJUSTES
@given(st.lists(_HOSTIL, min_size=4, max_size=4))
def test_snbt_traduccion_hostil_queda_dentro_de_su_cadena(textos: list[str]) -> None:
    cadenas = snbt.escanear(_SNBT)
    assert len(cadenas) == 5
    nuevos = {c.inicio: t for c, t in zip(cadenas[:4], textos, strict=True)}
    salida = snbt.reemplazar(_SNBT, cadenas, nuevos)
    otra = snbt.escanear(salida)
    assert [c.texto for c in otra] == [*textos, "0A1B"]
    assert [c.campo for c in otra] == [c.campo for c in cadenas]
    tramos_a = [(c.inicio, c.fin) for c in cadenas]
    tramos_b = [(c.inicio, c.fin) for c in otra]
    assert _sin_cadenas(salida, tramos_b) == _sin_cadenas(_SNBT, tramos_a)


# --- JSON (Patchouli, BetterQuesting, lang) ------------------------------------------------------------------------

_JSON = '{\n  "name": "Libro",\n  "pages": [\n    {"type": "text", "text": "Pagina"},\n    "Suelto"\n  ]\n}\n'


@_AJUSTES
@given(st.lists(_HOSTIL, min_size=3, max_size=3))
def test_json_traduccion_hostil_sigue_siendo_json_valido_y_con_las_mismas_claves(textos: list[str]) -> None:
    cadenas = [c for c in json_cadenas.escanear(_JSON) if c.texto in ("Libro", "Pagina", "Suelto")]
    salida = json_cadenas.reemplazar(_JSON, cadenas, {c.inicio: t for c, t in zip(cadenas, textos, strict=True)})
    datos = json.loads(salida)
    assert datos == {"name": textos[0], "pages": [{"type": "text", "text": textos[1]}, textos[2]]}


@_AJUSTES
@given(st.dictionaries(_HOSTIL, _HOSTIL, max_size=6))
def test_lang_json_ida_y_vuelta_con_textos_hostiles(textos: dict[str, str]) -> None:
    assert lang_json.leer(lang_json.escribir(textos)) == textos


@_AJUSTES
@example({"\ufeff": ""})  # la clave queda primera: no se puede leer como la marca del archivo
@given(st.dictionaries(_HOSTIL, _HOSTIL, max_size=6))
def test_lang_legacy_no_deja_meter_lineas_nuevas(textos: dict[str, str]) -> None:
    """Un valor con salto de línea no puede crear claves nuevas en el .lang: o se rechaza o vuelve igual."""
    try:
        datos = lang_legacy.escribir(textos)
    except ValueError:
        return
    leido = lang_legacy.leer(datos)
    assert set(leido) <= set(textos)
    for clave, valor in leido.items():
        assert valor == textos[clave]


def test_lang_legacy_clave_con_almohadilla_se_pierde_al_releer() -> None:
    """Caracterización (H-007): una clave que empieza por «#» se escribe pero al leerla es un comentario."""
    datos = lang_legacy.escribir({"#clave": "valor", "otra": "x"})
    assert lang_legacy.leer(datos) == {"otra": "x"}


# --- JavaScript (KubeJS) -------------------------------------------------------------------------------------------


def _script(comillas: list[str]) -> str:
    a, b, c = comillas
    return (
        "// comentario 'no' es texto\n"
        f"ServerEvents.tick(e => {{\n  e.player.tell({a}Hola{a});\n"
        f"  let x = {b}Adios{b} + 1 / 2; /* fin */\n"
        f"  e.server.runCommand({c}say Bienvenido{c})\n}})\n"
    )


@_AJUSTES
@given(st.lists(st.sampled_from(['"', "'", "`"]), min_size=3, max_size=3), st.lists(_HOSTIL, min_size=3, max_size=3))
def test_js_traduccion_hostil_no_cambia_el_codigo(comillas: list[str], textos: list[str]) -> None:
    # En una plantilla `…` el formato deja pasar «${» a propósito (el original puede traer `${nombre}`): lo que
    # impide meter código nuevo es `scripts._seguro`, que se prueba abajo.
    textos = [t.replace("${", "$ {") if q == "`" else t for q, t in zip(comillas, textos, strict=True)]
    src = _script(comillas)
    cadenas = javascript.escanear(src)
    assert [c.texto for c in cadenas] == ["Hola", "Adios", "say Bienvenido"]
    salida = javascript.reemplazar(src, cadenas, {c.inicio: t for c, t in zip(cadenas, textos, strict=True)})
    otra = javascript.escanear(salida)
    assert [c.texto for c in otra] == textos
    assert [(c.funcion, c.receptor) for c in otra] == [(c.funcion, c.receptor) for c in cadenas]
    tramos_a = [(c.inicio, c.fin) for c in cadenas]
    tramos_b = [(c.inicio, c.fin) for c in otra]
    assert _sin_cadenas(salida, tramos_b) == _sin_cadenas(src, tramos_a)


@pytest.mark.parametrize(
    ("original", "traduccion", "seguro"),
    [
        ("Hola ${nombre}", "Hola ${nombre}", True),
        ("Hola ${nombre}", "Hola ${nombre} ${java.lang.System.exit(0)}", False),
        ("Hola", "Hola ${x}", False),
        ("Hola ${a}", "Hola", False),
    ],
)
def test_scripts_no_acepta_codigo_nuevo_en_una_plantilla(original: str, traduccion: str, seguro: bool) -> None:
    from traductor_es.modulos.scripts import _seguro  # pyright: ignore[reportPrivateUsage]

    (cadena,) = javascript.escanear(f"p.tell(`{original}`)")
    assert _seguro(cadena, traduccion) is seguro


@pytest.mark.parametrize("comilla", ['"', "'", "`"])
@pytest.mark.parametrize("texto", ["${process.exit()}", "\\${x}", "a`b", "</script>", " ", "\\", "\r\n"])
def test_js_escapar_y_des_escapar_son_inversos(comilla: str, texto: str) -> None:
    assert javascript.des_escapar(javascript.escapar(texto, comilla)) == texto


def test_lang_legacy_clave_con_marca_al_principio() -> None:
    datos = lang_legacy.escribir({"\ufeffa": "x"})
    assert datos == "#\n\ufeffa=x\n".encode()
    assert lang_legacy.leer(datos) == {"\ufeffa": "x"}

import pytest
from hypothesis import given
from hypothesis import strategies as st

from traductor_es.formatos.snbt import des_escapar, escanear, escapar, reemplazar

CAPITULO = r"""{
	default_hide_dependency_lines: false
	filename: "getting_started"
	id: "61E9F8FCB1C14B9B"
	quests: [
		{
			description: [
				"Here are some \"useful\" commands!"
				""
				"{image:khazenor:textures/a.png width:100 height:50 align:1}"
				'single \'quoted\' text'
				"keep raw \n escapes"
			]
			id: "38597CE6BB709431"
			tasks: [{ count: 16L id: "356D013846BD6115" title: "Any #minecraft:logs" type: "item" }]
			title: "Info: Remember to /sethome!"
			x: 0.5d
		}
	]
	quest.ABC.title: "Clave con puntos"
	"quoted.key": "Valor"
}
"""


def test_campos_detectados() -> None:
    cadenas = escanear(CAPITULO)
    por_campo = {(c.campo, c.texto) for c in cadenas}
    assert ("description", 'Here are some "useful" commands!') in por_campo
    assert ("description", "single 'quoted' text") in por_campo
    assert ("title", "Info: Remember to /sethome!") in por_campo
    assert ("title", "Any #minecraft:logs") in por_campo
    assert ("quest.ABC.title", "Clave con puntos") in por_campo
    assert ("quoted.key", "Valor") in por_campo
    assert ("id", "61E9F8FCB1C14B9B") in por_campo
    assert all(c.texto != "quoted.key" for c in cadenas)  # las claves no son valores


def test_reemplazo_identidad_es_byte_a_byte() -> None:
    cadenas = escanear(CAPITULO)
    assert reemplazar(CAPITULO, cadenas, {c.inicio: c.texto for c in cadenas}) == CAPITULO


def test_reemplazo_solo_toca_lo_pedido() -> None:
    cadenas = escanear(CAPITULO)
    titulo = next(c for c in cadenas if c.texto.startswith("Info"))
    nuevo = reemplazar(CAPITULO, cadenas, {titulo.inicio: 'Recuerda usar "/sethome"'})
    assert 'title: "Recuerda usar \\"/sethome\\""' in nuevo
    assert nuevo.replace('Recuerda usar \\"/sethome\\"', "Info: Remember to /sethome!") == CAPITULO


def test_escape_crudo_se_conserva() -> None:
    cadenas = escanear(CAPITULO)
    raw = next(c for c in cadenas if c.texto.startswith("keep raw"))
    nuevo = reemplazar(CAPITULO, cadenas, {raw.inicio: raw.texto.replace("keep raw", "conservar")})
    assert '"conservar \\n escapes"' in nuevo


def test_cadena_sin_cerrar_falla() -> None:
    with pytest.raises(ValueError):
        escanear('{ title: "abierta }')


@given(st.text(), st.sampled_from(['"', "'"]))
def test_escapar_y_desescapar_son_inversos(texto: str, comilla: str) -> None:
    if "\ue000" in texto:
        return
    assert des_escapar(escapar(texto, comilla), comilla) == texto


_valor = st.text(alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\ue000"), max_size=30)


@given(
    st.lists(st.tuples(st.from_regex(r"[a-z_]{1,8}", fullmatch=True), _valor, st.sampled_from(['"', "'"])), max_size=8)
)
def test_documento_generado_ida_y_vuelta(pares: list[tuple[str, str, str]]) -> None:
    lineas = [f"\t{k}: {q}{escapar(v, q)}{q}" for k, v, q in pares]
    src = "{\n" + "\n".join(lineas) + "\n}\n"
    cadenas = escanear(src)
    assert [c.texto for c in cadenas] == [v for _, v, _ in pares]
    assert [c.campo for c in cadenas] == [k for k, _, _ in pares]
    assert reemplazar(src, cadenas, {c.inicio: c.texto for c in cadenas}) == src
    traducido = reemplazar(src, cadenas, {c.inicio: "T" + c.texto for c in cadenas})
    assert [c.texto for c in escanear(traducido)] == ["T" + v for _, v, _ in pares]

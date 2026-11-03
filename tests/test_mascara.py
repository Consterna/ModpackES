from hypothesis import given
from hypothesis import strategies as st

from traductor_es.nucleo.mascara import ESCAPE_CRUDO, desenmascarar, enmascarar, es_traducible, separar_bordes

CODIGOS = [
    "%s",
    "%1$s",
    "%d",
    "%.1f",
    "%%",
    "§a",
    "&c",
    "$(l)",
    "$()",
    "$(l:basics/mana)",
    "{image:mod:tex.png width:100}",
    "{@pagebreak}",
    "{0}",
    "{player_name}",
    "<NEWLINE>",
    '<ItemLink id="ae2:controller" />',
    "<br>",
    "](entry://basics)",
    "![logo](logo.png)",
    "https://example.com/a?b=1",
    "\\n",
    "\n",
    "/home",
    "minecraft:stone",
    "create:item/wrench",
    ESCAPE_CRUDO + "t",
]


def test_cada_codigo_se_protege_y_vuelve_igual() -> None:
    for codigo in CODIGOS:
        texto = f"Usa {codigo} ahora"
        m = enmascarar(texto)
        assert codigo not in m.texto or codigo in ("{0}",), codigo  # el código no llega al traductor
        assert m.tokens, codigo
        assert desenmascarar(m.texto, m.tokens) == texto


def test_porcentaje_normal_y_barras_no_se_protegen() -> None:
    for texto in ["50% more", "and/or", "w/e", "R&D team?"]:
        m = enmascarar(texto)
        assert "⟦" not in m.texto or texto == "R&D team?"
        assert desenmascarar(m.texto, m.tokens) == texto


def test_rechaza_marcador_perdido_repetido_o_inventado() -> None:
    m = enmascarar("Cuesta %s y %d")
    assert desenmascarar("Cuesta ⟦0⟧", m.tokens) is None
    assert desenmascarar("Cuesta ⟦0⟧ ⟦0⟧ y ⟦1⟧", m.tokens) is None
    assert desenmascarar("Cuesta ⟦0⟧ y ⟦1⟧ ⟦2⟧", m.tokens) is None
    assert desenmascarar("Cuesta ⟦1⟧ y ⟦0⟧", m.tokens) == "Cuesta %d y %s"


def test_rechaza_corchetes_sueltos() -> None:
    m = enmascarar("Hola %s")
    assert desenmascarar("Hola ⟦0⟧ ⟦", m.tokens) is None


def test_es_traducible() -> None:
    assert es_traducible("Iron Ingot")
    assert es_traducible("Ñu")
    assert not es_traducible("%s: %d")
    assert not es_traducible("minecraft:stone")
    assert not es_traducible("   ")
    assert not es_traducible("123 / 456")
    assert not es_traducible("{image:x:y.png}")


def test_separar_bordes() -> None:
    assert separar_bordes("  Hola  ") == ("  ", "Hola", "  ")
    assert separar_bordes("Hola") == ("", "Hola", "")
    assert separar_bordes("   ") == ("   ", "", "")


@given(st.text())
def test_ida_y_vuelta_sin_cambios_para_cualquier_texto(texto: str) -> None:
    m = enmascarar(texto)
    if "⟦" in texto or "⟧" in texto:
        return  # texto que ya trae los corchetes de marcador: no aplica
    assert desenmascarar(m.texto, m.tokens) == texto


@given(st.lists(st.sampled_from(CODIGOS), min_size=1, max_size=6), st.text(alphabet="abc xyz", max_size=20))
def test_reordenar_marcadores_es_valido(codigos: list[str], relleno: str) -> None:
    texto = relleno.join(codigos)
    m = enmascarar(texto)
    invertido = " ".join(f"⟦{i}⟧" for i in reversed(range(len(m.tokens))))
    restaurado = desenmascarar(invertido, m.tokens)
    assert restaurado is not None
    assert sorted(restaurado.split(" ")) == sorted(" ".join(m.tokens).split(" "))

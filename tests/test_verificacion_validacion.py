"""Casos límite de las reglas de calidad y de la revisión automática."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from traductor_es.validacion.calidad import revisar_glosario, validar
from traductor_es.validacion.revision import ResumenRevision, interpretar_veredicto

SUAVE = settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)


@pytest.mark.parametrize(
    ("original", "traduccion", "motivo"),
    [
        ("Iron Plate", "Placa de hierro", None),
        ("Iron Plate", "", "vacía"),
        ("Iron Plate", "   \t ", "vacía"),
        ("One line", "Dos\nlíneas", "salto de línea nuevo"),
        ("One\nline", "Una\nlínea", None),
        ("A long enough original text here", "x", "largo raro"),
        ("Short", "Un texto absurdamente largo para algo tan corto, de verdad que sí lo es", None),
        (
            "You can use the tool to break the stone and then place it with your hand",
            "You can use the tool to break the stone and then place it with your hand",
            "sin traducir",
        ),
        ("⟦0⟧ and ⟦1⟧", "⟦0⟧ y ⟦1⟧", None),
        ("Ñandú ¡Ágüita! cañón", "Ñandú ¡Ágüita! cañón", None),  # nombres propios iguales: no es error
        ("日本語のテキスト", "日本語のテキスト", None),
    ],
)
def test_validar_casos(original: str, traduccion: str, motivo: str | None) -> None:
    assert validar(original, traduccion) == motivo


@SUAVE
@given(st.text(max_size=200), st.text(max_size=200))
def test_validar_nunca_falla(original: str, traduccion: str) -> None:
    resultado = validar(original, traduccion)
    assert resultado is None or isinstance(resultado, str)


def test_revisar_glosario_con_regex_y_utf8() -> None:
    glosario = {"C++": "C++", "(Test)": "(Prueba)", "Wheat": "Trigo", "Ñu": "Ñu"}
    traducciones = {
        "Use C++ here": "Usa C++ aquí",
        "A (Test) item": "Un objeto",
        "Wheat bread": "Pan de cebada",
        "Ñu is Ñu": "Ñu es Ñu",
    }
    r = revisar_glosario(traducciones, glosario, list(glosario))
    assert r.inconsistentes == {"(Test)": 1, "Wheat": 1}
    assert "Términos del glosario no respetados" in str(r)
    assert str(revisar_glosario({}, glosario, [])) == "Glosario respetado en todas las traducciones."


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("OK", None),
        ("ok, todo bien", None),
        ("", None),
        ("grave|exactitud|cambia el sentido", ("grave", "exactitud", "cambia el sentido")),
        ("Crítica | Terminología | falta el glosario", ("critica", "terminologia", "falta el glosario")),
        ("grave|exactitud", None),  # falta la explicación
        ("enorme|exactitud|x", None),  # gravedad desconocida
        ("grave|ortografia|x", None),  # categoría desconocida
        ("grave|estilo|" + "x" * 1000, ("grave", "estilo", "x" * 300)),  # se recorta
        ("grave|estilo|con | barras | extra", ("grave", "estilo", "con | barras | extra")),
    ],
)
def test_veredicto(valor: str, esperado: tuple[str, str, str] | None) -> None:
    assert interpretar_veredicto(valor) == esperado


@SUAVE
@given(st.text(max_size=100))
def test_veredicto_nunca_falla(valor: str) -> None:
    interpretar_veredicto(valor)


def test_resumen_de_revision_suma_y_se_lee() -> None:
    a = ResumenRevision(revisados=3, marcados={"exactitud": 1}, leves=1, corregidos=1)
    a.sumar(ResumenRevision(revisados=2, marcados={"exactitud": 1, "estilo": 2}, leves=0, corregidos=2))
    assert a.revisados == 5 and a.marcados == {"exactitud": 2, "estilo": 2} and a.corregidos == 3
    assert "4 con errores graves" in str(a) and "ninguno con errores graves" in str(ResumenRevision(revisados=7))

"""La máscara protege los códigos y nada más: «R&D» y una frase entre llaves llegan al modelo como texto."""

from __future__ import annotations

import pytest

from traductor_es.nucleo.mascara import desenmascarar, enmascarar, sin_formato


@pytest.mark.parametrize(
    ("texto", "tokens"),
    [
        ("Defeat the &4Arachnarch", ("&4",)),
        ("&c&lDanger!", ("&c", "&l")),  # códigos encadenados
        ("§c&lMix", ("§c", "&l")),
        ("Salt &bPepper", ("&b",)),
        ("the &6Wrench&r to rotate", ("&6", "&r")),  # el cierre va pegado a la palabra
        ("WRENCH&r done", ("&r",)),
        ("{image:mod:textures/a.png width:50}", ("{image:mod:textures/a.png width:50}",)),
        ("{@pagebreak}", ("{@pagebreak}",)),
        ("{0} items", ("{0}",)),
        ("Press {key.jump}", ("{key.jump}",)),
    ],
)
def test_los_codigos_se_protegen(texto: str, tokens: tuple[str, ...]) -> None:
    m = enmascarar(texto)
    assert m.tokens == tokens
    assert desenmascarar(m.texto, m.tokens) == texto


@pytest.mark.parametrize("texto", ["R&D Lab", "Q&A", "B&B Inn", "AT&T", "{the quick brown fox}"])
def test_lo_que_no_es_codigo_queda_como_texto(texto: str) -> None:
    assert enmascarar(texto).tokens == ()


def test_sin_formato_no_se_come_letras() -> None:
    assert sin_formato("R&D and &4Red") == "R&D and Red"

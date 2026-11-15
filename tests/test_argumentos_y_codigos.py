"""Errores que rompen el juego: argumentos al revés, escapes rotos, formatos fuera de orden y códigos inventados."""

from __future__ import annotations

import itertools

from hypothesis import given
from hypothesis import strategies as st

from traductor_es.formatos import javascript
from traductor_es.motores.base import Lote
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import (
    codigos_inventados,
    desenmascarar,
    enmascarar,
    pares_en_orden,
    posicionar_argumentos,
)
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor

# ---------------------------------------------------------------- argumentos


def _restaurar(original: str, crudo: str) -> str | None:
    m = enmascarar(original)
    posicionados = posicionar_argumentos(crudo, m.tokens)
    assert posicionados is not None
    return desenmascarar(crudo, posicionados[0])


def test_argumentos_al_reves_se_numeran() -> None:
    # «%s was slain by %s»: el modelo puso primero al asesino; sin numerar, el juego invertiría a los dos
    assert _restaurar("%s was slain by %s", "⟦1⟧ mató a ⟦0⟧") == "%2$s mató a %1$s"


def test_en_orden_no_se_tocan() -> None:
    assert _restaurar("%s was slain by %s", "⟦0⟧ fue asesinado por ⟦1⟧") == "%s fue asesinado por %s"


def test_con_formato_y_ya_numerados() -> None:
    assert _restaurar("Gave %d %s", "⟦1⟧ ×⟦0⟧") == "%2$s ×%1$d"
    assert _restaurar("%2$s by %1$s", "⟦1⟧ de ⟦0⟧") == "%1$s de %2$s"  # numerados: el orden es libre


def test_mezcla_de_numerados_y_sin_numero_no_se_arregla() -> None:
    assert posicionar_argumentos("⟦1⟧ ⟦0⟧", enmascarar("%s and %2$s").tokens) is None


@given(st.integers(min_value=2, max_value=4).flatmap(lambda n: st.permutations(list(range(n)))))
def test_cualquier_orden_lleva_cada_valor_a_su_sitio(orden: list[int]) -> None:
    n = len(orden)
    original = " ".join(f"v{i} %s" for i in range(n))
    crudo = " ".join(f"v{i} ⟦{i}⟧" for i in orden)  # palabra y valor se mueven juntos
    restaurado = _restaurar(original, crudo)
    assert restaurado is not None
    if orden == list(range(n)):
        assert restaurado == original
    else:
        for i in range(n):  # el valor i del original sigue junto a su palabra, con su número
            assert f"v{i} %{i + 1}$s" in restaurado


def test_todas_las_permutaciones_de_tres() -> None:
    for orden in itertools.permutations(range(3)):
        crudo = " ".join(f"⟦{i}⟧" for i in orden)
        restaurado = _restaurar("%s %s %s", crudo)
        esperado = " ".join(f"%{i + 1}$s" for i in orden) if list(orden) != [0, 1, 2] else "%s %s %s"
        assert restaurado == esperado


# ---------------------------------------------------------------- pares de formato y códigos inventados


def test_pares_de_formato() -> None:
    tokens = enmascarar("the §aIron§r §bSword§r").tokens
    assert pares_en_orden("la ⟦2⟧Espada⟦3⟧ de ⟦0⟧Hierro⟦1⟧", tokens)  # mover un par entero vale
    assert not pares_en_orden("la ⟦1⟧Espada⟦0⟧ de ⟦2⟧Hierro⟦3⟧", tokens)  # el cierre antes de su apertura no
    libro = enmascarar("Press $(k:use) to $(l)open$() the $(item)book$().").tokens
    assert pares_en_orden("Pulsa ⟦0⟧ para ⟦1⟧abrir⟦2⟧ el ⟦3⟧libro⟦4⟧.", libro)
    assert not pares_en_orden("Pulsa ⟦0⟧ para ⟦2⟧abrir⟦1⟧ el ⟦3⟧libro⟦4⟧.", libro)


def test_codigos_inventados() -> None:
    tokens = enmascarar("Deals %s damage").tokens
    assert not codigos_inventados("Hace %s de daño", tokens)
    assert codigos_inventados("Hace §c%s de daño", tokens)  # el modelo agregó un color
    assert codigos_inventados("Hace %s de daño %s", tokens)  # y aquí un argumento
    assert not codigos_inventados("Hace %s de daño (50 %%)", tokens, porcentajes=1)


# ---------------------------------------------------------------- escapes \uXXXX


def test_escapes_unicode_visibles_se_decodifican_y_los_de_control_se_protegen() -> None:
    cadena = javascript.escanear("p.tell('\\u00a7cWarning: \\u00e9xito \\u0007')")[0]
    assert cadena.texto.startswith("§cWarning: éxito ")
    m = enmascarar(cadena.texto)
    assert m.texto.startswith("⟦0⟧Warning: éxito ") and m.tokens[0] == "§c"
    assert len(m.tokens) == 2 and m.tokens[1].endswith("u0007")  # el de control, entero


# ---------------------------------------------------------------- en el traductor


class _Fijo:
    nombre = "fijo"

    def __init__(self, respuesta: str) -> None:
        self.respuesta = respuesta

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        return {e.id: self.respuesta for e in lote.entradas}


def _traducir(respuesta: str, texto: str, ambito: str = "ui") -> tuple[dict[str, str], dict[str, str]]:
    with Memoria(":memory:") as mem:
        r = Traductor(_Fijo(respuesta), mem, Glosario()).traducir([texto], ambito)
    return r.traducciones, r.rechazados


def test_en_un_archivo_de_idioma_se_numeran() -> None:
    traducciones, _ = _traducir("⟦1⟧ mató a ⟦0⟧ con su espada", "%s was slain by %s with a sword")
    assert traducciones == {"%s was slain by %s with a sword": "%2$s mató a %1$s con su espada"}


def test_en_un_script_no_se_puede_y_queda_en_ingles() -> None:
    traducciones, rechazados = _traducir("⟦1⟧ mató a ⟦0⟧ con su espada", "%s was slain by %s with a sword", "script")
    assert traducciones == {} and rechazados == {"%s was slain by %s with a sword": "orden de argumentos"}


def test_un_porcentaje_suelto_se_escapa() -> None:
    traducciones, _ = _traducir("Aumenta un 50 % el daño de ⟦0⟧", "Increases %s damage by half")
    assert traducciones == {"Increases %s damage by half": "Aumenta un 50 %% el daño de %s"}

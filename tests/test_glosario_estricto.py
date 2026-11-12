"""El glosario deja de ser una sugerencia: si falta un término, el texto se reintenta con la instrucción explícita."""

from __future__ import annotations

from traductor_es.motores.base import Lote
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.validacion.calidad import terminos_faltantes

GLOSARIO = {"Iron Ingot": "Lingote de hierro", "Chest": "Cofre"}


def test_un_termino_que_sale_no_falta() -> None:
    assert terminos_faltantes("Put an Iron Ingot in the Chest", "Pon un lingote de hierro en el cofre", GLOSARIO) == {}


def test_tolera_plural_tildes_y_mayusculas() -> None:
    assert terminos_faltantes("Two Iron Ingot here", "Dos Lingotes De Hierro aquí", GLOSARIO) == {}
    assert terminos_faltantes("A Chest", "Un COFRE", {"Chest": "Cofre"}) == {}
    assert terminos_faltantes("A Furnace", "Un horno", {"Furnace": "Hornó"}) == {}


def test_un_termino_ausente_se_detecta() -> None:
    faltan = terminos_faltantes("Put an Iron Ingot in the Chest", "Pon una barra de hierro en el baúl", GLOSARIO)
    assert faltan == {"Iron Ingot": "Lingote de hierro", "Chest": "Cofre"}


def test_un_termino_que_no_esta_en_el_original_no_se_exige() -> None:
    assert terminos_faltantes("Hello there", "Hola", GLOSARIO) == {}


def test_un_termino_igual_en_los_dos_idiomas_no_se_exige() -> None:
    assert terminos_faltantes("A Creeper", "Una criatura verde", {"Creeper": "Creeper"}) == {}


def test_solo_cuenta_la_palabra_completa() -> None:
    assert terminos_faltantes("Chestplate", "Peto", {"Chest": "Cofre"}) == {}


class _Olvidadizo:
    """Ignora el glosario la primera vez y lo respeta cuando el aviso lo menciona."""

    nombre = "olvidadizo"

    def __init__(self) -> None:
        self.lotes: list[Lote] = []

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.lotes.append(lote)
        return {
            e.id: "Pon el lingote de hierro en el cofre"
            if "estos términos del glosario" in e.pista
            else "Pon la barra de hierro en el baúl"
            for e in lote.entradas
        }


def test_el_texto_sin_el_termino_se_reintenta_con_el_aviso() -> None:
    glosario = Glosario()
    glosario.agregar_pares({"Iron Ingot": "Iron Ingot", "Chest": "Chest"}, GLOSARIO)
    motor = _Olvidadizo()
    with Memoria(":memory:") as mem:
        r = Traductor(motor, mem, glosario).traducir(["Put the Iron Ingot in the Chest"], "ui")
    assert r.traducciones == {"Put the Iron Ingot in the Chest": "Pon el lingote de hierro en el cofre"}
    pista = motor.lotes[-1].entradas[0].pista
    assert "«Iron Ingot» = «Lingote de hierro»" in pista and "«Chest» = «Cofre»" in pista


def test_si_tras_el_reintento_sigue_sin_el_termino_se_acepta() -> None:
    class _Terco(_Olvidadizo):
        def traducir_lote(self, lote: Lote) -> dict[str, str]:
            self.lotes.append(lote)
            return {e.id: "Pon la barra de hierro en el baúl" for e in lote.entradas}

    glosario = Glosario()
    glosario.agregar_pares({"Iron Ingot": "Iron Ingot"}, {"Iron Ingot": "Lingote de hierro"})
    with Memoria(":memory:") as mem:
        r = Traductor(_Terco(), mem, glosario).traducir(["Put the Iron Ingot here"], "ui")
    assert r.traducciones == {"Put the Iron Ingot here": "Pon la barra de hierro en el baúl"}

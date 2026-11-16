"""Una palabra suelta de un mod que el español escribe en minúscula no recibe mayúscula a mitad de frase."""

from __future__ import annotations

from traductor_es.motores.base import Lote
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor


class _Fijo:
    nombre = "fijo"

    def __init__(self, salida: dict[str, str]) -> None:
        self.salida = salida

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        return {e.id: self.salida[e.texto] for e in lote.entradas}


def _glosario() -> Glosario:
    g = Glosario()
    g.agregar_pares({"a": "Gear", "b": "Arcanite"}, {"a": "Engranaje", "b": "Arcanita"}, fuente="mod")
    g.aprender_usos({"z": "Craft a gear"}, {"z": "Fabrica un engranaje"})  # el español lo escribe en minúscula
    return g


def test_un_sustantivo_comun_no_recibe_mayuscula() -> None:
    texto = "Put the Gear and the Arcanite in the machine"
    motor = _Fijo({texto: "Pon el engranaje y la arcanita en la máquina"})
    with Memoria(":memory:") as m:
        r = Traductor(motor, m, _glosario()).traducir([texto], "mision")
    assert r.traducciones[texto] == "Pon el engranaje y la Arcanita en la máquina"  # nombre propio del mod


def test_el_glosario_del_usuario_conserva_sus_mayusculas() -> None:
    g = _glosario()
    g.fijar({"Gear": "Engranaje"})
    texto = "Put the Gear in the machine"
    with Memoria(":memory:") as m:
        r = Traductor(_Fijo({texto: "Pon el engranaje en la máquina"}), m, g).traducir([texto], "mision")
    assert r.traducciones[texto] == "Pon el Engranaje en la máquina"

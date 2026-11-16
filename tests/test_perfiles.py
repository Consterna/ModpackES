"""Perfiles de calidad: verificador a ciegas en dos órdenes, corrección de lo dudoso y consenso de lo corto."""

from __future__ import annotations

from collections.abc import Callable

from traductor_es.motores.base import Lote
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import ECONOMICO, EQUILIBRADO, MAXIMO, MOTIVO_INCIERTO, Traductor
from traductor_es.proceso import Informe, InformeModulo
from traductor_es.validacion.verificacion import gana_la_nueva


class _Motor:
    """Traduce con `traducir(texto, n)` (n = cuántas veces se pidió ese texto) y juzga con `juzgar(a, b)`."""

    nombre = "falso"

    def __init__(self, traducir: Callable[[str, int], str], juzgar: Callable[[str, str], str]) -> None:
        self._traducir, self._juzgar = traducir, juzgar
        self.veces: dict[str, int] = {}
        self.comparaciones = 0

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        if lote.tarea == "comparar":
            self.comparaciones += len(lote.entradas)
            return {e.id: self._juzgar(e.traduccion, e.alternativa) for e in lote.entradas}
        salida: dict[str, str] = {}
        for e in lote.entradas:
            n = self.veces.get(e.texto, 0)
            self.veces[e.texto] = n + 1
            salida[e.id] = self._traducir(e.texto, n)
        return salida


def _prefiere(palabra: str) -> Callable[[str, str], str]:
    return lambda a, b: "A" if palabra in a else "B" if palabra in b else "igual"


def test_la_nueva_gana_solo_si_el_juez_la_prefiere_en_los_dos_ordenes() -> None:
    casos = [("Cost: 64", "", "Costo: 32", "Costo: 64")]
    assert gana_la_nueva(_Motor(lambda t, n: t, _prefiere("64")), "es_mx", "ui", casos) == [True]
    assert gana_la_nueva(_Motor(lambda t, n: t, lambda a, b: "A"), "es_mx", "ui", casos) == [False]  # sesgo de orden
    assert gana_la_nueva(_Motor(lambda t, n: t, lambda a, b: "igual"), "es_mx", "ui", casos) == [False]


def _cifras(texto: str, n: int) -> str:
    """La primera vez cambia la cifra (duda del control de calidad); al corregir, la pone bien."""
    return "Cuesta 32 monedas" if n == 0 else "Cuesta 64 monedas"


def test_equilibrado_corrige_lo_dudoso_si_el_juez_lo_prefiere() -> None:
    motor = _Motor(_cifras, _prefiere("64"))
    with Memoria(":memory:") as m:
        r = Traductor(motor, m, Glosario(), perfil=EQUILIBRADO).traducir(["Costs 64 coins"], "ui")
        assert r.traducciones == {"Costs 64 coins": "Cuesta 64 monedas"}
        assert not r.dudosos and r.corregidos == 1
        assert m.obtener("Costs 64 coins", "es_mx", "ui") == "Cuesta 64 monedas"  # y quedó «ok» en la memoria


def test_equilibrado_deja_la_primera_si_el_juez_no_prefiere_la_correccion() -> None:
    motor = _Motor(_cifras, _prefiere("32"))
    with Memoria(":memory:") as m:
        r = Traductor(motor, m, Glosario(), perfil=EQUILIBRADO).traducir(["Costs 64 coins"], "ui")
        assert r.traducciones == {"Costs 64 coins": "Cuesta 32 monedas"}
        assert "Costs 64 coins" in r.dudosos and r.corregidos == 0
        assert m.obtener("Costs 64 coins", "es_mx", "ui", "*") == "Cuesta 32 monedas"


def test_economico_no_pide_nada_mas() -> None:
    motor = _Motor(_cifras, _prefiere("64"))
    with Memoria(":memory:") as m:
        r = Traductor(motor, m, Glosario(), perfil=ECONOMICO).traducir(["Costs 64 coins"], "ui")
    assert r.traducciones == {"Costs 64 coins": "Cuesta 32 monedas"} and motor.comparaciones == 0


def test_maximo_elige_por_mayoria_entre_tres_traducciones() -> None:
    opciones = {"Iron Gear": ["Engrane de hierro", "Engranaje de hierro", "Engranaje de hierro"]}
    motor = _Motor(lambda t, n: opciones[t][n], _prefiere("Engranaje"))
    with Memoria(":memory:") as m:
        r = Traductor(motor, m, Glosario(), perfil=MAXIMO).traducir(["Iron Gear"], "ui")
        assert r.traducciones == {"Iron Gear": "Engranaje de hierro"} and r.elegidos == 1
        assert not r.dudosos
        assert m.obtener("Iron Gear", "es_mx", "ui") == "Engranaje de hierro"


def test_maximo_sin_mayoria_elige_por_rangos_y_marca_incierto() -> None:
    # La tercera tiene una duda del control de calidad («usted»); entre las otras dos, gana la más parecida al resto
    opciones = {"Place the block": ["Pon el bloque", "Coloca el bloque", "Coloque el bloque"]}
    motor = _Motor(lambda t, n: opciones[t][n], lambda a, b: "igual")
    with Memoria(":memory:") as m:
        r = Traductor(motor, m, Glosario(), perfil=MAXIMO).traducir(["Place the block"], "ui")
    assert r.traducciones["Place the block"] in ("Pon el bloque", "Coloca el bloque")
    assert r.dudosos == {"Place the block": MOTIVO_INCIERTO}


def test_maximo_no_toca_los_textos_largos() -> None:
    largo = "This machine slowly crushes ores into dust over time"
    motor = _Motor(
        lambda t, n: "Esta máquina tritura despacio los minerales hasta hacerlos polvo", lambda a, b: "igual"
    )
    with Memoria(":memory:") as m:
        Traductor(motor, m, Glosario(), perfil=MAXIMO).traducir([largo], "ui")
    assert motor.veces[largo] == 1


def test_el_costo_estimado_sube_con_el_perfil() -> None:
    informe = Informe(modulos=[InformeModulo("mods", "Mods", "", 100, 100, 5000)])
    economico = informe.costo("gemini-3.8-flash", False, calidad=ECONOMICO)
    equilibrado = informe.costo("gemini-3.8-flash", False, calidad=EQUILIBRADO)
    maximo = informe.costo("gemini-3.8-flash", False, calidad=MAXIMO)
    assert economico is not None and equilibrado is not None and maximo is not None
    assert economico < equilibrado < maximo

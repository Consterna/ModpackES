import threading
from collections.abc import Iterator
from typing import Any

import pytest

from traductor_es.motores.base import Cancelado, ErrorFatal, Lote, Motor
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor

_ABIERTAS: list[Memoria] = []


def memoria() -> Memoria:
    m = Memoria(":memory:")
    _ABIERTAS.append(m)
    return m


@pytest.fixture(autouse=True)
def _cerrar_memorias() -> Iterator[None]:
    yield
    while _ABIERTAS:
        _ABIERTAS.pop().cerrar()


def nuevo(motor: Motor | None = None, **kw: Any) -> Traductor:
    return Traductor(motor or Simulador(), memoria(), Glosario(), **kw)


def test_traduce_conserva_bordes_y_codigos() -> None:
    t = nuevo()
    r = t.traducir(["  Hello %s  ", "§aGreen", "%s", "minecraft:stone"], "ui")
    assert r.traducciones == {"  Hello %s  ": "  «ES» Hello %s  ", "§aGreen": "«ES» §aGreen"}


def test_memoria_evita_segunda_llamada() -> None:
    motor = Simulador()
    t = nuevo(motor)
    t.traducir(["Iron Ingot", "Iron Ingot", " Iron Ingot"], "ui")
    assert sum(len(lote.entradas) for lote in motor.lotes_recibidos) == 1
    r = t.traducir(["Iron Ingot"], "ui")
    assert r.enviados == 0 and r.traducciones == {"Iron Ingot": "«ES» Iron Ingot"}
    assert t.pendientes(["Iron Ingot"], "mision") == ["Iron Ingot"]  # otro ámbito, otra traducción


def test_glosario_exacto_y_relevante() -> None:
    motor = Simulador()
    g = Glosario()
    g.agregar_pares({"a": "Crafting Table", "b": "Oak"}, {"a": "Mesa de trabajo", "b": "Roble"})
    t = Traductor(motor, memoria(), g)
    r = t.traducir(["Crafting Table", "Place a crafting table here"], "mision")
    assert r.traducciones["Crafting Table"] == "Mesa de trabajo"
    assert motor.lotes_recibidos[0].glosario == {"Crafting Table": "Mesa de trabajo"}


def test_glosario_fijo_manda_y_palabra_completa() -> None:
    g = Glosario()
    g.agregar_pares({"a": "Oak"}, {"a": "Roble"})
    g.fijar({"Oak": "Encino"})
    assert g.exacto("Oak") == "Encino"
    assert g.relevantes(["Oakland city"]) == {}
    assert g.relevantes(["an oak log"]) == {"Oak": "Encino"}


def test_termino_del_usuario_gana_sobre_la_memoria() -> None:
    """Regresión: si el texto ya estaba en la memoria, el término del usuario nunca se aplicaba."""
    g = Glosario()
    g.agregar_pares({"a": "Oak"}, {"a": "Roble"})  # nombre oficial: pierde contra la memoria
    m = memoria()
    m.guardar({"Copper Gear": "Engranaje cobrizo", "Oak": "Roble viejo"}, "es_mx", "ui", "gemini")
    t = Traductor(Simulador(), m, g)
    g.fijar({"Copper Gear": "Engranaje de cobre"})
    r = t.traducir(["Copper Gear", "Oak"], "ui")
    assert r.traducciones == {"Copper Gear": "Engranaje de cobre", "Oak": "Roble viejo"}
    assert r.enviados == 0


def test_danados_se_reintentan_y_si_siguen_mal_se_descartan() -> None:
    motor = Simulador(danar=1.0)
    t = nuevo(motor)
    r = t.traducir(["Cost %s coins", "Plain text"], "ui")
    assert "Cost %s coins" not in r.traducciones
    assert r.rechazados == {"Cost %s coins": "códigos dañados"}
    assert r.traducciones["Plain text"] == "«ES» Plain text"  # sin códigos, el daño no aplica
    assert len(motor.lotes_recibidos) == 2  # ronda normal + reintento


def test_validador_externo() -> None:
    def largo(original: str, traduccion: str) -> str | None:
        return "muy largo" if len(traduccion) > 3 * len(original) else None

    t = nuevo(validador=largo)
    r = t.traducir(["Hi"], "ui")
    assert r.traducciones == {} and r.rechazados == {"Hi": "muy largo"}


class Explota:
    nombre = "explota"

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        raise ErrorFatal("clave inválida")


def test_error_fatal_se_propaga() -> None:
    with pytest.raises(ErrorFatal):
        nuevo(Explota()).traducir(["Hello"], "ui")


def test_cancelar() -> None:
    ev = threading.Event()

    class Cancela:
        nombre = "c"

        def traducir_lote(self, lote: Lote) -> dict[str, str]:
            ev.set()
            return {e.id: "x" + e.texto for e in lote.entradas}

    t = Traductor(Cancela(), memoria(), Glosario(), cancelar=ev, limite_entradas=1, hilos=1)
    with pytest.raises(Cancelado):
        t.traducir([f"Text {i}" for i in range(20)], "ui")


def test_progreso_y_lotes() -> None:
    avances: list[tuple[int, int]] = []
    motor = Simulador()

    def avanzar(hechos: int, total: int) -> None:
        avances.append((hechos, total))

    t = nuevo(motor, progreso=avanzar, limite_entradas=3)
    t.traducir([f"Word number {i}" for i in range(10)], "ui")
    assert len(motor.lotes_recibidos) == 4
    assert avances[0] == (0, 10) and avances[-1] == (10, 10)


def test_dialecto_desconocido() -> None:
    with pytest.raises(ValueError):
        nuevo(dialecto="pt_br")


def test_memoria_persistente(tmp_path: object) -> None:
    from pathlib import Path

    ruta = Path(str(tmp_path)) / "m.db"
    with Memoria(ruta) as m:
        m.guardar({"Hello": "Hola"}, "es_mx", "ui", "sim")
    with Memoria(ruta) as m:
        assert m.obtener("Hello", "es_mx", "ui") == "Hola"
        assert m.obtener("Hello", "es_es", "ui") is None
        m.olvidar("Hello", "es_mx", "ui")
        assert m.cantidad() == 0

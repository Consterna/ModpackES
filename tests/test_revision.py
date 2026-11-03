"""Revisión automática: marca, rehace lo grave y nunca empeora un texto válido ni toca correcciones."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes import vanilla
from traductor_es.motores.base import Entrada, Lote
from traductor_es.motores.instrucciones import sistema, usuario
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.proceso import Informe, InformeModulo, Proceso
from traductor_es.validacion import revision
from traductor_es.validacion.calidad import validar

from . import fabrica


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    m = Memoria(":memory:")
    yield m
    m.cerrar()


def test_interpretar_veredicto() -> None:
    assert revision.interpretar_veredicto("OK") is None
    assert revision.interpretar_veredicto("ok, sin errores") is None
    assert revision.interpretar_veredicto("grave|terminología|usa «Cofre»") == ("grave", "terminologia", "usa «Cofre»")
    assert revision.interpretar_veredicto("Crítica | exactitud | cambia el sentido") == (
        "critica", "exactitud", "cambia el sentido",
    )  # fmt: skip
    assert revision.interpretar_veredicto("grave|inventada|x") is None  # categoría desconocida
    assert revision.interpretar_veredicto("algo raro") is None


def test_instrucciones_de_revision() -> None:
    lote = Lote(
        (Entrada("0", "Craft a ⟦0⟧Chest", "misión", "Fabrica un ⟦0⟧cofre"),), "mision", "español", {"Chest": "Cofre"}
    )
    revisar = Lote(lote.entradas, lote.ambito, lote.dialecto, lote.glosario, tarea="revisar")
    assert "revisor profesional" in sistema(revisar) and "gravedad|categoría" in sistema(revisar)
    assert "revisor" not in sistema(lote)
    datos = json.loads(usuario(revisar))
    assert datos["pares"]["0"] == {
        "original": "Craft a ⟦0⟧Chest",
        "traduccion": "Fabrica un ⟦0⟧cofre",
        "contexto": "misión",
    }
    assert datos["glosario"] == {"Chest": "Cofre"} and "textos" not in datos


def test_marca_y_rehace_lo_grave(memoria: Memoria) -> None:
    motor = Simulador(marcar=frozenset({"«ES» Find iron ore"}))
    t = Traductor(motor, memoria, Glosario(), validador=validar)
    r = t.traducir(["Find iron ore", "Build a house"], "mision")
    assert set(r.nuevas) == {"Find iron ore", "Build a house"}
    resumen = revision.revisar_y_corregir(t, r.nuevas, "mision", {})
    assert (resumen.revisados, resumen.marcados, resumen.corregidos) == (2, {"exactitud": 1}, 1)
    assert memoria.obtener("Find iron ore", "es_mx", "mision") == "«ES*» Find iron ore"
    assert memoria.obtener("Build a house", "es_mx", "mision") == "«ES» Build a house"
    pedido = next(lote for lote in motor.lotes_recibidos if lote.tarea == "revisar")
    assert {e.traduccion for e in pedido.entradas} == {"«ES» Find iron ore", "«ES» Build a house"}
    rehecho = motor.lotes_recibidos[-1].entradas[0]
    assert "marcado por la prueba" in rehecho.pista and "«ES» Find iron ore" in rehecho.pista
    assert "1 quedaron corregidos" in str(resumen)


class _RehaceMal(Simulador):
    """Marca todo y, al rehacer, devuelve algo que no pasa las reglas (vacío)."""

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        if lote.tarea == "revisar":
            return {e.id: "critica|fluidez|mal" for e in lote.entradas}
        if any("revisión" in e.pista for e in lote.entradas):
            return {e.id: "" for e in lote.entradas}
        return super().traducir_lote(lote)


def test_si_lo_rehecho_no_pasa_las_reglas_queda_lo_anterior(memoria: Memoria) -> None:
    t = Traductor(_RehaceMal(), memoria, Glosario(), validador=validar)
    r = t.traducir(["Find iron ore"], "mision")
    resumen = revision.revisar_y_corregir(t, r.nuevas, "mision", {})
    assert resumen.marcados == {"fluidez": 1} and resumen.corregidos == 0
    assert memoria.obtener("Find iron ore", "es_mx", "mision") == "«ES» Find iron ore"


def test_las_correcciones_del_usuario_no_se_revisan(memoria: Memoria) -> None:
    motor = Simulador(marcar=frozenset({"Encuentra hierro"}))
    memoria.corregir("Find iron ore", "es_mx", "Encuentra hierro")
    t = Traductor(motor, memoria, Glosario())
    resumen = revision.revisar_y_corregir(t, {"Find iron ore": "Encuentra hierro"}, "mision", {})
    assert resumen.revisados == 0 and motor.lotes_recibidos == []


def test_lo_leve_se_cuenta_pero_no_se_rehace(memoria: Memoria) -> None:
    class Leve(Simulador):
        def traducir_lote(self, lote: Lote) -> dict[str, str]:
            if lote.tarea == "revisar":
                return {e.id: "leve|estilo|podría sonar mejor" for e in lote.entradas}
            return super().traducir_lote(lote)

    t = Traductor(Leve(), memoria, Glosario())
    r = t.traducir(["Find iron ore"], "mision")
    resumen = revision.revisar_y_corregir(t, r.nuevas, "mision", {})
    assert (resumen.leves, resumen.marcados, resumen.corregidos) == (1, {}, 0)


def test_proceso_con_revision_solo_en_misiones_y_libros(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
    juego = fabrica.prism(tmp_path, "1.20.1")
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text('{ title: "Find iron ore" }', encoding="utf-8")
    script = juego / "kubejs" / "server_scripts" / "s.js"
    script.parent.mkdir(parents=True)
    script.write_text("player.tell('Find iron ore')\n", encoding="utf-8")
    motor = Simulador(marcar=frozenset({"«ES» Find iron ore"}))
    with Memoria(tmp_path / "m.db") as memoria, Proceso(juego, motor, memoria=memoria, revisar=True) as p:
        informe = p.ejecutar(activar=False)
    assert "«ES*» Find iron ore" in capitulo.read_text("utf-8")
    assert script.read_text("utf-8") == "player.tell('«ES» Find iron ore')\n"  # los scripts no se revisan
    assert informe.revision_automatica is not None and informe.revision_automatica.corregidos == 1
    revisados = [lote for lote in motor.lotes_recibidos if lote.tarea == "revisar"]
    assert len(revisados) == 1 and revisados[0].ambito == "mision"


def test_el_costo_con_revision_es_mayor_solo_por_misiones_y_libros() -> None:
    con_misiones = Informe([InformeModulo("misiones", "M", "", 100, 100, 50_000)])
    solo_mods = Informe([InformeModulo("mods", "Mods", "", 100, 100, 50_000)])
    for informe in (con_misiones, solo_mods):
        assert informe.costo("gemini-3.8-flash", False) is not None
    sin = con_misiones.costo("gemini-3.8-flash", False) or 0
    con = con_misiones.costo("gemini-3.8-flash", False, revisar=True) or 0
    assert 1.2 * sin < con < 1.7 * sin
    assert solo_mods.costo("gemini-3.8-flash", False, revisar=True) == solo_mods.costo("gemini-3.8-flash", False)

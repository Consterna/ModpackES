"""Correcciones del usuario: mandan sobre la memoria y el motor, y no pueden romper los códigos."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Coincidencia, Memoria, codigos_iguales
from traductor_es.nucleo.traductor import Traductor


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    m = Memoria(":memory:")
    yield m
    m.cerrar()


def test_la_correccion_gana_en_todos_los_ambitos(memoria: Memoria) -> None:
    memoria.guardar({"Copper Gear": "Engranaje cobrizo"}, "es_mx", "ui", "gemini")
    memoria.guardar({"Copper Gear": "Engranaje cobrizo"}, "es_mx", "mision", "gemini")
    memoria.corregir("Copper Gear", "es_mx", "Engranaje de cobre")
    motor = Simulador()
    t = Traductor(motor, memoria, Glosario())
    assert t.traducir(["Copper Gear"], "ui").traducciones == {"Copper Gear": "Engranaje de cobre"}
    assert t.traducir(["  Copper Gear"], "mision").traducciones == {"  Copper Gear": "  Engranaje de cobre"}
    assert t.traducir(["Copper Gear"], "libro").traducciones == {"Copper Gear": "Engranaje de cobre"}
    assert motor.lotes_recibidos == []  # nada de eso se paga


def test_la_correccion_es_por_variante(memoria: Memoria) -> None:
    memoria.corregir("Ore", "es_es", "Mena")
    assert memoria.correccion("Ore", "es_es") == "Mena" and memoria.correccion("Ore", "es_mx") is None


def test_una_correccion_que_rompe_codigos_se_rechaza(memoria: Memoria) -> None:
    with pytest.raises(ValueError, match="códigos"):
        memoria.corregir("Deals %s damage", "es_mx", "Hace daño")
    with pytest.raises(ValueError, match="vacía"):
        memoria.corregir("Hello", "es_mx", "   ")
    memoria.corregir("§aDeals %s damage", "es_mx", "§aHace %s de daño")
    assert memoria.correccion("§aDeals %s damage", "es_mx") == "§aHace %s de daño"


def test_codigos_iguales_admite_otro_orden() -> None:
    assert codigos_iguales("%1$s of %2$s", "%2$s de %1$s")
    assert not codigos_iguales("§a%s", "%s")


def test_quitar_correccion_vuelve_a_la_memoria(memoria: Memoria) -> None:
    memoria.guardar({"Oak": "Roble"}, "es_mx", "ui", "gemini")
    memoria.corregir("Oak", "es_mx", "Encino")
    memoria.quitar_correccion("Oak", "es_mx")
    t = Traductor(Simulador(), memoria, Glosario())
    assert t.traducir(["Oak"], "ui").traducciones == {"Oak": "Roble"}


def test_buscar_en_original_y_traduccion_sin_comodines(memoria: Memoria) -> None:
    memoria.guardar({"Iron Ingot": "Lingote de hierro", "100% done": "100 % listo"}, "es_mx", "ui", "g")
    memoria.guardar({"Iron Ingot": "Lingote de hierro"}, "es_mx", "mision", "g")
    memoria.corregir("Iron Ingot", "es_mx", "Lingote de fierro")
    memoria.corregir("Only corrected", "es_mx", "Solo corregido")
    assert memoria.buscar("hierro", "es_mx") == [
        Coincidencia("Iron Ingot", "mision", "Lingote de fierro", True),
        Coincidencia("Iron Ingot", "ui", "Lingote de fierro", True),
    ]
    assert [c.origen for c in memoria.buscar("0% d", "es_mx")] == ["100% done"]
    assert memoria.buscar("_", "es_mx") == []  # «_» no es comodín
    vacia = memoria.buscar("", "es_mx")
    assert {c.origen for c in vacia} == {"Iron Ingot", "Only corrected"} and all(c.corregida for c in vacia)


def test_una_memoria_vieja_gana_la_tabla_nueva_sin_perder_nada(tmp_path: Path) -> None:
    ruta = tmp_path / "memoria.db"
    db = sqlite3.connect(ruta)
    db.execute(
        "CREATE TABLE traducciones (origen TEXT NOT NULL, dialecto TEXT NOT NULL, ambito TEXT NOT NULL, "
        "traduccion TEXT NOT NULL, motor TEXT NOT NULL, fecha TEXT NOT NULL, PRIMARY KEY (origen, dialecto, ambito))"
    )
    db.execute("INSERT INTO traducciones VALUES ('Oak', 'es_mx', 'ui', 'Roble', 'gemini', '2026-11-01')")
    db.commit()
    db.close()
    with Memoria(ruta) as m:
        assert m.obtener("Oak", "es_mx", "ui") == "Roble"
        m.corregir("Oak", "es_mx", "Encino")
    with Memoria(ruta) as m:
        assert m.correccion("Oak", "es_mx") == "Encino" and m.cantidad() == 1

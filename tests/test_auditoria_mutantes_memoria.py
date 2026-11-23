"""Bordes de la memoria de traducciones (`nucleo/memoria.py`): cada prueba detecta una mutación que antes sobrevivía
(`logs/fase-03/mutacion_memoria.log`, 76,6 %)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from traductor_es.nucleo.memoria import Coincidencia, Fila, Memoria


def test_migrar_una_memoria_del_esquema_1_guarda_una_copia(tmp_path: Path) -> None:
    ruta = tmp_path / "memoria.db"
    with sqlite3.connect(ruta) as db:
        db.execute(
            "CREATE TABLE traducciones (origen TEXT, dialecto TEXT, ambito TEXT, traduccion TEXT, motor TEXT, fecha TEXT,"
            " PRIMARY KEY (origen, dialecto, ambito))"
        )
        db.execute("INSERT INTO traducciones VALUES ('Gear', 'es_mx', 'ui', 'Engranaje', 'gemini', '2026-01-01')")
    db.close()
    with Memoria(ruta) as m:
        assert m.obtener("Gear", "es_mx", "ui", "otro-pack") == "Engranaje"  # pasa al pack «*» con calidad «ok»
    assert (tmp_path / "memoria.db.v1.bak").is_file()


def test_la_calidad_se_guarda_cortada_a_200_caracteres() -> None:
    with Memoria(":memory:") as m:
        m.guardar({"Gear": "Engranaje"}, "es_mx", "ui", "gemini", "p", {"Gear": "x" * 300})
        fila = m.fila("Gear", "es_mx", "ui", "p")
        assert fila is not None and fila[1] == "x" * 200
        m.importar([Fila("Rod", "ui", "Vara", "gemini", "y" * 300)], "es_mx", "p")
        fila = m.fila("Rod", "es_mx", "ui", "p")
        assert fila is not None and fila[1] == "y" * 200


def test_filas_solo_devuelve_las_que_existen() -> None:
    with Memoria(":memory:") as m:
        m.guardar({"Gear": "Engranaje"}, "es_mx", "ui", "gemini")
        filas = m.filas([("Gear", "ui"), ("Missing", "ui")], "es_mx")
    assert filas == [Fila("Gear", "ui", "Engranaje", "gemini", "ok")]


def test_buscar_respeta_el_tope_y_marca_las_correcciones() -> None:
    with Memoria(":memory:") as m:
        m.guardar({f"Gear {i:03d}": f"Engranaje {i:03d}" for i in range(250)}, "es_mx", "ui", "gemini")
        assert len(m.buscar("gear", "es_mx")) == 200
        assert len(m.buscar("gear", "es_mx", limite=7)) == 7
        m.corregir("Gear 000", "es_mx", "Engranaje cero")
        primera = m.buscar("Gear 000", "es_mx")
        assert primera == [Coincidencia("Gear 000", "ui", "Engranaje cero", True)]
    assert Coincidencia("a", "ui", "b").corregida is False


def test_recientes_respeta_el_tope() -> None:
    with Memoria(":memory:") as m:
        m.guardar({f"T{i}": f"E{i}" for i in range(10)}, "es_mx", "ui", "gemini")
        assert len(m.recientes("es_mx")) == 10
        assert len(m.recientes("es_mx", limite=3)) == 3

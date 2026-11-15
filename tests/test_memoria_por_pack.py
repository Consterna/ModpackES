"""Memoria con pack y calidad: migración sin pérdidas, lo dudoso no viaja entre packs y lo viejo se revalida."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from traductor_es.motores.base import Lote
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor


def _memoria_v1(ruta: Path) -> None:
    db = sqlite3.connect(ruta)
    db.execute(
        "CREATE TABLE traducciones (origen TEXT NOT NULL, dialecto TEXT NOT NULL, ambito TEXT NOT NULL, "
        "traduccion TEXT NOT NULL, motor TEXT NOT NULL, fecha TEXT NOT NULL, PRIMARY KEY (origen, dialecto, ambito))"
    )
    db.execute("INSERT INTO traducciones VALUES ('Hello', 'es_mx', 'ui', 'Hola', 'gemini', '2026-01-01')")
    db.commit()
    db.close()


def test_la_migracion_conserva_todo_y_guarda_una_copia(tmp_path: Path) -> None:
    ruta = tmp_path / "memoria.sqlite"
    _memoria_v1(ruta)
    with Memoria(ruta) as m:
        assert m.obtener("Hello", "es_mx", "ui", "Cualquier pack") == "Hola"  # lo viejo vale en todos los packs
        assert m.cantidad() == 1
        assert m._db.execute("PRAGMA user_version").fetchone()[0] == 2  # pyright: ignore[reportPrivateUsage]
    assert (tmp_path / "memoria.sqlite.v1.bak").is_file()
    with Memoria(ruta) as m:  # abrirla otra vez no vuelve a migrar
        assert m.obtener("Hello", "es_mx", "ui") == "Hola"


def test_lo_dudoso_de_un_pack_no_se_usa_en_otro() -> None:
    with Memoria(":memory:") as m:
        m.guardar({"Gear": "Engranaje"}, "es_mx", "ui", "g", "A")
        m.guardar({"Lead": "Correa"}, "es_mx", "ui", "g", "A", {"Lead": "terminología: «Lead»"})
        assert m.obtener("Lead", "es_mx", "ui", "A") == "Correa"  # en su pack, sí
        assert m.obtener("Lead", "es_mx", "ui", "B") is None  # en otro, se traduce de nuevo
        assert m.obtener("Gear", "es_mx", "ui", "B") == "Engranaje"  # lo que quedó bien viaja
        m.guardar({"Gear": "Rueda"}, "es_mx", "ui", "g", "B")
        assert m.obtener("Gear", "es_mx", "ui", "A") == "Engranaje"  # cada pack prefiere lo suyo
        assert m.cantidad() == 2  # el mismo texto en dos packs cuenta una vez
        assert len(m.buscar("Gear", "es_mx")) == 1


class _Contador:
    nombre = "contador"

    def __init__(self, respuestas: dict[str, str]) -> None:
        self.respuestas = respuestas
        self.pedidos: list[str] = []

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.pedidos += [e.texto for e in lote.entradas]
        return {e.id: self.respuestas.get(e.texto, e.texto) for e in lote.entradas}


def test_el_nombre_del_juego_manda_sobre_la_memoria() -> None:
    glosario = Glosario()
    glosario.agregar_pares({"k": "Iron Ingot"}, {"k": "Lingote de hierro"}, fuente="minecraft", oficial=True)
    with Memoria(":memory:") as m:
        m.guardar({"Iron Ingot": "Lingote de Hierro"}, "es_mx", "ui", "g")
        t = Traductor(_Contador({}), m, glosario)
        assert t.conocidas(["Iron Ingot"], "ui") == {"Iron Ingot": "Lingote de hierro"}


def test_lo_que_la_memoria_tiene_como_bueno_se_revalida_con_el_glosario_de_hoy() -> None:
    glosario = Glosario()
    glosario.fijar({"Wrench": "Llave inglesa"})
    texto = "Use the Wrench on it"
    with Memoria(":memory:") as m:
        m.guardar({texto: "Usa la herramienta en él"}, "es_mx", "ui", "g")  # de antes del término
        motor = _Contador({texto: "Usa la Llave inglesa en él"})
        r = Traductor(motor, m, glosario).traducir([texto], "ui")
        assert motor.pedidos == [texto]
        assert r.traducciones == {texto: "Usa la Llave inglesa en él"}


def test_lo_aceptado_con_dudas_en_el_mismo_pack_no_se_vuelve_a_pedir() -> None:
    glosario = Glosario()
    glosario.fijar({"Wrench": "Llave inglesa"})
    texto = "Use the Wrench on it"
    with Memoria(":memory:") as m:
        m.guardar({texto: "Usa la herramienta"}, "es_mx", "ui", "g", "A", {texto: "terminología: «Wrench»"})
        motor = _Contador({})
        Traductor(motor, m, glosario, pack="A").traducir([texto], "ui")
        assert motor.pedidos == []


def test_los_terminos_de_un_texto_son_los_mismos_que_relevantes() -> None:
    glosario = Glosario()
    glosario.agregar_pares(
        {"a": "Iron Ingot", "b": "Iron", "c": "Furnace", "d": "Blast Furnace"},
        {"a": "Lingote de hierro", "b": "Hierro", "c": "Horno", "d": "Alto horno"},
        fuente="minecraft",
        oficial=True,
    )
    for texto in ("Smelt an Iron Ingot in a Blast Furnace", "&4Furnace", "Nothing here", "iron and furnaces"):
        assert glosario.terminos_en(texto) == glosario.relevantes([texto])

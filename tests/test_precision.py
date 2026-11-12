"""Mejoras de precisión: contexto por texto, ejemplos parecidos, términos repetidos y textos sin traducir."""

from __future__ import annotations

import json
from pathlib import Path

from traductor_es.modulos.base import Pieza, reunir_pistas
from traductor_es.modulos.mods import Mods, tipo_de_clave
from traductor_es.motores.base import Entrada, Lote
from traductor_es.motores.instrucciones import sistema, usuario
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo import terminos
from traductor_es.nucleo.ejemplos import Ejemplos
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor

# ------------------------------------------------------------------ 1. contexto por texto


def test_el_tipo_se_deduce_de_la_clave() -> None:
    assert tipo_de_clave("item.create.wrench") == "nombre de un objeto"
    assert tipo_de_clave("block.create.cogwheel") == "nombre de un bloque"
    assert tipo_de_clave("item.create.wrench.tooltip") == "descripción o tooltip de un objeto"
    assert tipo_de_clave("item.mod.music_disc_x") == "nombre de un disco de música"
    assert tipo_de_clave("advancements.mod.root.title") == "logro"
    assert tipo_de_clave("mod.cosa.rara") == ""


def test_la_pista_de_un_mod_dice_el_origen_y_el_tipo() -> None:
    assert Mods.pista("create", "item.create.wrench") == "create: item.create.wrench · nombre de un objeto"
    assert Mods.pista("mod", "algo.raro") == "mod: algo.raro"


def test_un_texto_con_varias_claves_junta_sus_pistas() -> None:
    piezas = [Pieza("Open", "a: gui.open"), Pieza("Open", "b: key.open"), Pieza("Open", "a: gui.open"), Pieza("Close")]
    pistas = reunir_pistas(piezas)
    assert pistas == {"Open": "a: gui.open | b: key.open"}
    muchas = [Pieza("X", f"m: k{i}") for i in range(10)]
    assert reunir_pistas(muchas)["X"].count("|") == 2  # como mucho 3 pistas


def test_las_instrucciones_explican_el_contexto_y_los_ejemplos() -> None:
    lote = Lote((Entrada("0", "Playing", "mod: item.x.music_disc · nombre de un disco de música"),), "ui", "español")
    texto = sistema(lote)
    assert "contexto" in texto and "ejemplos" in texto and "se traduce" in texto


# ------------------------------------------------------------------ 2. ejemplos parecidos


def test_los_ejemplos_traen_lo_parecido_y_no_el_propio_texto() -> None:
    e = Ejemplos()
    e.agregar_pares(
        {
            "Moon Berries Pie": "Pastel de bayas lunares",
            "Moon Berries Jam": "Mermelada de bayas lunares",
            "Iron Sword of Doom": "Espada de hierro del destino",
            "Totally Unrelated Thing": "Cosa sin relación",
        }
    )
    elegidos = e.parecidos(["Moon Berries Tart", "Moon Berries Pie"])
    assert "Moon Berries Jam" in elegidos
    assert "Moon Berries Pie" not in elegidos  # es uno de los textos del lote
    assert "Totally Unrelated Thing" not in elegidos


def test_los_ejemplos_ignoran_textos_con_codigos_o_sin_cambio() -> None:
    e = Ejemplos()
    e.agregar_pares({"Press §aE§r to open": "Pulsa §aE§r para abrir", "Same text here": "Same text here"})
    e.agregar_pares({"Cost %s coins": "Cuesta %s monedas", "Good Honey Jar": "Tarro de miel"})
    assert len(e) == 1


def test_los_ejemplos_respetan_el_limite_de_largo() -> None:
    e = Ejemplos()
    e.agregar_pares({f"Moon Berries Thing {i}": f"Cosa de bayas lunares {i}" for i in range(50)})
    elegidos = e.parecidos(["Moon Berries Pie"], cantidad=3)
    assert len(elegidos) == 3


def test_el_motor_recibe_ejemplos_de_lo_ya_traducido() -> None:
    motor = Simulador()
    ejemplos = Ejemplos()
    ejemplos.agregar_pares({"Moon Berries Jam": "Mermelada de bayas lunares"})
    with Memoria(":memory:") as mem:
        Traductor(motor, mem, Glosario(), ejemplos=ejemplos).traducir(["Moon Berries Pie"], "mision")
    assert motor.lotes_recibidos[0].ejemplos == {"Moon Berries Jam": "Mermelada de bayas lunares"}


def test_los_ejemplos_van_al_pedido_solo_si_hay() -> None:
    sin = Lote((Entrada("0", "Hello"),), "ui", "español")
    con = Lote((Entrada("0", "Hello"),), "ui", "español", ejemplos={"Hi there": "Hola"})
    assert "ejemplos" not in json.loads(usuario(sin))
    assert json.loads(usuario(con))["ejemplos"] == {"Hi there": "Hola"}


# ------------------------------------------------------------------ 3. términos repetidos


def test_se_detectan_los_terminos_que_se_repiten_en_los_nombres() -> None:
    nombres = [f"Moon Berries {x}" for x in ("Pie", "Jam", "Tart", "Juice")] + ["Iron Sword", "Hello there you"]
    encontrados = terminos.repetidos(nombres)
    assert "Moon Berries" in encontrados
    assert "Moon" not in encontrados and "Berries" not in encontrados  # siempre van juntos: se prefiere el largo
    assert "Iron Sword" not in encontrados


def test_los_terminos_se_traducen_primero_y_se_fijan_en_el_glosario() -> None:
    motor = Simulador()
    nombres = [f"Moon Berries {x}" for x in ("Pie", "Jam", "Tart", "Juice")]
    glosario = Glosario()
    with Memoria(":memory:") as mem:
        Traductor(motor, mem, glosario).traducir(nombres, "ui")
    assert glosario.exacto("Moon Berries") == "«ES» Moon Berries"
    primer = {e.texto for e in motor.lotes_recibidos[0].entradas}
    assert primer == {"Moon Berries"}  # el término va solo en la primera ronda
    siguientes = motor.lotes_recibidos[1].glosario
    assert siguientes.get("Moon Berries") == "«ES» Moon Berries"


def test_los_terminos_solo_se_unifican_en_textos_de_mods() -> None:
    motor = Simulador()
    nombres = [f"Moon Berries {x}" for x in ("Pie", "Jam", "Tart", "Juice")]
    with Memoria(":memory:") as mem:
        Traductor(motor, mem, Glosario()).traducir(nombres, "mision")
    assert len(motor.lotes_recibidos) == 1


# ------------------------------------------------------------------ 4. textos que vuelven sin traducir


class _Terco:
    """Devuelve igual al original lo que está en `iguales`, a menos que el aviso diga que lo traduzca."""

    nombre = "terco"

    def __init__(self, obedece: bool) -> None:
        self.obedece = obedece
        self.lotes: list[Lote] = []

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.lotes.append(lote)
        return {
            e.id: (f"ES {e.texto}" if self.obedece and "igual al original" in e.pista else e.texto)
            for e in lote.entradas
        }


def test_un_nombre_devuelto_igual_se_reintenta_con_un_aviso() -> None:
    motor = _Terco(obedece=True)
    with Memoria(":memory:") as mem:
        r = Traductor(motor, mem, Glosario()).traducir(["Magic Wand"], "mision")
    assert r.traducciones == {"Magic Wand": "ES Magic Wand"}
    assert "igual al original" in motor.lotes[-1].entradas[0].pista


def test_si_sigue_igual_tras_el_reintento_se_acepta() -> None:
    motor = _Terco(obedece=False)
    with Memoria(":memory:") as mem:
        r = Traductor(motor, mem, Glosario()).traducir(["Create Cobblemon"], "mision")
        assert r.traducciones == {"Create Cobblemon": "Create Cobblemon"}
        assert mem.obtener("Create Cobblemon", "es_mx", "mision") == "Create Cobblemon"  # no se repite en la próxima


def test_una_palabra_o_un_texto_ya_en_espanol_no_se_reintenta() -> None:
    motor = _Terco(obedece=False)
    with Memoria(":memory:") as mem:
        Traductor(motor, mem, Glosario()).traducir(["Botania", "Bolsa de tela"], "mision")
    assert len(motor.lotes) == 1


def test_la_app_manda_las_pistas_de_todas_las_claves(tmp_path: Path) -> None:
    """Proceso (lo que usan la ventana y la línea de comandos) junta las pistas igual que `reunir_pistas`."""
    from traductor_es.proceso import Proceso

    from . import fabrica

    juego = fabrica.prism(tmp_path, "1.20.1")
    textos = {"gui.m.open": "Open the gate", "key.m.open": "Open the gate"}
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", textos))
    motor = Simulador()
    with Memoria(":memory:") as mem, Proceso(juego, motor, grupos=["mods"], memoria=mem) as p:
        p.ejecutar(activar=False)
    pista = next(e.pista for lote in motor.lotes_recibidos for e in lote.entradas if e.texto == "Open the gate")
    assert "gui.m.open" in pista and "key.m.open" in pista

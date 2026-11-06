"""Mensajes de chat: comandos `tellraw`/`say` en scripts de KubeJS, y logros y funciones de `kubejs/data`."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import comandos
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.datos import Datos
from traductor_es.modulos.scripts import ScriptsKubeJS
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo

from . import fabrica

SCRIPT = r"""ServerEvents.commandRegistry(event => {})
PlayerEvents.loggedIn(event => {
  event.server.runCommandSilent('tellraw @a {"text":"Welcome to the village!","color":"gold"}')
  event.server.runCommand("title @a actionbar {\"text\":\"Market opens soon\"}")
  event.server.runCommand('say The festival begins')
  event.server.runCommand(`execute as @a run tellraw @s ["",{"text":"Hello ${event.player.username}"}]`)
  event.server.runCommandSilent('title @a times 10 70 20')
  event.server.runCommandSilent('give @p minecraft:stone 2')
  event.server.runCommandSilent('tellraw @a {text:"snbt not touched"}')
})
"""


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


@pytest.mark.parametrize(
    ("texto", "prefijo", "cuerpo", "es_json"),
    [
        ('tellraw @a {"text":"Hi"}', "tellraw @a ", '{"text":"Hi"}', True),
        ('/tellraw @a[distance=..5, tag=x] ["Hi"]', "/tellraw @a[distance=..5, tag=x] ", '["Hi"]', True),
        ('title @s subtitle {"text":"Hi"}', "title @s subtitle ", '{"text":"Hi"}', True),
        ("say Hello there", "say ", "Hello there", False),
        ("execute as @a run msg @s Hello", "execute as @a run msg @s ", "Hello", False),
    ],
)
def test_analiza_comandos_de_chat(texto: str, prefijo: str, cuerpo: str, es_json: bool) -> None:
    assert comandos.analizar(texto) == comandos.Comando(prefijo, cuerpo, es_json)


@pytest.mark.parametrize("texto", ["give @p stone", "title @a times 1 2 3", "title @a clear", "tellraw @a", "# say hi"])
def test_ignora_lo_que_no_muestra_texto(texto: str) -> None:
    assert comandos.analizar(texto) is None


def test_runcommand_traduce_solo_el_mensaje(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = juego / "kubejs" / "server_scripts" / "chat.js"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(SCRIPT, encoding="utf-8")
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        resumen = traducir_modulo(ScriptsKubeJS(ctx), Traductor(Simulador(), memoria, Glosario()))
        assert resumen.traducidos == 5 and resumen.pendientes == 0
        nuevo = ruta.read_text(encoding="utf-8")
        assert """tellraw @a {"text": "«ES» Welcome to the village!", "color": "gold"}""" in nuevo
        assert r"""title @a actionbar {\"text\": \"«ES» Market opens soon\"}""" in nuevo
        assert "say «ES» The festival begins" in nuevo
        assert "${event.player.username}" in nuevo and "execute as @a run tellraw @s " in nuevo
        assert "times 10 70 20" in nuevo and "give @p minecraft:stone 2" in nuevo
        assert 'tellraw @a {text:"«ES» snbt not touched"}' in nuevo  # SNBT (1.21.5+): se conserva el formato
        ScriptsKubeJS(ctx).restaurar()
    assert ruta.read_text(encoding="utf-8") == SCRIPT


LOGRO = {
    "display": {
        "icon": {"item": "minecraft:wheat"},
        "title": {"text": "First Harvest", "color": "gold"},
        "description": "Harvest your first crop",
        "frame": "task",
    },
    "criteria": {"x": {"trigger": "minecraft:impossible"}},
}
FUNCION = (
    "# say no se toca\r\n"
    'tellraw @a {"text":"The shop is open"}\r\n'
    "scoreboard players add @a visits 1\r\n"
    "say Come in\r\n"
)


def test_logros_y_funciones(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    datos = juego / "kubejs" / "data" / "fc" / "advancements" / "farm"
    funciones = juego / "kubejs" / "data" / "fc" / "functions"
    datos.mkdir(parents=True)
    funciones.mkdir(parents=True)
    (datos / "harvest.json").write_text(json.dumps(LOGRO), encoding="utf-8")
    (juego / "kubejs" / "data" / "fc" / "recipes").mkdir()
    (juego / "kubejs" / "data" / "fc" / "recipes" / "r.json").write_text(json.dumps(LOGRO), encoding="utf-8")
    (funciones / "open.mcfunction").write_bytes(FUNCION.encode())
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        modulo = Datos(ctx)
        assert modulo.detectar() and modulo.describir() == "2 archivos de datos"
        resumen = traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        assert resumen.traducidos == 4 and resumen.pendientes == 0 and len(resumen.archivos) == 2
        logro = json.loads((datos / "harvest.json").read_text(encoding="utf-8"))
        assert logro["display"]["title"] == {"text": "«ES» First Harvest", "color": "gold"}
        assert logro["display"]["description"] == "«ES» Harvest your first crop"
        assert logro["display"]["icon"] == LOGRO["display"]["icon"] and logro["criteria"] == LOGRO["criteria"]
        nueva = (funciones / "open.mcfunction").read_bytes().decode()
        assert nueva == (
            "# say no se toca\r\n"
            'tellraw @a {"text": "«ES» The shop is open"}\r\n'
            "scoreboard players add @a visits 1\r\n"
            "say «ES» Come in\r\n"
        )
        assert json.loads((juego / "kubejs" / "data" / "fc" / "recipes" / "r.json").read_text("utf-8")) == LOGRO
        modulo.restaurar()
    assert json.loads((datos / "harvest.json").read_text(encoding="utf-8")) == LOGRO
    assert (funciones / "open.mcfunction").read_bytes().decode() == FUNCION


ARMADO = """const efectos = [
  { id: 'minecraft:luck', name: 'Luck' },
  { id: 'minecraft:speed', name: 'Speed' },
]
const avisar = (player, lista) => {
  let mensaje = 'The food has given you '
  for (let i = 0; i < lista.length; i++) {
    if (i > 0) mensaje += ', '
    if (i > 0 && i === lista.length - 1) mensaje += 'and '
    mensaje += lista[i].name
    mensaje += global.nombres[lista[i]]
  }
  let otro = 'Not a message at all'
  player.tell(mensaje)
  if (player.name == 'Steve') player.tell('Hi')
}
"""
TABLA = """global.nombres = {
  fcSweet: 'Sweet',
  fcSavory: 'Savory',
}
global.ids = { dulce: 'Not shown' }
"""


def test_mensajes_armados_por_partes(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    server = juego / "kubejs" / "server_scripts" / "dieta.js"
    startup = juego / "kubejs" / "startup_scripts" / "globales.js"
    for ruta, src in ((server, ARMADO), (startup, TABLA)):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(src, encoding="utf-8")
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        resumen = traducir_modulo(ScriptsKubeJS(ctx), Traductor(Simulador(), memoria, Glosario()))
        nuevo = server.read_text(encoding="utf-8")
        assert "let mensaje = '«ES» The food has given you '" in nuevo and "mensaje += '«ES» and '" in nuevo
        assert "name: '«ES» Luck'" in nuevo and "name: '«ES» Speed'" in nuevo
        assert "id: 'minecraft:luck'" in nuevo and "mensaje += ', '" in nuevo  # sin letras: no es texto
        assert "let otro = 'Not a message at all'" in nuevo  # no llega a ningún mensaje
        assert "tell('«ES» Hi')" in nuevo and "'Steve'" in nuevo
        tabla = startup.read_text(encoding="utf-8")
        assert "fcSweet: '«ES» Sweet'" in tabla and "fcSavory: '«ES» Savory'" in tabla
        assert "dulce: 'Not shown'" in tabla  # esa tabla no se suma a ningún mensaje
        assert resumen.pendientes == 0
        ScriptsKubeJS(ctx).restaurar()
    assert server.read_text(encoding="utf-8") == ARMADO and startup.read_text(encoding="utf-8") == TABLA

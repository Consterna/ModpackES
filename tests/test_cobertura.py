"""Informe de lo que queda en inglés: frases de scripts sin elegir y texto escrito en el código de los mods."""

import struct
from pathlib import Path

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto
from traductor_es.modulos.cobertura import constantes_utf8, revisar_cobertura
from traductor_es.motores.simulador import Simulador
from traductor_es.proceso import Proceso
from traductor_es.salida.copias import Respaldo

from . import fabrica

SCRIPT = """PlayerEvents.loggedIn(event => {
  event.player.tell('Welcome to the village')
  let aviso = 'The market is closed today'
  console.log('This should be a debug message here')
  if (event.player.name == 'Some Long Name Here') return
})
ServerEvents.recipes(event => { event.shapeless('minecraft:stone', ['Not A Real Recipe Name']) })
"""


def _clase(*constantes: str) -> bytes:
    """Un .class mínimo: solo la cabecera y la tabla de constantes con esas cadenas (más un entero entre medias)."""
    cuerpo = b"".join(b"\x01" + struct.pack(">H", len(c.encode())) + c.encode() for c in constantes[:1])
    cuerpo += b"\x03\x00\x00\x00\x07"  # un Integer: el lector tiene que saltarlo bien
    cuerpo += b"".join(b"\x01" + struct.pack(">H", len(c.encode())) + c.encode() for c in constantes[1:])
    cantidad = len(constantes) + 2  # las casillas empiezan en 1
    return b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 52, cantidad) + cuerpo


def test_lee_la_tabla_de_constantes_de_un_class() -> None:
    assert constantes_utf8(_clase("literal", "You can't do that here!", "ñandú")) == [
        "literal", "You can't do that here!", "ñandú",
    ]  # fmt: skip
    assert constantes_utf8(b"no es un class") == []
    assert constantes_utf8(_clase("literal")[:-3]) == []  # truncado: no se inventa nada


def test_cobertura_de_scripts_y_java(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    (juego / "kubejs" / "server_scripts").mkdir(parents=True)
    (juego / "kubejs" / "server_scripts" / "a.js").write_text(SCRIPT, encoding="utf-8")
    fabrica.jar(
        juego / "mods" / "m.jar",
        {
            "com/m/Chat.class": _clase("literal", "You can't use this item here!", "Failed to load the config file"),
            "com/m/Fabric.class": _clase("method_43470", "Click the block to open the menu"),
            "com/m/Otra.class": _clase("nada", "Another English sentence here"),  # no construye texto
            "com/m/Spanish.class": _clase("literal", "Alacena de abedul sin corteza"),  # ya está en español
        },
    )
    with Instancia(juego) as inst:
        sin_java = revisar_cobertura(Contexto(inst, Respaldo(juego)))
        con_java = revisar_cobertura(Contexto(inst, Respaldo(juego)), java=True)
    assert [(h.categoria, h.donde) for h in sin_java] == [("script", "kubejs/server_scripts/a.js")]
    assert sin_java[0].cantidad == 1  # `tell` ya se traduce; recetas, comparaciones y console.log no cuentan
    assert sin_java[0].ejemplos == ("The market is closed today",)
    de_java = [h for h in con_java if h.categoria == "java"]
    assert len(de_java) == 1
    assert set(de_java[0].ejemplos) == {"You can't use this item here!", "Click the block to open the menu"}


def test_analizar_avisa_sin_detener_el_analisis(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    (juego / "kubejs" / "server_scripts").mkdir(parents=True)
    (juego / "kubejs" / "server_scripts" / "a.js").write_text(SCRIPT, encoding="utf-8")
    with Proceso(juego, Simulador(), grupos=["scripts"]) as p:
        informe = p.analizar()
    assert any("1 frases de 1 lugares de los scripts" in a for a in informe.avisos)
    assert informe.modulos and informe.modulos[0].grupo == "scripts"


def test_formatos_desconocidos_se_informan_sin_tocar(tmp_path: Path) -> None:
    import json

    from traductor_es.modulos.cobertura import formatos_desconocidos

    juego = fabrica.prism(tmp_path, "1.20.1")
    quiz = juego / "kubejs" / "data" / "a" / "quizzes" / "q1.json"
    quiz.parent.mkdir(parents=True)
    quiz.write_text(json.dumps({"title": "What do cows eat for breakfast?", "id": "x"}), encoding="utf-8")
    conocido = juego / "kubejs" / "data" / "a" / "advancements" / "g.json"
    conocido.parent.mkdir(parents=True)
    conocido.write_text(json.dumps({"display": {"title": {"text": "A conocido title here"}}}), encoding="utf-8")
    receta = juego / "kubejs" / "data" / "a" / "recipes" / "r.json"
    receta.parent.mkdir(parents=True)
    receta.write_text(json.dumps({"result": {"text": "Not shown to the player, a recipe"}}), encoding="utf-8")
    antes = quiz.read_bytes()
    hallazgos = formatos_desconocidos(juego)
    assert [(h.categoria, h.donde, h.cantidad) for h in hallazgos] == [("formato", "kubejs/data/a/quizzes", 1)]
    assert hallazgos[0].ejemplos == ("What do cows eat for breakfast?",) and quiz.read_bytes() == antes


def test_texto_y_json_del_informe() -> None:
    import json

    from traductor_es.modulos.cobertura import Hallazgo, informe_en_json, texto_del_informe

    hallazgos = [
        Hallazgo("java", "m.jar", 2, "Escrito en el código", ("You can't do that!", "Ñandú ¡hola!")),
        Hallazgo("script", "kubejs/a.js", 1, "Parece una frase", ("The market is closed",)),
    ]
    texto = texto_del_informe(hallazgos)
    assert texto.index("Frases de scripts") < texto.index("Escrito en el código de los mods")  # script antes que java
    assert "m.jar: 2 textos" in texto and "Ñandú ¡hola!" in texto
    assert texto_del_informe([]) == "No encontré texto que se quede en inglés.\n"
    datos = json.loads(informe_en_json(hallazgos))
    assert datos[0] == {"categoria": "java", "donde": "m.jar", "textos": 2, "motivo": "Escrito en el código",
                        "ejemplos": ["You can't do that!", "Ñandú ¡hola!"]}  # fmt: skip
    assert "Ñandú" in informe_en_json(hallazgos)  # UTF-8 sin escapar


#: `queue` es de otro mod (Embers Text API): la app no conoce su formato y no debe tocarlo, solo avisar.
SCRIPT_CON_COMANDOS = """
const cola = (p, texto) => p.server.runCommandSilent(`emberstextapi queue "${p.name.string}" hotbar [bg gradient=1]${texto}</align>`)
ServerEvents.commandRegistry(event => {
    event.server.runCommandSilent(`/eta queue "${event.player.name.string}" credits <dur:400> Thank you for playing, we hope that you enjoyed it`)
    event.server.runCommand('scoreboard objectives add Hurt minecraft.custom:minecraft.damage_dealt')
    event.server.runCommand('execute as @a at @s run function foo:bar')
    event.server.runCommandSilent('tellraw @a {"text":"Welcome back to the village, friend"}')
    console.log('You can see this only in the log of the server')
})
"""


def test_comandos_de_otros_mods_con_frase_se_avisan_y_no_se_tocan(tmp_path: Path) -> None:
    from traductor_es.modulos.cobertura import hallazgos_de_comandos
    from traductor_es.modulos.scripts import ScriptsKubeJS

    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = juego / "kubejs" / "server_scripts" / "a.js"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(SCRIPT_CON_COMANDOS, encoding="utf-8")
    antes = ruta.read_bytes()
    with Instancia(juego) as inst:
        s = ScriptsKubeJS(Contexto(inst, Respaldo(juego)))
        piezas = s.recolectar()
        hallazgos = hallazgos_de_comandos(juego, s.comandos_ajenos)
    assert [(h.categoria, h.donde, h.cantidad) for h in hallazgos] == [("comando", "kubejs/server_scripts/a.js", 1)]
    assert "Thank you for playing" in hallazgos[0].ejemplos[0]
    # el comando de chat (tellraw) sí se traduce; el de otro mod no entra entre lo que se traduce
    assert [p.texto for p in piezas] == ["Welcome back to the village, friend"]
    assert ruta.read_bytes() == antes  # analizar no escribe nada


def test_el_informe_incluye_los_comandos_de_otros_mods(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = juego / "kubejs" / "server_scripts" / "a.js"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(SCRIPT_CON_COMANDOS, encoding="utf-8")
    with Instancia(juego) as inst:
        hallazgos = revisar_cobertura(Contexto(inst, Respaldo(juego)))
    assert "comando" in {h.categoria for h in hallazgos}
    from traductor_es.modulos.cobertura import texto_del_informe

    assert "Comandos de otros mods" in texto_del_informe(hallazgos)

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
    assert any("1 frases de 1 scripts" in a for a in informe.avisos)
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

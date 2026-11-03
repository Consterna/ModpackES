import gzip
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import nbt, snbt
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, Resumen, traducir_modulo
from traductor_es.modulos.misiones import HQM, BetterQuesting, FTBQuests, Heracles, _Base  # pyright: ignore[reportPrivateUsage]
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo

from . import fabrica

CAPITULO = r"""{
	filename: "getting_started"
	id: "61E9F8FCB1C14B9B"
	quests: [
		{
			title: "Craft a &aWorkbench"
			subtitle: "{ftbquests.chapter.x.subtitle}"
			description: [
				"Press \"E\" to open your inventory."
				""
				"{image:mod:textures/a.png width:100 height:50 align:1}"
				"{@pagebreak}"
				"[\"\", {\"text\": \"Click here\", \"color\": \"gold\", \"clickEvent\": {\"action\": \"open_url\", \"value\": \"https://x.y\"}}]"
			]
			id: "38597CE6BB709431"
			tasks: [{ id: "356D013846BD6115", item: "minecraft:crafting_table", type: "item", title: "Any table" }]
		}
	]
	title: "Getting Started"
}
"""


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def ejecutar(modulo: _Base, memoria: Memoria, motor: Simulador | None = None) -> Resumen:
    return traducir_modulo(modulo, Traductor(motor or Simulador(), memoria, Glosario()))


def contexto(juego: Path) -> tuple[Instancia, Contexto]:
    inst = Instancia(juego)
    return inst, Contexto(inst, Respaldo(juego))


def test_ftbquests_snbt_en_linea(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "getting_started.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text(CAPITULO, encoding="utf-8")
    (juego / "config" / "ftbquests" / "quests" / "data.snbt").write_text('{ title: "Quests" }', encoding="utf-8")
    inst, ctx = contexto(juego)
    with inst:
        modulo = FTBQuests(ctx)
        assert modulo.formato(modulo.raices()[0]) == "snbt"
        resumen = ejecutar(modulo, memoria)
        traducido = capitulo.read_text(encoding="utf-8")
        textos = {c.texto for c in snbt.escanear(traducido)}
        assert "«ES» Craft a &aWorkbench" in textos and "«ES» Getting Started" in textos
        assert '«ES» Press "E" to open your inventory.' in textos
        assert "{ftbquests.chapter.x.subtitle}" in textos  # clave de traducción: no se toca
        assert "{image:mod:textures/a.png width:100 height:50 align:1}" in textos and "{@pagebreak}" in textos
        componente = next(json.loads(t) for t in textos if t.startswith("["))
        assert componente[1]["text"] == "«ES» Click here" and componente[1]["clickEvent"]["value"] == "https://x.y"
        assert "minecraft:crafting_table" in textos and "«ES» Any table" in textos
        assert resumen.traducidos == 6 and len(resumen.archivos) == 2
        # Segunda ejecución: parte del inglés guardado, no traduce sobre lo traducido
        motor = Simulador()
        ejecutar(FTBQuests(ctx), memoria, motor)
        assert motor.lotes_recibidos == [] and capitulo.read_text(encoding="utf-8") == traducido
        assert sorted(FTBQuests(ctx).restaurar()) == sorted([capitulo, capitulo.parent.parent / "data.snbt"])
    assert capitulo.read_text(encoding="utf-8") == CAPITULO


def test_ftbquests_lang_respeta_lo_que_trae_el_modpack(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.21.1", "neoforge")
    lang = juego / "config" / "ftbquests" / "quests" / "lang"
    (lang / "en_us" / "chapters").mkdir(parents=True)
    en = '{\n\tquest.A.title: "Find Iron"\n\tquest.A.quest_desc: ["Mine it", ""]\n\tchapter.B.title: "Start"\n}\n'
    (lang / "en_us.snbt").write_text(en, encoding="utf-8")
    (lang / "en_us" / "chapters" / "c.snbt").write_text('{ quest.C.title: "Deep" }', encoding="utf-8")
    es_es = '{\n\tchapter.B.title: "Inicio"\n}\n'
    (lang / "es_es.snbt").write_text(es_es, encoding="utf-8")
    inst, ctx = contexto(juego)
    with inst:
        modulo = FTBQuests(ctx)
        assert modulo.describir() == "quests: textos en lang/ (1.21+)"
        ejecutar(modulo, memoria)
        for variante in VARIANTES:
            textos = {c.campo: c.texto for c in snbt.escanear((lang / f"{variante}.snbt").read_text(encoding="utf-8"))}
            assert textos["quest.A.title"] == "«ES» Find Iron"
            assert textos["chapter.B.title"] == ("Inicio" if variante == "es_es" else "«ES» Start")
            sub = (lang / variante / "chapters" / "c.snbt").read_text(encoding="utf-8")
            assert "«ES» Deep" in sub
        assert (lang / "en_us.snbt").read_text(encoding="utf-8") == en
        # Segunda vez: la traducción del modpack sigue mandando aunque el archivo ya lo reescribió la app
        ejecutar(FTBQuests(ctx), memoria)
        assert "Inicio" in (lang / "es_es.snbt").read_text(encoding="utf-8")
        FTBQuests(ctx).restaurar()
    assert (lang / "es_es.snbt").read_text(encoding="utf-8") == es_es
    assert (lang / "es_mx.snbt").read_bytes() == b"{\n}\n"


def test_ftbquests_nbt_de_112(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.12.2")
    carpeta = juego / "config" / "ftbquests" / "normal" / "chapters" / "abc"
    carpeta.mkdir(parents=True)
    c = nbt.Compuesto()
    c.hijos["title"] = (nbt.STRING, "Find Redstone")
    c.hijos["text"] = (nbt.LISTA, nbt.Lista(nbt.STRING, ["Mine it", "&cCareful"]))
    c.hijos["icon"] = (nbt.STRING, "minecraft:redstone")
    c.hijos["x"] = (nbt.DOUBLE, b"\x3f\xf8\x00\x00\x00\x00\x00\x00")
    original = nbt.escribir(nbt.Raiz(nbt.COMPUESTO, "", c))
    (carpeta / "q1.nbt").write_bytes(original)
    inst, ctx = contexto(juego)
    with inst:
        modulo = FTBQuests(ctx)
        assert modulo.formato(modulo.raices()[0]) == "nbt"
        ejecutar(modulo, memoria)
        raiz, compresion = nbt.leer((carpeta / "q1.nbt").read_bytes())
        textos = {(x.campo, x.texto) for x in nbt.cadenas(raiz)}
        assert compresion == "gzip"
        assert textos == {("title", "«ES» Find Redstone"), ("text", "«ES» Mine it"), ("text", "«ES» &cCareful"),
                          ("icon", "minecraft:redstone")}  # fmt: skip
        assert raiz.valor.hijos["x"] == (nbt.DOUBLE, b"\x3f\xf8\x00\x00\x00\x00\x00\x00")  # type: ignore[union-attr]
        FTBQuests(ctx).restaurar()
    assert gzip.decompress((carpeta / "q1.nbt").read_bytes()) == gzip.decompress(original)


def test_betterquesting(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.12.2")
    archivo = juego / "config" / "betterquesting" / "DefaultQuests.json"
    archivo.parent.mkdir(parents=True)
    datos = {
        "questDatabase:9": {
            "0:10": {"questID:3": 0, "properties:10": {"betterquesting:10": {"name:8": "Welcome", "desc:8": "Read me\nnow", "icon:10": {"id:8": "minecraft:book"}}}},
            "1:10": {"questID:3": 1, "properties:10": {"betterquesting:10": {"name:8": "bq.quest.1.name", "desc:8": "§aGreen text"}}},
        },
        "questLines:9": {"0:10": {"properties:10": {"betterquesting:10": {"name:8": "Chapter One"}}}},
    }  # fmt: skip
    texto = json.dumps(datos, indent=2)
    archivo.write_text(texto, encoding="utf-8")
    inst, ctx = contexto(juego)
    with inst:
        ejecutar(BetterQuesting(ctx), memoria)
        nuevo = json.loads(archivo.read_text(encoding="utf-8"))
        props = nuevo["questDatabase:9"]["0:10"]["properties:10"]["betterquesting:10"]
        assert props["name:8"] == "«ES» Welcome" and props["desc:8"] == "«ES» Read me\nnow"
        assert props["icon:10"]["id:8"] == "minecraft:book"
        assert nuevo["questDatabase:9"]["1:10"]["properties:10"]["betterquesting:10"]["name:8"] == "bq.quest.1.name"
        assert nuevo["questLines:9"]["0:10"]["properties:10"]["betterquesting:10"]["name:8"] == "«ES» Chapter One"
        BetterQuesting(ctx).restaurar()
    assert archivo.read_text(encoding="utf-8") == texto


def test_hqm(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "fabric")
    sets = juego / "config" / "hqm" / "sets"
    sets.mkdir(parents=True)
    (juego / "config" / "hqm" / "sets.json").write_text('{"sets": ["Basics"]}', encoding="utf-8")
    quest = {"name": "Basics", "description": "The beginning", "quests": [{"name": "Wood", "description": "Get wood",
             "tasks": [{"type": "CONSUME", "name": "Chop", "description": "Chop a tree"}]}]}  # fmt: skip
    (sets / "Basics.json").write_text(json.dumps(quest), encoding="utf-8")
    inst, ctx = contexto(juego)
    with inst:
        ejecutar(HQM(ctx), memoria)
    nuevo = json.loads((sets / "Basics.json").read_text(encoding="utf-8"))
    assert nuevo["description"] == "«ES» The beginning" and nuevo["quests"][0]["tasks"][0]["name"] == "«ES» Chop"
    assert nuevo["quests"][0]["tasks"][0]["type"] == "CONSUME"
    assert (juego / "config" / "hqm" / "sets.json").read_text(encoding="utf-8") == '{"sets": ["Basics"]}'


def test_heracles(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "fabric")
    carpeta = juego / "config" / "heracles" / "quests" / "Main"
    carpeta.mkdir(parents=True)
    quest = {
        "display": {
            "title": '"Getting Started"',
            "subtitle": '{"text": "First steps", "color": "gray"}',
            "description": ["Welcome to the pack!", '<item id="minecraft:apple"/>'],
            "icon": {"type": "heracles:item", "item": "minecraft:apple"},
            "groups": {"Main": {"position": [0, 0]}},
        },
        "tasks": {"t1": {"type": "heracles:item", "item": "minecraft:apple", "title": "Collect apples"}},
        "rewards": {"r1": {"type": "heracles:xp", "title": "Some XP", "amount": 5}},
    }
    (carpeta / "start.json").write_text(json.dumps(quest, indent=2), encoding="utf-8")
    inst, ctx = contexto(juego)
    with inst:
        ejecutar(Heracles(ctx), memoria)
    nuevo = json.loads((carpeta / "start.json").read_text(encoding="utf-8"))
    d = nuevo["display"]
    assert json.loads(d["title"]) == "«ES» Getting Started"
    assert json.loads(d["subtitle"]) == {"text": "«ES» First steps", "color": "gray"}
    assert d["description"] == ["«ES» Welcome to the pack!", '<item id="minecraft:apple"/>']
    assert list(d["groups"]) == ["Main"] and d["icon"]["item"] == "minecraft:apple"
    assert nuevo["tasks"]["t1"]["title"] == "«ES» Collect apples" and nuevo["rewards"]["r1"]["title"] == "«ES» Some XP"


def test_json_roto_se_deja_igual(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    carpeta = juego / "config" / "heracles" / "quests"
    carpeta.mkdir(parents=True)
    (carpeta / "roto.json").write_text('{"display": {"title": ', encoding="utf-8")
    avisos: list[str] = []
    inst = Instancia(juego)
    with inst:
        ctx = Contexto(inst, Respaldo(juego), registro=avisos.append)
        resumen = ejecutar(Heracles(ctx), memoria)
    assert resumen.archivos == [] and avisos == ["roto.json no es JSON válido: se deja igual"]


def test_analizar_no_escribe_nada_en_la_instancia(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text(CAPITULO, encoding="utf-8")
    inst, ctx = contexto(juego)
    with inst:
        assert FTBQuests(ctx).recolectar()
    assert not (juego / "traductor_es").exists()


def test_capitulo_danado_no_frena_a_los_demas(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    capitulos = juego / "config" / "ftbquests" / "quests" / "chapters"
    capitulos.mkdir(parents=True)
    (capitulos / "bueno.snbt").write_text('{ title: "Good" }', encoding="utf-8")
    (capitulos / "roto.snbt").write_text('{ title: "Broken }', encoding="utf-8")
    avisos: list[str] = []
    inst = Instancia(juego)
    with inst:
        ctx = Contexto(inst, Respaldo(juego), registro=avisos.append)
        ejecutar(FTBQuests(ctx), memoria)
    assert "«ES» Good" in (capitulos / "bueno.snbt").read_text(encoding="utf-8")
    assert (capitulos / "roto.snbt").read_text(encoding="utf-8") == '{ title: "Broken }'
    assert avisos == ["roto.snbt está dañado: se deja igual"]

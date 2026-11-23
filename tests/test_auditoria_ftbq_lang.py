"""FTB Quests contrastado con su código (`.auditoria/investigacion/dominio_mods.md`, D2 y D6).

- 1.21 con carpeta lang: solo pasan a lang el título, el subtítulo y la descripción. El texto de una recompensa de
  aviso, el `lock_message` de data.snbt, los nombres de los objetos de recompensa y el de las cajas de botín siguen
  en los capítulos, y antes se saltaban (H-042).
- `loot_crate.item_name` no se traducía en ninguna versión; `string_id`, a su lado, es un id.
- 26.x guarda todo en JSON5, que la app todavía no lee: antes no traducía nada y no lo decía.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import lang_json5, snbt
from traductor_es.fuentes import vanilla
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto
from traductor_es.modulos.misiones import FTBQuests
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso
from traductor_es.salida.copias import Respaldo

from . import fabrica

CAPITULO_LANG = """{
\tid: "0000000000000001"
\tquests: [{
\t\tid: "0A1B2C3D4E5F6071"
\t\ttasks: [{ id: "1A1B2C3D4E5F6071", type: "checkmark" }]
\t\trewards: [
\t\t\t{ id: "2A1B2C3D4E5F6071", type: "toast", description: "You did it!" }
\t\t\t{ id: "3A1B2C3D4E5F6071", type: "item", item: { id: "minecraft:diamond", count: 1, components: { "minecraft:custom_name": "Shiny Reward" } } }
\t\t]
\t}]
}
"""
TABLA = '{\n\tid: "4A1B2C3D4E5F6071"\n\tloot_crate: { string_id: "common", item_name: "Common Crate", color: 123 }\n}\n'


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _pack_lang(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.21.1", "neoforge")
    quests = juego / "config" / "ftbquests" / "quests"
    (quests / "lang").mkdir(parents=True)
    (quests / "lang" / "en_us.snbt").write_text('{\n\tquest.0A1B2C3D4E5F6071.title: "Find Iron"\n}\n', "utf-8")
    (quests / "chapters").mkdir()
    (quests / "chapters" / "uno.snbt").write_text(CAPITULO_LANG, encoding="utf-8")
    (quests / "chapters" / "vacio.snbt").write_text('{ id: "0000000000000002" }', encoding="utf-8")
    (quests / "data.snbt").write_text('{\n\tlock_message: "Finish the intro first"\n\tversion: 13\n}\n', "utf-8")
    (quests / "reward_tables").mkdir()
    (quests / "reward_tables" / "t.snbt").write_text(TABLA, encoding="utf-8")
    return juego


def test_con_carpeta_lang_se_traduce_lo_que_sigue_en_los_capitulos(tmp_path: Path, memoria: Memoria) -> None:
    juego = _pack_lang(tmp_path)
    quests = juego / "config" / "ftbquests" / "quests"
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar()
    capitulo = {c.texto for c in snbt.escanear((quests / "chapters" / "uno.snbt").read_text(encoding="utf-8"))}
    assert "«ES» You did it!" in capitulo
    assert "«ES» Shiny Reward" in capitulo
    assert "toast" in capitulo and "minecraft:diamond" in capitulo  # tipo e id, intactos
    assert "«ES» Finish the intro first" in (quests / "data.snbt").read_text(encoding="utf-8")
    tabla = (quests / "reward_tables" / "t.snbt").read_text(encoding="utf-8")
    assert 'item_name: "«ES» Common Crate"' in tabla and 'string_id: "common"' in tabla
    assert "«ES» Find Iron" in (quests / "lang" / "es_mx.snbt").read_text(encoding="utf-8")
    # un capítulo sin nada en línea no se reescribe
    assert (quests / "chapters" / "vacio.snbt").read_text(encoding="utf-8") == '{ id: "0000000000000002" }'


def test_la_version_de_espana_no_vuelve_a_tocar_los_capitulos(tmp_path: Path, memoria: Memoria) -> None:
    juego = _pack_lang(tmp_path)
    inst = Instancia(juego)
    with inst:
        ctx = Contexto(inst, Respaldo(juego), solo_por_idioma=True)
        modulo = FTBQuests(ctx)
        textos = {p.texto for p in modulo.recolectar()}  # una vez por variante, solo lo de la carpeta lang
    assert textos == {"Find Iron"}


def test_la_caja_de_botin_tambien_en_120(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    tabla = juego / "config" / "ftbquests" / "quests" / "reward_tables" / "t.snbt"
    tabla.parent.mkdir(parents=True)
    tabla.write_text(TABLA, encoding="utf-8")
    (tabla.parent.parent / "chapters").mkdir()
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar()
    texto = tabla.read_text(encoding="utf-8")
    assert 'item_name: "«ES» Common Crate"' in texto and 'string_id: "common"' in texto


#: FTB Quests 26.x (rama `main`): `lang/<idioma>/**/*.json5`, un objeto plano por archivo; `quest_desc` es una lista
INTRO_JSON5 = """{
  // escrito por FTB Quests con de.marhali.json5
  'quest.0123456789ABCDEF.title': 'Welcome',
  "quest.0123456789ABCDEF.quest_desc": ["Hello there.", "", "{@pagebreak}", "Second page"],
  "chapter.0A0B0C0D0E0F0102.title": "Intro",
}
"""


def _pack_26(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "26.1.2", "neoforge")
    quests = juego / "config" / "ftbquests" / "quests"
    (quests / "lang" / "en_us" / "chapters").mkdir(parents=True)
    (quests / "data.json5").write_text("{ version: 13 }", encoding="utf-8")
    (quests / "chapters").mkdir()
    (quests / "chapters" / "intro.json5").write_text('{ id: "0A0B0C0D0E0F0102" }', encoding="utf-8")
    (quests / "lang" / "en_us" / "chapters" / "intro.json5").write_text(INTRO_JSON5, encoding="utf-8")
    (quests / "lang" / "en_us" / "chapter_group.json5").write_text('{"chapter_group.1A.title": "Basics"}', "utf-8")
    return juego


def test_json5_de_26_se_traduce_en_cada_idioma(tmp_path: Path, memoria: Memoria) -> None:
    juego = _pack_26(tmp_path)
    lang = juego / "config" / "ftbquests" / "quests" / "lang"
    # el modpack ya trae su propio es_es para el título del capítulo: se respeta
    (lang / "es_es" / "chapters").mkdir(parents=True)
    (lang / "es_es" / "chapters" / "intro.json5").write_text(
        '{"chapter.0A0B0C0D0E0F0102.title": "Introducción"}', "utf-8"
    )
    avisos: list[str] = []
    with Proceso(juego, Simulador(), memoria=memoria, registro=avisos.append) as p:
        p.ejecutar()
    mx = lang_json5.leer((lang / "es_mx" / "chapters" / "intro.json5").read_bytes())
    assert mx == {
        "quest.0123456789ABCDEF.title": "«ES» Welcome",
        "quest.0123456789ABCDEF.quest_desc": ["«ES» Hello there.", "", "{@pagebreak}", "«ES» Second page"],
        "chapter.0A0B0C0D0E0F0102.title": "«ES» Intro",
    }
    es = lang_json5.leer((lang / "es_es" / "chapters" / "intro.json5").read_bytes())
    assert es["chapter.0A0B0C0D0E0F0102.title"] == "Introducción"  # lo del modpack manda
    assert es["quest.0123456789ABCDEF.title"] == "«ES» Welcome"
    assert lang_json5.leer((lang / "es_ar" / "chapter_group.json5").read_bytes()) == {
        "chapter_group.1A.title": "«ES» Basics"
    }
    assert (lang / "en_us" / "chapters" / "intro.json5").read_text(
        encoding="utf-8"
    ) == INTRO_JSON5  # el inglés no se toca
    assert not (lang / "es_mx.json5").exists()  # FTB Quests 26.x no lee un archivo suelto por idioma
    assert any("dentro de los capítulos" in a for a in avisos)  # lo que sigue en línea, avisado


def test_json5_de_26_se_restaura(tmp_path: Path, memoria: Memoria) -> None:
    juego = _pack_26(tmp_path)
    lang = juego / "config" / "ftbquests" / "quests" / "lang"
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar()
        assert (lang / "es_mx" / "chapters" / "intro.json5").is_file()
        p.restaurar()
    assert (lang / "es_mx" / "chapters" / "intro.json5").read_bytes() == b"{}\n"  # vacío: el juego usa en_us
    assert (lang / "en_us" / "chapters" / "intro.json5").read_text(encoding="utf-8") == INTRO_JSON5


def test_json5_en_la_version_de_espana(tmp_path: Path) -> None:
    juego = _pack_26(tmp_path)
    inst = Instancia(juego)
    with inst:
        modulo = FTBQuests(Contexto(inst, Respaldo(juego), solo_por_idioma=True))
        assert modulo.detectar()
        assert modulo.formato(modulo.raices()[0]) == "json5"
        assert "JSON5" in modulo.describir()
        assert {p.texto for p in modulo.recolectar()} == {"Welcome", "Hello there.", "Second page", "Intro", "Basics"}


def test_json5_danado_se_salta_con_aviso(tmp_path: Path, memoria: Memoria) -> None:
    juego = _pack_26(tmp_path)
    lang = juego / "config" / "ftbquests" / "quests" / "lang"
    (lang / "en_us" / "roto.json5").write_text("{ 'quest.X.title': ", encoding="utf-8")
    avisos: list[str] = []
    inst = Instancia(juego)
    with inst:
        modulo = FTBQuests(Contexto(inst, Respaldo(juego), registro=avisos.append))
        assert {p.texto for p in modulo.recolectar()} >= {"Welcome", "Basics"}
    assert "roto.json5 está dañado: se deja igual" in avisos


@pytest.mark.parametrize(
    "texto",
    ['Comillas "dobles" y \\ barra', "Línea\u2028separada", "Un 'apóstrofo'", "Tab\tdentro"],
)
def test_lang_json5_ida_y_vuelta(texto: str) -> None:
    datos = {"quest.A.title": texto, "quest.A.quest_desc": [texto, ""]}
    escrito = lang_json5.escribir(datos)
    assert lang_json5.leer(escrito) == datos
    assert "\u2028".encode() not in escrito  # nunca un U+2028 crudo: va escapado

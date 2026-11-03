import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from traductor_es.formatos import javascript as js
from traductor_es.formatos import lang_json
from traductor_es.fuentes import vanilla
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.mods import Mods
from traductor_es.modulos.scripts import ScriptsKubeJS
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import ESCAPE_CRUDO
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica

SCRIPT = r"""// Tooltip con 'comillas' en un comentario
/* bloque "con" comillas */
ItemEvents.tooltip(event => {
  event.add(['create:wrench', 'minecraft:stone'], ['You can sell 2 of these', '§aFor 5 tickets'])
  event.addAdvanced('minecraft:apple', (item, advanced, text) => {
    text.add(1, Text.of('A tasty "red" apple').gold())
  })
})
ServerEvents.tags('item', event => {
  event.add('forge:gems', 'Shiny Gem Item')
})
ServerEvents.recipes(event => {
  event.shaped(Item.of('minecraft:stone', 2), ['AB ', ' C '], { A: 'minecraft:dirt' })
})
PlayerEvents.chat(event => {
  if (event.message == 'Hello There') event.player.tell(`Welcome back, ${event.player.username}!`)
  let re = /it's "not" a string/g
  event.player.tell('Line one\nLine two')
  event.player.tell('stone')
})
StartupEvents.registry('item', event => {
  event.create('miles_ticket').displayName('Miles Ticket')
})
"""


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def test_escaner_contexto_y_lo_que_se_elige() -> None:
    cadenas = js.escanear(SCRIPT)
    from traductor_es.modulos.scripts import es_texto_visible

    elegidas = [c.texto for c in cadenas if es_texto_visible(c)]
    assert elegidas == [
        "You can sell 2 of these", "§aFor 5 tickets", 'A tasty "red" apple',
        "Welcome back, ${event.player.username}!", "Line one\nLine two", "Miles Ticket",
    ]  # fmt: skip
    textos = {c.texto for c in cadenas}
    assert 'it\'s "not" a string' not in textos  # la expresión regular no se toma por cadena
    assert "comillas" not in " ".join(textos)  # los comentarios tampoco
    hola = next(c for c in cadenas if c.texto == "Hello There")
    assert hola.comparada
    gema = next(c for c in cadenas if c.texto == "Shiny Gem Item")
    assert not es_texto_visible(gema) and "ServerEvents.tags:item" in gema.contexto
    assert js.reemplazar(SCRIPT, cadenas, {c.inicio: c.texto for c in cadenas}) == SCRIPT


@given(st.text(st.characters(blacklist_categories=("Cs",), blacklist_characters=ESCAPE_CRUDO)), st.sampled_from("'\"`"))
def test_escapar_y_leer_de_vuelta(texto: str, comilla: str) -> None:
    src = f"x.tell({comilla}{js.escapar(texto, comilla)}{comilla})"
    if comilla == "`" and "${" in texto:
        return  # en plantillas «${» es código
    cadenas = js.escanear(src)
    assert [c.texto for c in cadenas] == [texto]


def _node() -> str | None:
    return shutil.which("node")


def _sintaxis_valida(ruta: Path) -> bool:
    node = _node()
    assert node
    return subprocess.run([node, "--check", str(ruta)], capture_output=True, check=False).returncode == 0


def test_scripts_kubejs(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = juego / "kubejs" / "client_scripts" / "tooltips.js"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(SCRIPT, encoding="utf-8")
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        resumen = traducir_modulo(ScriptsKubeJS(ctx), Traductor(Simulador(), memoria, Glosario()))
        assert resumen.traducidos == 6
        nuevo = ruta.read_text(encoding="utf-8")
        assert "'«ES» You can sell 2 of these'" in nuevo and "'«ES» §aFor 5 tickets'" in nuevo
        assert "Text.of('«ES» A tasty \"red\" apple')" in nuevo
        assert "`«ES» Welcome back, ${event.player.username}!`" in nuevo
        assert "'«ES» Line one\\nLine two'" in nuevo and ".displayName('«ES» Miles Ticket')" in nuevo
        assert "'Shiny Gem Item'" in nuevo and "'Hello There'" in nuevo and "tell('stone')" in nuevo
        if _node():
            assert _sintaxis_valida(ruta)
        ScriptsKubeJS(ctx).restaurar()
    assert ruta.read_text(encoding="utf-8") == SCRIPT


def test_mods_escribe_variantes_y_copia_lo_existente(
    tmp_path: Path, memoria: Memoria, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sin_lanzadores() -> list[Path]:
        return []  # sin el juego real del PC

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", sin_lanzadores)
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(
        juego / "mods" / "m.jar",
        {
            **fabrica.lang("m", "en_us", {"item.m.a": "Iron Plate", "item.m.b": "Gold Plate", "item.m.c": "%s"}),
            **fabrica.lang("m", "es_es", {"item.m.a": "Placa de hierro"}),
        },
    )
    (juego / "kubejs" / "assets" / "kubejs" / "lang").mkdir(parents=True)
    (juego / "kubejs" / "assets" / "kubejs" / "lang" / "en_us.json").write_text('{"item.kubejs.t": "Ticket"}', "utf-8")
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        resumen = traducir_modulo(Mods(ctx), Traductor(Simulador(), memoria, Glosario()))
    assert resumen.traducidos == 2 and resumen.pendientes == 0
    pack = juego / "resourcepacks" / "Traduccion_ES" / "assets"
    for v in VARIANTES:
        m = (
            lang_json.leer((pack / "m" / "lang" / f"{v}.json").read_bytes())
            if (pack / "m" / "lang" / f"{v}.json").exists()
            else {}
        )
        if v == "es_es":
            assert m == {"item.m.b": "«ES» Gold Plate"}  # «a» ya lo trae el mod en es_es
        else:
            assert m == {"item.m.a": "Placa de hierro", "item.m.b": "«ES» Gold Plate"}
        k = json.loads((pack / "kubejs" / "lang" / f"{v}.json").read_text("utf-8"))
        assert k == {"item.kubejs.t": "«ES» Ticket"}
    assert not (juego / "traductor_es").exists()  # el módulo de mods no toca la instancia


class _Inventa:
    """Motor que mete saltos de línea o «${» que el original no tenía."""

    nombre = "inventa"

    def traducir_lote(self, lote: object) -> dict[str, str]:
        from traductor_es.motores.base import Lote

        assert isinstance(lote, Lote)
        return {e.id: e.texto + "\n${hack}" for e in lote.entradas}


def test_traducciones_peligrosas_se_descartan(
    tmp_path: Path, memoria: Memoria, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sin_lanzadores() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", sin_lanzadores)
    juego = fabrica.prism(tmp_path, "1.12.2")
    fabrica.jar(juego / "mods" / "viejo.jar", fabrica.lang("v", "en_us", {"a": "Old Item"}, legacy=True))
    script = juego / "kubejs" / "server_scripts" / "s.js"
    script.parent.mkdir(parents=True)
    script.write_text("player.tell(`Hi ${name}`)\n", encoding="utf-8")
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        traductor = Traductor(_Inventa(), memoria, Glosario())  # pyright: ignore[reportArgumentType]
        mods = traducir_modulo(Mods(ctx), traductor)
        scripts = traducir_modulo(ScriptsKubeJS(ctx), traductor)
    assert mods.traducidos == 0 and mods.pendientes == 1  # el .lang no admite el salto: queda en inglés
    assert scripts.traducidos == 0 and script.read_text(encoding="utf-8") == "player.tell(`Hi ${name}`)\n"


def test_sin_nada_que_escribir_no_crea_pack(tmp_path: Path, memoria: Memoria, monkeypatch: pytest.MonkeyPatch) -> None:
    def sin_lanzadores() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", sin_lanzadores)
    juego = fabrica.prism(tmp_path, "1.20.1")
    with Instancia(juego) as inst:
        traducir_modulo(Mods(Contexto(inst, Respaldo(juego))), Traductor(Simulador(), memoria, Glosario()))
    assert not (juego / "resourcepacks" / "Traduccion_ES").exists()

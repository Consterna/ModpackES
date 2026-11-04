import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import markdown
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, Resumen, traducir_modulo
from traductor_es.modulos.libros import Libros
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica

ENTRADA = {
    "name": "Mana Basics",
    "icon": "botania:mana_pool",
    "category": "botania:basics",
    "pages": [
        {"type": "patchouli:text", "text": "Mana is $(l:basics/pool)stored$() in a $(item)Mana Pool$().$(br2)Simple."},
        {"type": "patchouli:crafting", "recipe": "botania:pool", "text": "botania.page.pool1"},
        {"type": "patchouli:spotlight", "title": "#title", "item": "botania:pool"},
    ],
}
GUIA = """---
navigation:
  title: Getting Started
  position: 10
---

# Getting Started

<GameScene zoom="4">
  <ImportStructure src="assets/a.snbt" />
</GameScene>

To begin, find a [meteorite](meteorites.md) and
mine its <ItemLink id="ae2:cube" /> center.

- Mine certus quartz
- Keep the budding blocks

```java
code();
```
"""
LAVENDER = """```json
{
  "title": "Welcome Entry",
  "icon": "minecraft:book"
}
```

Hello there, *traveler*.
"""


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def correr(juego: Path, memoria: Memoria, motor: Simulador | None = None) -> tuple[Resumen, Path, list[str]]:
    avisos: list[str] = []
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), registro=avisos.append, pack=PackSalida(inst))
        resumen = traducir_modulo(Libros(ctx), Traductor(motor or Simulador(), memoria, Glosario()))
    return resumen, juego / "resourcepacks" / "Traduccion_ES", avisos


def test_patchouli_mantle_citadel_guideme_lavender(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    citadel = "<NEWLINE>\nThe anaconda is a huge snake that lives in swamps and\neats almost anything.\n<NEWLINE>\n"
    mantle = {"title": "Byproducts", "text": [{"text": "Ores give byproducts.", "paragraph": True}], "data": "x.nbt"}
    fabrica.jar(
        juego / "mods" / "libros.jar",
        {
            "assets/botania/patchouli_books/lexicon/en_us/entries/basics/mana.json": ENTRADA,
            "assets/botania/patchouli_books/lexicon/en_us/templates/t.json": {"components": [{"text": "#text"}]},
            "assets/tconstruct/book/foundry/en_us/byproducts.json": mantle,
            "assets/alexsmobs/book/animal_dictionary/en_us/anaconda.txt": citadel,
            "assets/ae2/ae2guide/getting-started.md": GUIA,
            "assets/bud/lavender/entries/guide/welcome.md": LAVENDER,
            "assets/bud/lavender/entries/guide/de_de/welcome.md": LAVENDER.replace("Hello", "Hallo"),
            "data/viejo/patchouli_books/manual/en_us/entries/a.json": {"name": "Old"},
        },
    )
    resumen, pack, avisos = correr(juego, memoria)
    assert (
        resumen.traducidos == 12 and resumen.pendientes == 0
    )  # 2 Patchouli, 2 Mantle, 1 Citadel, 5 GuideME, 2 Lavender
    for v in VARIANTES:
        entrada = json.loads(
            (pack / f"assets/botania/patchouli_books/lexicon/{v}/entries/basics/mana.json").read_text("utf-8")
        )
        assert entrada["name"] == "«ES» Mana Basics" and entrada["icon"] == "botania:mana_pool"
        assert entrada["pages"][0]["text"].startswith("«ES» Mana is $(l:basics/pool)stored$()")
        assert entrada["pages"][1]["text"] == "botania.page.pool1" and entrada["pages"][2]["title"] == "#title"
        assert not (pack / f"assets/botania/patchouli_books/lexicon/{v}/templates").exists()
        byp = json.loads((pack / f"assets/tconstruct/book/foundry/{v}/byproducts.json").read_text("utf-8"))
        assert byp == {
            "title": "«ES» Byproducts",
            "text": [{"text": "«ES» Ores give byproducts.", "paragraph": True}],
            "data": "x.nbt",
        }
        txt = (pack / f"assets/alexsmobs/book/animal_dictionary/{v}/anaconda.txt").read_text("utf-8").split("\n")
        assert txt[0] == "<NEWLINE>" and txt[-2] == "<NEWLINE>" and all(len(x) <= 54 for x in txt)
        guia = (pack / f"assets/ae2/ae2guide/_{v}/getting-started.md").read_text("utf-8")
        assert "  title: «ES» Getting Started" in guia and "# «ES» Getting Started" in guia
        assert (
            '«ES» To begin, find a [meteorite](meteorites.md) and\nmine its <ItemLink id="ae2:cube" /> center.' in guia
        )
        assert (
            '<ImportStructure src="assets/a.snbt" />' in guia
            and "code();" in guia
            and "- «ES» Keep the budding blocks" in guia
        )
        lav = (pack / f"assets/bud/lavender/entries/guide/{v}/welcome.md").read_text("utf-8")
        assert '"title": "«ES» Welcome Entry",' in lav and "«ES» Hello there, *traveler*." in lav
    assert any("viejo:manual" in a for a in avisos)


def test_copia_variante_existente_y_reemplaza_copia_vieja(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = "assets/m/patchouli_books/b/{}/entries/e.json"
    fabrica.jar(juego / "mods" / "a.jar", {ruta.format("en_us"): {"name": "Entry"}})
    _, pack, _ = correr(juego, memoria)
    assert json.loads((pack / ruta.format("es_es")).read_text("utf-8"))["name"] == "«ES» Entry"
    # El mod se actualiza y trae su propia traducción es_es: se copia a las demás y reemplaza lo de la app
    fabrica.jar(
        juego / "mods" / "a.jar", {ruta.format("en_us"): {"name": "Entry"}, ruta.format("es_es"): {"name": "Entrada"}}
    )
    motor = Simulador()
    _, pack, _ = correr(juego, memoria, motor)
    assert motor.lotes_recibidos == []
    for v in VARIANTES:
        assert json.loads((pack / ruta.format(v)).read_text("utf-8"))["name"] == "Entrada"


def test_libro_propio_del_modpack_se_restaura_al_ingles(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.16.5")
    base = juego / "patchouli_books" / "manual"
    (base / "en_us" / "entries").mkdir(parents=True)
    original = json.dumps({"name": "Welcome", "pages": [{"type": "text", "text": "Hi"}]}).encode()
    (base / "en_us" / "entries" / "w.json").write_bytes(original)
    correr(juego, memoria)
    es = json.loads((base / "es_mx" / "entries" / "w.json").read_text("utf-8"))
    assert es["name"] == "«ES» Welcome" and es["pages"][0]["text"] == "«ES» Hi"
    with Instancia(juego) as inst:
        Libros(Contexto(inst, Respaldo(juego))).restaurar()
    assert (base / "es_mx" / "entries" / "w.json").read_bytes() == original
    assert (base / "en_us" / "entries" / "w.json").read_bytes() == original


def test_markdown_sin_traducciones_queda_igual() -> None:
    lineas, segs = markdown.segmentar(GUIA)
    assert markdown.reconstruir(lineas, segs, {}) == GUIA
    crlf = GUIA.replace("\n", "\r\n")
    lineas, segs = markdown.segmentar(crlf)
    traducido = markdown.reconstruir(lineas, segs, {s.texto: s.texto.upper() for s in segs})
    assert traducido.count("\r\n") == crlf.count("\r\n") and "# GETTING STARTED\r\n" in traducido


def test_md_suelto_no_es_guia_y_las_urls_no_se_parten(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    url = "https://example.com/" + "a" * 90
    fabrica.jar(
        juego / "mods" / "m.jar",
        {
            "assets/m/docs/CHANGELOG.md": "# Changelog\n\nFixed bugs.\n",
            "assets/m/book/b/en_us/p.txt": f"Read more at {url} for details about this creature.\n",
        },
    )
    _, pack, _ = correr(juego, memoria)
    assert not (pack / "assets/m/docs").exists()
    texto = (pack / "assets/m/book/b/es_mx/p.txt").read_text("utf-8")
    assert url in texto


def test_linea_de_etiquetas_mal_formada_no_se_cuelga() -> None:
    """Regresión (CodeQL py/redos): «<A/><A/>…» sin cierre tardaba un tiempo exponencial en descartarse."""
    import time

    linea = "<A" + "/><A" * 200
    inicio = time.perf_counter()
    _, segmentos = markdown.segmentar(f"# Título\n\n{linea}\n")
    assert time.perf_counter() - inicio < 0.5
    assert [s.texto for s in segmentos] == ["Título", linea]  # no son solo etiquetas: queda como texto
    _, solo = markdown.segmentar('<GameScene zoom="2" />\n<ItemImage id="ae2:controller"/>\n')
    assert solo == []

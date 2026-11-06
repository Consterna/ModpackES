"""Casos límite de los módulos: lang con textos difíciles, scripts con codificaciones raras y archivos dañados."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import lang_json, lang_legacy
from traductor_es.fuentes import vanilla
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.libros import Libros
from traductor_es.modulos.misiones import HQM, BetterQuesting, FTBQuests, Heracles
from traductor_es.modulos.mods import Mods
from traductor_es.modulos.scripts import ScriptsKubeJS
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import enmascarar
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica

DIFICILES = {
    "item.m.a": "Iron Plate",
    "item.m.b": "§aGreen %s with %d items §r and %1$s",
    "item.m.c": 'Say "hello" \\ back\\slash and {0} and ${x}',
    "item.m.d": "Línea uno\nLínea dos con tab\tfin",
    "item.m.e": "Ñandú ¡Ágüita! cañón 日本語 😀 click here",
    "item.m.f": "Visit https://example.com/a_b?x=1&y=2 now please",
    "item.m.g": "%s",  # solo un código: no hay nada que traducir
    "item.m.h": "<b>Bold</b> text and <br> a break",
}


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


@pytest.fixture(autouse=True)
def _sin_lanzadores(monkeypatch: pytest.MonkeyPatch) -> None:

    def sin_lanzadores() -> list[Path]:
        return []  # sin el juego real del PC

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", sin_lanzadores)


def _traducir_mods(juego: Path, memoria: Memoria) -> Path:
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        resumen = traducir_modulo(Mods(ctx), Traductor(Simulador(), memoria, Glosario()))
        assert resumen.archivos
        return ctx.pack_listo().raiz


def test_mods_modernos_producen_json_valido_con_los_mismos_codigos(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", DIFICILES))
    pack = _traducir_mods(juego, memoria)
    json.loads((pack / "pack.mcmeta").read_text(encoding="utf-8"))
    for variante in VARIANTES:
        ruta = pack / "assets" / "m" / "lang" / f"{variante}.json"
        crudo = ruta.read_bytes()
        crudo.decode("utf-8")  # UTF-8 puro
        assert not crudo.startswith(b"\xef\xbb\xbf")
        textos = json.loads(crudo)  # JSON válido
        assert set(textos) <= set(DIFICILES)
        for clave, valor in textos.items():
            assert sorted(enmascarar(valor).tokens) == sorted(enmascarar(DIFICILES[clave]).tokens), (variante, clave)
        assert textos["item.m.e"] == "«ES» Ñandú ¡Ágüita! cañón 日本語 😀 click here"
        assert "item.m.g" not in textos  # sin nada que traducir no se inventa nada


def test_mods_legacy_lang_sin_saltos_de_linea_reales(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.12.2")
    textos = {k: v for k, v in DIFICILES.items() if "\n" not in v}
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", textos, legacy=True))
    pack = _traducir_mods(juego, memoria)
    for ruta in (pack / "assets" / "m" / "lang").glob("*.lang"):
        crudo = ruta.read_bytes()
        crudo.decode("utf-8")
        leidos = lang_legacy.leer(crudo)
        assert set(leidos) <= set(textos)
        for clave, valor in leidos.items():
            assert sorted(enmascarar(valor).tokens) == sorted(enmascarar(textos[clave]).tokens)
    assert any((pack / "assets" / "m" / "lang").glob("*.lang"))


def test_lang_vacio_roto_o_sin_texto_no_detiene_a_los_demas(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "vacio.jar", {"assets/v/lang/en_us.json": "{}"})
    fabrica.jar(juego / "mods" / "roto.jar", {"assets/r/lang/en_us.json": '{"a": "Hello there'})
    fabrica.jar(juego / "mods" / "mixto.jar", {"assets/x/lang/en_us.json": '{"a": 5, "b": null, "c": "Hello there"}'})
    fabrica.jar(juego / "mods" / "bueno.jar", fabrica.lang("m", "en_us", {"item.m.a": "Iron Plate"}))
    pack = _traducir_mods(juego, memoria)
    assert json.loads((pack / "assets" / "m" / "lang" / "es_mx.json").read_text("utf-8")) == {
        "item.m.a": "«ES» Iron Plate"
    }
    assert json.loads((pack / "assets" / "x" / "lang" / "es_mx.json").read_text("utf-8")) == {"c": "«ES» Hello there"}


# ------------------------------------------------------------------ scripts
def _script(tmp_path: Path, contenido: bytes) -> tuple[Path, Path]:
    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = juego / "kubejs" / "server_scripts" / "s.js"
    ruta.parent.mkdir(parents=True)
    ruta.write_bytes(contenido)
    return juego, ruta


def _correr(juego: Path, memoria: Memoria, avisos: list[str] | None = None) -> int:
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), registro=(avisos.append if avisos is not None else lambda _m: None))
        return traducir_modulo(ScriptsKubeJS(ctx), Traductor(Simulador(), memoria, Glosario())).traducidos


def test_script_con_bom_y_crlf_se_conserva(tmp_path: Path, memoria: Memoria) -> None:
    fuente = "﻿PlayerEvents.chat(e => {\r\n  e.player.tell('Hello there ñ')\r\n})\r\n".encode()
    juego, ruta = _script(tmp_path, fuente)
    assert _correr(juego, memoria) == 1
    nuevo = ruta.read_bytes()
    assert nuevo.startswith(b"\xef\xbb\xbf") and nuevo.count(b"\r\n") == 3 and "«ES» Hello there ñ".encode() in nuevo


@pytest.mark.parametrize(
    "contenido",
    [
        b"",
        b"\n\n",
        b"// solo un comentario 'x'\n",
        b"let a = 'sin cerrar\n",
        b"x.tell('\xe9\xe9 latin-1')\n",
        b"\x00\x01\x02",
        b"`${",
    ],
)
def test_script_vacio_roto_o_con_otra_codificacion_se_deja_igual(
    tmp_path: Path, memoria: Memoria, contenido: bytes
) -> None:
    juego, ruta = _script(tmp_path, contenido)
    avisos: list[str] = []
    assert _correr(juego, memoria, avisos) == 0
    assert ruta.read_bytes() == contenido


def test_script_enorme(tmp_path: Path, memoria: Memoria) -> None:
    cuerpo = "".join(f"e.player.tell('Mensaje número {i} para ti')\n" for i in range(5000)).encode()
    juego, ruta = _script(tmp_path, cuerpo)
    assert _correr(juego, memoria) == 5000
    assert ruta.read_text("utf-8").count("«ES»") == 5000


# ------------------------------------------------------------------ misiones y libros dañados
@pytest.mark.parametrize(
    ("modulo", "ruta", "contenido"),
    [
        (FTBQuests, "config/ftbquests/quests/chapters/a.snbt", b'{ title: "sin cerrar '),
        (FTBQuests, "config/ftbquests/quests/chapters/b.snbt", b"\xff\xfe\x00 no utf8"),
        (FTBQuests, "config/ftbquests/quests/chapters/c.nbt", b"\x1f\x8b\x08 gzip roto"),
        (BetterQuesting, "config/betterquesting/DefaultQuests.json", b'{"questDatabase:9": {'),
        (HQM, "config/hqm/quests.json", b"no es json"),
        (Heracles, "config/heracles/quests/q.json", b"\xff\xfe"),
    ],
)
def test_mision_danada_se_deja_igual_sin_reventar(
    tmp_path: Path, memoria: Memoria, modulo: type, ruta: str, contenido: bytes
) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    destino = juego / ruta
    destino.parent.mkdir(parents=True)
    destino.write_bytes(contenido)
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        m = modulo(ctx)
        if m.detectar():
            traducir_modulo(m, Traductor(Simulador(), memoria, Glosario()))
    assert destino.read_bytes() == contenido


def test_libro_con_json_roto_y_libro_bueno(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    libros = juego / "patchouli_books" / "guia"
    (libros / "en_us" / "entries").mkdir(parents=True)
    (libros / "book.json").write_text(
        json.dumps({"name": "Guide book", "landing_text": "Welcome to the guide."}), "utf-8"
    )
    (libros / "en_us" / "entries" / "roto.json").write_text('{"name": "Roto', "utf-8")
    (libros / "en_us" / "entries" / "bueno.json").write_text(
        json.dumps(
            {
                "name": "Good entry",
                "category": "x",
                "pages": [{"type": "patchouli:text", "text": "Hello $(l)there$()."}],
            }
        ),
        "utf-8",
    )
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        modulo = Libros(ctx)
        if modulo.detectar():
            traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
    assert (libros / "en_us" / "entries" / "roto.json").read_text("utf-8") == '{"name": "Roto'
    salida = json.dumps(lang_json.leer("{}"))  # el lector de lang sigue sano
    assert salida == "{}"


# ------------------------------------------------------------------ datos (funciones, logros, tips) raros
def test_datos_con_formas_inesperadas_no_revientan(tmp_path: Path, memoria: Memoria) -> None:
    from traductor_es.modulos.datos import Datos

    juego = fabrica.prism(tmp_path, "1.20.1")
    base = juego / "kubejs" / "data" / "a"
    casos = {
        "advancements/texto.json": json.dumps({"display": "no es un objeto"}),
        "advancements/lista.json": json.dumps(["x", {"display": {"title": "Hi there"}}]),
        "advancements/nulos.json": json.dumps({"display": {"title": None, "description": 5}}),
        "advancements/bom.json": "\ufeff"
        + json.dumps({"display": {"title": "Big Win", "description": {"translate": "k"}}}),
        "functions/macro.mcfunction": '$tellraw @a {"text":"$(x) hello there"}\n',
        "functions/vacia.mcfunction": "",
        "functions/latin.mcfunction": None,  # bytes que no son UTF-8
    }
    for rel, contenido in casos.items():
        ruta = base / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if contenido is None:
            ruta.write_bytes(b"say \xe9\xe9 hola\n")
        else:
            ruta.write_text(contenido, encoding="utf-8")
    antes = {p: p.read_bytes() for p in base.rglob("*") if p.is_file()}
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        traducir_modulo(Datos(ctx), Traductor(Simulador(), memoria, Glosario()))
    despues = {p: p.read_bytes() for p in base.rglob("*") if p.is_file()}
    cambiados = sorted(p.name for p in antes if antes[p] != despues[p])
    assert cambiados == ["bom.json"]  # solo el logro bueno: lo raro se deja igual
    assert json.loads((base / "advancements" / "bom.json").read_text("utf-8"))["display"]["title"] == "«ES» Big Win"


def test_zip_danado_se_ignora(tmp_path: Path, memoria: Memoria) -> None:
    from traductor_es.modulos.datos import Datos

    juego = fabrica.prism(tmp_path, "1.20.1")
    (juego / "datapacks").mkdir()
    (juego / "datapacks" / "roto.zip").write_bytes(b"PK\x03\x04 no es un zip de verdad")
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        assert not Datos(ctx).detectar()


@pytest.mark.parametrize("namespace", ["..", "a:b", "nul", "COM1.x", "con.", "trailing ", "a|b"])
def test_namespace_imposible_no_tumba_el_resto(tmp_path: Path, memoria: Memoria, namespace: str) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    avisos: list[str] = []
    fabrica.jar(
        juego / "mods" / "x.jar",
        {
            f"assets/{namespace}/lang/en_us.json": '{"a": "Hello there"}',
            **fabrica.lang("ok", "en_us", {"b": "Good one"}),
        },
    )
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst), registro=avisos.append)
        resumen = traducir_modulo(Mods(ctx), Traductor(Simulador(), memoria, Glosario()))
        pack = ctx.pack_listo().raiz
    assert json.loads((pack / "assets" / "ok" / "lang" / "es_mx.json").read_text("utf-8")) == {"b": "«ES» Good one"}
    assert resumen.pendientes >= 1 and any("no se puede guardar" in a for a in avisos)
    assert not (tmp_path / "Pack" / "minecraft" / "lang").exists()  # nada se escribió fuera del pack

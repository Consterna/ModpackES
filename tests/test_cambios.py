"""Informe «qué cambió desde la última traducción»: índice en la marca del pack y comparación (solo lee)."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.__main__ import main
from traductor_es.fuentes import vanilla
from traductor_es.fuentes.instancia import Instancia
from traductor_es.fuentes.recursos import MARCA
from traductor_es.modulos.cambios import (
    VERSION_INDICE,
    Cambios,
    CambiosLugar,
    Lugar,
    comparar,
    huella,
    indice_de,
    leer_indice,
    mezclar,
    para_la_marca,
    sin_indice,
)
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    def ninguna() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", ninguna)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


# ---------------------------------------------------------------------- comparación pura


def _uno(cambios: list[CambiosLugar], donde: str) -> CambiosLugar:
    return next(c for c in cambios if c.donde == donde)


def test_comparar_por_claves() -> None:
    antes = indice_de([("mods", "Mods", [Lugar("m", {"a": "Wrench", "b": "Gear", "c": "Old"})])])
    ahora = [("mods", "Mods", [Lugar("m", {"a": "Wrench", "b": "Big Gear", "d": "New"})])]
    c = _uno(comparar(antes, ahora), "m")
    assert (c.nuevas, c.cambiadas, c.borradas, c.cantidad_borradas) == (["d"], ["b"], ["c"], 1)
    assert sorted(c.textos) == ["Big Gear", "New"]  # lo que habría que traducir
    assert "1 nuevas (d)" in str(c) and "1 cambiadas (b)" in str(c) and "1 borradas (c)" in str(c)


def test_comparar_en_orden_reconoce_insertados_y_reemplazados() -> None:
    antes = indice_de([("misiones", "FTB", [Lugar("a.snbt", ["Title", "First", "Second", "Gone"])])])
    # «Extra» se insertó, «Second» se reescribió en su sitio y «Gone» desapareció
    ahora = [("misiones", "FTB", [Lugar("a.snbt", ["Title", "Extra", "First", "Second!"])])]
    c = _uno(comparar(antes, ahora), "a.snbt")
    assert c.nuevas == ["Extra"] and c.cambiadas == ["Second!"] and c.cantidad_borradas == 1
    assert c.borradas == []  # un archivo en orden no tiene claves: solo se cuentan


def test_insertar_al_principio_no_marca_todo_como_cambiado() -> None:
    textos = [f"Quest number {i}" for i in range(300)]
    antes = indice_de([("misiones", "FTB", [Lugar("a.snbt", textos)])])
    c = _uno(comparar(antes, [("misiones", "FTB", [Lugar("a.snbt", ["Brand new quest", *textos])])]), "a.snbt")
    assert (c.nuevas, c.cambiadas, c.cantidad_borradas) == (["Brand new quest"], [], 0)


def test_sin_cambios_no_hay_lugares() -> None:
    lugares = [("mods", "Mods", [Lugar("m", {"a": "Wrench"})]), ("scripts", "JS", [Lugar("t.js", ["Hi there"])])]
    assert comparar(indice_de(lugares), lugares) == []
    assert Cambios([], "indice", "2026-01-02T03:04:05+00:00").resumen() == (
        "Desde la última traducción (2026-01-02): no cambió nada."
    )


def test_lugares_y_modulos_que_desaparecen() -> None:
    antes = indice_de([
        ("mods", "Mods", [Lugar("m", {"a": "Wrench"}), Lugar("viejo", {"x": "Bye", "y": "Old"})]),
        ("misiones", "FTB", [Lugar("a.snbt", ["One", "Two"])]),
    ])  # fmt: skip
    cambios = comparar(antes, [("mods", "Mods", [Lugar("m", {"a": "Wrench"})])])
    assert _uno(cambios, "viejo").borradas == ["x", "y"]  # el mod se quitó del modpack
    assert _uno(cambios, "a.snbt").cantidad_borradas == 2  # el módulo de misiones entero ya no está
    total = Cambios(cambios)
    assert (total.nuevas, total.cambiadas, total.borradas) == (0, 0, 4)


def test_mezclar_conserva_los_grupos_no_traducidos() -> None:
    anterior = indice_de([("mods", "Mods", [Lugar("m", {"a": "A"})]), ("misiones", "FTB", [Lugar("q", ["Q"])])])
    nuevo = indice_de([("mods", "Mods", [Lugar("m", {"a": "B"})])])
    mezcla = mezclar(anterior, nuevo, ["mods"])
    assert mezcla["Mods"]["lugares"]["m"] == {"a": huella("B")} and "FTB" in mezcla
    assert "FTB" not in mezclar(anterior, nuevo, ["mods", "misiones"])  # se tradujo y ya no estaba: se va


def test_leer_indice_ignora_lo_que_no_entiende() -> None:
    assert leer_indice({}) is None
    assert leer_indice({"indice": "roto"}) is None
    assert leer_indice({"indice": {"version": VERSION_INDICE + 1, "modulos": {}}}) is None
    indice = indice_de([("mods", "Mods", [Lugar("m", {"a": "A"})])])
    datos = para_la_marca({**indice, "malo": "x"}, "2026-01-01")  # pyright: ignore[reportArgumentType]
    leido = leer_indice({"indice": datos})
    assert leido == (indice, "2026-01-01")


def test_sin_indice_cuenta_lo_que_falta() -> None:
    actuales = [("mods", "Mods", [Lugar("m", {"a": "Known", "b": "Unknown"})])]
    cambios = sin_indice(actuales, lambda _m, t: t == "Unknown")
    assert len(cambios) == 1 and cambios[0].nuevas == ["b"] and cambios[0].textos == ["Unknown"]
    assert Cambios(cambios, "memoria").resumen().startswith("Sin índice")


# ---------------------------------------------------------------------- marca del pack


def test_preparar_conserva_el_indice(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    with Instancia(juego) as inst:
        pack = PackSalida(inst)
        assert pack.leer_marca() == {}
        pack.guardar_indice({"version": VERSION_INDICE, "modulos": {}})
        assert not (pack.raiz / "pack.mcmeta").exists()  # sin pack.mcmeta el juego no usa la carpeta
        pack.preparar()
        marca = pack.leer_marca()
    assert marca["app"] == "ModpackES" and marca["indice"] == {"version": VERSION_INDICE, "modulos": {}}


# ---------------------------------------------------------------------- de punta a punta


def _modpack(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1")
    _mod(juego, {"item.m.wrench": "Wrench", "item.m.gear": "Gear", "item.m.old": "Old Thing"})
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text(
        '{ quests: [{ title: "Getting started" description: ["Craft your first tool."] }] }', encoding="utf-8"
    )
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _mod(juego: Path, textos: dict[str, str]) -> None:
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", textos))


def _actualizar_modpack(juego: Path) -> None:
    """Una versión nueva del modpack: una clave nueva, una cambiada, una borrada y una misión nueva."""
    _mod(juego, {"item.m.wrench": "Wrench", "item.m.gear": "Large Gear", "item.m.drill": "Drill"})
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.write_text(
        '{ quests: [{ title: "Getting started" description: ["Craft your first tool."] }'
        ' { title: "Digging deeper" description: ["Build a drill to mine faster."] }] }',
        encoding="utf-8",
    )


def test_traducir_guarda_el_indice_y_analizar_compara(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        primero = p.analizar()
        assert primero.cambios is not None and primero.cambios.base == "memoria"  # nunca se tradujo
        p.ejecutar(activar=False)
    marca_ruta = juego / "resourcepacks" / "Traduccion_ES" / MARCA
    leido = leer_indice(json.loads(marca_ruta.read_text("utf-8")))
    assert leido is not None
    indice, _fecha = leido
    assert set(indice["Textos de mods (objetos, bloques, menús)"]["lugares"]["m"]) == {
        "item.m.wrench", "item.m.gear", "item.m.old",
    }  # fmt: skip
    assert "config/ftbquests/quests/chapters/a.snbt" in indice["Misiones de FTB Quests"]["lugares"]

    # Sin cambios en el modpack: nada nuevo
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        igual = p.analizar()
    assert igual.cambios is not None and igual.cambios.base == "indice" and igual.cambios.lugares == []
    assert igual.diferencia.a_traducir == 0

    _actualizar_modpack(juego)
    antes = marca_ruta.read_bytes()
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        informe = p.analizar()
    assert marca_ruta.read_bytes() == antes  # analizar no escribe nada
    cambios = informe.cambios
    assert cambios is not None
    mod = _uno(cambios.lugares, "m")
    assert (mod.nuevas, mod.cambiadas, mod.borradas) == (["item.m.drill"], ["item.m.gear"], ["item.m.old"])
    mision = _uno(cambios.lugares, "config/ftbquests/quests/chapters/a.snbt")
    assert mision.nuevas == ["Digging deeper", "Build a drill to mine faster."] and not mision.cambiadas
    diferencia = informe.diferencia
    # «Drill», «Large Gear» y los dos textos de la misión nueva; lo demás ya está en la memoria
    assert diferencia.a_traducir == 4 and diferencia.a_traducir < informe.a_traducir + 4
    assert diferencia.costo("gemini-3.8-flash", False) is not None
    assert diferencia.costo("gemini-3.8-flash", False) <= informe.costo("gemini-3.8-flash", False)  # pyright: ignore[reportOperatorIssue]

    # Al traducir otra vez, el índice se pone al día
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar(activar=False)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        despues = p.analizar()
    assert despues.cambios is not None and despues.cambios.lugares == []


def test_traducir_solo_un_grupo_no_borra_el_indice_de_los_demas(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar(activar=False)
    _actualizar_modpack(juego)
    with Proceso(juego, Simulador(), grupos=["mods"], memoria=memoria) as p:
        p.ejecutar(activar=False)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        informe = p.analizar()
    assert informe.cambios is not None
    # Los mods quedaron al día; la misión nueva sigue apareciendo porque las misiones no se volvieron a traducir
    assert [c.donde for c in informe.cambios.lugares] == ["config/ftbquests/quests/chapters/a.snbt"]
    # Y analizar solo un grupo no hace pasar por borrado lo que no se leyó
    with Proceso(juego, Simulador(), grupos=["mods"], memoria=memoria) as p:
        solo_mods = p.analizar()
    assert solo_mods.cambios is not None and solo_mods.cambios.lugares == []


def test_linea_de_comandos_cambios(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    juego = _modpack(tmp_path)
    assert main(["cambios", str(juego)]) == 0
    salida = capsys.readouterr().out
    assert "No hay índice de una traducción anterior" in salida and "Sin índice" in salida
    assert main(["traducir", str(juego), "--simular", "--no-activar"]) == 0
    capsys.readouterr()
    _actualizar_modpack(juego)
    assert main(["cambios", str(juego)]) == 0
    salida = capsys.readouterr().out
    assert "Desde la última traducción" in salida and "1 nuevas (item.m.drill)" in salida
    assert salida.index("== Textos de mods") < salida.index("== Misiones de FTB Quests ==")
    assert "Para traducir solo lo nuevo y lo cambiado" in salida
    assert main(["analizar", str(juego)]) == 0
    assert "Detalle con «modpackes cambios»" in capsys.readouterr().out
    assert main(["cambios", str(juego), "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["base"] == "indice" and datos["nuevas"] == 3 and datos["cambiadas"] == 1 and datos["borradas"] == 1
    assert {"m", "config/ftbquests/quests/chapters/a.snbt"} == {lugar["donde"] for lugar in datos["lugares"]}
    assert main(["cambios", str(juego), "--motor", "lmstudio", "--lotes"]) == 1  # --lotes solo con Gemini


def test_el_texto_del_codigo_no_se_pierde_sin_java(tmp_path: Path, memoria: Memoria) -> None:
    """Traducir o analizar sin `--java` no borra del índice el texto del código ni lo cuenta como borrado."""
    from .test_cobertura import _clase  # pyright: ignore[reportPrivateUsage]

    juego = _modpack(tmp_path)
    fabrica.jar(juego / "mods" / "c.jar", {"com/c/Chat.class": _clase("literal", "You have been muted by an admin!")})
    with Proceso(juego, Simulador(), memoria=memoria, texto_java=True) as p:
        p.ejecutar(activar=False)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        sin_java = p.analizar()
        p.ejecutar(activar=False)
    assert sin_java.cambios is not None and sin_java.cambios.lugares == []
    with Proceso(juego, Simulador(), memoria=memoria, texto_java=True) as p:
        con_java = p.analizar()
    assert con_java.cambios is not None and con_java.cambios.lugares == []
    marca = json.loads((juego / "resourcepacks" / "Traduccion_ES" / MARCA).read_text("utf-8"))
    leido = leer_indice(marca)
    assert leido is not None and leido[0]["Texto del código de los mods"]["grupo"] == "java"

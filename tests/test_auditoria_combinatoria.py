"""Combinaciones de opciones de `traducir` (todos los pares de valores), con el motor simulado.

Para cada combinación: termina sin error; traducir otra vez no cambia ningún archivo; `restaurar` devuelve las
misiones y los scripts a sus bytes originales; `--no-activar` no toca `options.txt` y `--no-idioma` no cambia el idioma.
Los pares se cubren con un algoritmo goloso con semilla fija: siempre las mismas combinaciones.
"""

from __future__ import annotations

import hashlib
import itertools
import random
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest

from traductor_es.__main__ import main
from traductor_es.fuentes import vanilla

from . import fabrica

PARAMETROS: dict[str, tuple[object, ...]] = {
    "instancia": ("forge-1.20.1", "fabric-1.21.1", "forge-1.12.2", "neoforge-26.1.2"),
    "dialecto": ("es_mx", "es_es"),
    "tambien_es_es": (False, True),
    "solo": ("mods,libros,misiones,scripts", "mods", "misiones,scripts"),
    "calidad": ("economico", "equilibrado", "maximo"),
    "lotes": (False, True),
    "revisar": (False, True),
    "exhaustivo": (False, True),
    "hilos": (1, 8),
    "no_activar": (False, True),
    "no_idioma": (False, True),
}


def pares_cubiertos(parametros: Mapping[str, Sequence[object]], semilla: int = 0) -> list[dict[str, object]]:
    """Combinaciones que cubren cada par de valores de dos parámetros al menos una vez (goloso, determinista)."""
    nombres = list(parametros)
    faltan = {
        ((a, va), (b, vb))
        for a, b in itertools.combinations(nombres, 2)
        for va in parametros[a]
        for vb in parametros[b]
    }
    azar = random.Random(semilla)
    elegidas: list[dict[str, object]] = []
    while faltan:
        mejor: dict[str, object] | None = None
        puntos = -1
        par = next(iter(sorted(faltan, key=repr)))  # cada combinación arranca de un par que falta
        for _ in range(60):
            c = {n: azar.choice(list(parametros[n])) for n in nombres}
            c[par[0][0]], c[par[1][0]] = par[0][1], par[1][1]
            nuevos = sum(((a, c[a]), (b, c[b])) in faltan for a, b in itertools.combinations(nombres, 2))
            if nuevos > puntos:
                mejor, puntos = c, nuevos
        assert mejor is not None
        elegidas.append(mejor)
        faltan -= {((a, mejor[a]), (b, mejor[b])) for a, b in itertools.combinations(nombres, 2)}
    return elegidas


COMBINACIONES = pares_cubiertos(PARAMETROS)


def test_las_combinaciones_cubren_todos_los_pares() -> None:
    cubiertos = {((a, c[a]), (b, c[b])) for c in COMBINACIONES for a, b in itertools.combinations(list(PARAMETROS), 2)}
    total = sum(len(PARAMETROS[a]) * len(PARAMETROS[b]) for a, b in itertools.combinations(list(PARAMETROS), 2))
    assert len(cubiertos) == total
    assert len(COMBINACIONES) < 40  # mucho menos que el producto completo (≈ 9.000)


@pytest.fixture(autouse=True)
def _aislado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
    # la carpeta de datos de un usuario «José Núñez», con cirílico y kanji: memoria, registro y preferencias
    monkeypatch.setenv("TRADUCTOR_ES_DATOS", str(tmp_path / "José Núñez Пётр 東京" / "datos"))


def _instancia(base: Path, cual: str) -> Path:
    loader, version = cual.split("-")
    juego = fabrica.prism(base, version, loader)
    legacy = version == "1.12.2"
    fabrica.jar(
        juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench", "item.m.gear": "Gear"}, legacy)
    )
    quests = juego / "config" / "ftbquests" / "quests"
    if version == "26.1.2":
        (quests / "lang" / "en_us").mkdir(parents=True)
        (quests / "data.json5").write_text("{ version: 13 }", encoding="utf-8")
        (quests / "lang" / "en_us" / "c.json5").write_text('{"quest.0A.title": "Find Iron"}', encoding="utf-8")
    elif version == "1.21.1":
        (quests / "lang").mkdir(parents=True)
        (quests / "lang" / "en_us.snbt").write_text('{\n\tquest.0A.title: "Find Iron"\n}\n', encoding="utf-8")
    else:
        (quests / "chapters").mkdir(parents=True)
        (quests / "chapters" / "a.snbt").write_text('{ title: "Getting Started" }', encoding="utf-8")
    scripts = juego / "kubejs" / "client_scripts"
    scripts.mkdir(parents=True)
    evento = "onEvent('item.tooltip', e => { e.add('m:wrench', 'Turns bolts') })" if legacy else \
        "ItemEvents.tooltip(e => { e.add('m:wrench', 'Turns bolts') })"  # fmt: skip
    (scripts / "t.js").write_text(evento, encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _huellas(juego: Path, saltar: Sequence[str] = ()) -> dict[str, str]:
    return {
        p.relative_to(juego).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(juego.rglob("*"))
        if p.is_file() and not p.relative_to(juego).as_posix().startswith(tuple(saltar))
    }


def _argumentos(juego: Path, c: Mapping[str, object]) -> Iterator[str]:
    yield from ("traducir", str(juego), "--simular", "--dialecto", str(c["dialecto"]), "--solo", str(c["solo"]))
    yield from ("--calidad", str(c["calidad"]), "--hilos", str(c["hilos"]))
    for opcion in ("tambien_es_es", "lotes", "revisar", "exhaustivo", "no_activar", "no_idioma"):
        if c[opcion]:
            yield "--" + opcion.replace("_", "-")


@pytest.mark.parametrize("c", COMBINACIONES, ids=lambda c: "-".join(str(v) for v in c.values()))
def test_cada_combinacion(tmp_path: Path, c: dict[str, object]) -> None:
    juego = _instancia(tmp_path / "Mi Pack (1.20.1) [ES] ñandú", str(c["instancia"]))
    antes = _huellas(juego)
    opciones_antes = (juego / "options.txt").read_text(encoding="utf-8")
    argumentos = list(_argumentos(juego, c))
    assert main(argumentos) == 0
    opciones_despues = (juego / "options.txt").read_text(encoding="utf-8")
    if c["no_activar"]:
        assert opciones_despues == opciones_antes
    elif c["no_idioma"]:
        assert "lang:en_us" in opciones_despues
    # Otra vez: nada cambia (salvo las fechas del registro y de la marca del pack, a propósito: H-009)
    fechas = ("traductor_es/", "resourcepacks/Traduccion_ES/traductor_es.json")
    primera = _huellas(juego, fechas)
    assert main(argumentos) == 0
    assert _huellas(juego, fechas) == primera
    # Restaurar: los archivos del modpack vuelven a sus bytes originales (options.txt queda activado a propósito)
    assert main(["restaurar", str(juego)]) == 0
    despues = _huellas(juego, ("traductor_es/", "resourcepacks/"))
    for ruta, huella in antes.items():
        if ruta != "options.txt":
            assert despues.get(ruta) == huella, ruta

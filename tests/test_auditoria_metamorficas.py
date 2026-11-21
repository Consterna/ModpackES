"""Relaciones que deben cumplirse sin conocer la traducción correcta (pruebas metamórficas de punta a punta).

Usa el `Simulador` (determinista, sin gastar) sobre una instancia fabricada con mods, libros, misiones, scripts y
datapacks. Promesas del README que se comprueban: «analizar solo lee», «repetir no cambia nada», «restaurar
devuelve los originales» y «no modifica los jars».
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from traductor_es.fuentes import vanilla
from traductor_es.fuentes.recursos import MARCA
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

from . import fabrica

#: Archivos que la app escribe con la fecha de la corrida: se comparan sin ese campo.
_CON_FECHA = ("traductor_es/registro.json", f"resourcepacks/Traduccion_ES/{MARCA}")


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _modpack(base: Path, nombre: str = "Pack") -> Path:
    juego = fabrica.prism(base, "1.20.1", nombre=nombre)
    fabrica.jar(
        juego / "mods" / "m.jar",
        {
            **fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench", "item.m.gear": "Gear", "tip.m": "Use %s here"}),
            **fabrica.lang("m", "es_es", {"item.m.gear": "Engranaje"}),
            "assets/m/patchouli_books/guide/en_us/entries/e.json": {"name": "Using the Wrench", "pages": []},
        },
    )
    capitulos = juego / "config" / "ftbquests" / "quests" / "chapters"
    capitulos.mkdir(parents=True)
    (capitulos / "a.snbt").write_text(
        '{\n\ttitle: "Wrench"\n\tquests: [{\n\t\tid: "0A1B2C"\n\t\ttitle: "First steps"\n'
        '\t\tdescription: ["Craft your first tool.", "", "&aGood luck&r!"]\n\t}]\n}\n',
        encoding="utf-8",
    )
    script = juego / "kubejs" / "client_scripts" / "t.js"
    script.parent.mkdir(parents=True)
    script.write_text(
        "ItemEvents.tooltip(e => {\n  e.add('m:wrench', 'Rotates blocks')\n  if (x == 'Rotates') {}\n})\n",
        encoding="utf-8",
    )
    funcion = juego / "saves" / "Mundo" / "datapacks" / "dp" / "data" / "ns" / "functions" / "hola.mcfunction"
    funcion.parent.mkdir(parents=True)
    funcion.write_text('tellraw @a {"text":"Welcome to the server"}\ngive @p minecraft:diamond 1\n', encoding="utf-8")
    (juego / "saves" / "Mundo" / "datapacks" / "dp" / "pack.mcmeta").write_text(
        '{"pack": {"pack_format": 15, "description": "dp"}}', encoding="utf-8"
    )
    otra = juego / "config" / "otro_mod.toml"
    otra.write_text('nombre = "Do not touch"\n', encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _foto(juego: Path, con_fechas: bool = False, sin_jars: bool = False) -> dict[str, object]:
    """Huella de cada archivo de la instancia (y, si se pide, su fecha de modificación).

    `sin_jars`: para comparar dos instancias fabricadas por separado (los jars de prueba llevan la hora en que se
    crearon); que la app no toca los jars se comprueba aparte.
    """
    foto: dict[str, object] = {}
    for ruta in sorted(juego.rglob("*")):
        if not ruta.is_file() or (sin_jars and ruta.suffix == ".jar"):
            continue
        clave = ruta.relative_to(juego).as_posix()
        datos = ruta.read_bytes()
        if clave in _CON_FECHA:
            contenido: dict[str, Any] = json.loads(datos)
            contenido.pop("fecha", None)
            internos: list[dict[str, Any]] = (
                list(contenido.values()) if clave.endswith("registro.json") else [contenido.get("indice") or {}]
            )
            for valor in internos:
                valor.pop("fecha", None)
            datos = json.dumps(contenido, sort_keys=True).encode()
        huella = hashlib.sha256(datos).hexdigest()
        foto[clave] = (huella, ruta.stat().st_mtime_ns) if con_fechas else huella
    return foto


def _traducir(juego: Path, memoria: Memoria, motor: Simulador | None = None, **opciones: object) -> Simulador:
    motor = motor or Simulador()
    with Proceso(juego, motor, memoria=memoria, **opciones) as p:  # pyright: ignore[reportArgumentType]
        p.ejecutar()
    return motor


def test_analizar_y_cobertura_no_escriben_nada(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    antes = _foto(juego, con_fechas=True)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        informe = p.analizar()
        p.que_queda()
    assert informe.a_traducir > 0
    assert _foto(juego, con_fechas=True) == antes


def test_analizar_tras_traducir_tampoco_escribe(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    _traducir(juego, memoria)
    antes = _foto(juego, con_fechas=True)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.analizar()
        p.que_queda()
    assert _foto(juego, con_fechas=True) == antes


def test_traducir_dos_veces_es_igual_que_una_y_no_llama_al_motor(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    primero = _traducir(juego, memoria)
    assert primero.lotes_recibidos
    una = _foto(juego)
    segundo = _traducir(juego, memoria)
    assert _foto(juego) == una
    assert segundo.lotes_recibidos == []


def test_restaurar_devuelve_cada_original_byte_a_byte(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    antes = _foto(juego)
    for _ in range(3):  # tres traducciones seguidas no pisan la copia del original
        _traducir(juego, memoria)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.restaurar()
    despues = _foto(juego)
    cambiados = sorted(k for k, h in antes.items() if despues.get(k) != h)
    # options.txt no se restaura a propósito (el pack y el idioma quedan activos); todo lo demás vuelve igual
    assert cambiados == ["options.txt"]


def test_no_modifica_jars_ni_archivos_que_no_son_objetivo(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    jar_antes = (juego / "mods" / "m.jar").read_bytes()
    otro_antes = (juego / "config" / "otro_mod.toml").read_bytes()
    _traducir(juego, memoria)
    assert (juego / "mods" / "m.jar").read_bytes() == jar_antes
    assert (juego / "config" / "otro_mod.toml").read_bytes() == otro_antes
    funcion = (
        juego / "saves" / "Mundo" / "datapacks" / "dp" / "data" / "ns" / "functions" / "hola.mcfunction"
    ).read_text(encoding="utf-8")
    assert funcion.splitlines()[1] == "give @p minecraft:diamond 1"  # el comando que no es texto, intacto


def test_comparaciones_del_script_no_se_traducen(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    _traducir(juego, memoria)
    script = (juego / "kubejs" / "client_scripts" / "t.js").read_text(encoding="utf-8")
    assert "x == 'Rotates'" in script and "'m:wrench'" in script


@pytest.mark.parametrize("hilos", [1, 2, 16])
def test_numero_de_hilos_no_cambia_el_resultado(tmp_path: Path, hilos: int) -> None:
    referencia = _modpack(tmp_path / "ref")
    with Memoria(":memory:") as m:
        _traducir(referencia, m, hilos=4)
    otra = _modpack(tmp_path / "otra")
    with Memoria(":memory:") as m:
        _traducir(otra, m, hilos=hilos)
    assert _foto(otra, sin_jars=True) == _foto(referencia, sin_jars=True)


def test_carpeta_con_tildes_espacios_y_enye_da_el_mismo_resultado(tmp_path: Path) -> None:
    normal = _modpack(tmp_path / "a")
    with Memoria(":memory:") as m:
        _traducir(normal, m)
    rara = _modpack(tmp_path / "Ñandú y café (copia) 東京", nombre="Pack con espacios ñ")
    with Memoria(":memory:") as m:
        _traducir(rara, m)
    assert _foto(rara, sin_jars=True) == _foto(normal, sin_jars=True)


def test_aditividad_traducir_por_partes_es_traducir_todo(tmp_path: Path) -> None:
    """Traducir primero las misiones y luego el resto da lo mismo que traducir todo junto."""
    todo = _modpack(tmp_path / "todo")
    with Memoria(":memory:") as m:
        _traducir(todo, m)
    partes = _modpack(tmp_path / "partes")
    with Memoria(":memory:") as m:
        _traducir(partes, m, grupos=["misiones"])
        _traducir(partes, m)
    assert _foto(partes, sin_jars=True) == _foto(todo, sin_jars=True)


def test_copiar_la_instancia_traducida_y_restaurar_en_la_copia(tmp_path: Path, memoria: Memoria) -> None:
    """El registro guarda rutas relativas: la instancia se puede mover de carpeta y restaurar igual."""
    juego = _modpack(tmp_path / "origen")
    antes = _foto(juego)
    _traducir(juego, memoria)
    destino = tmp_path / "movida" / "Otra Carpeta"
    shutil.copytree(juego.parent, destino)
    copia = destino / juego.name
    with Proceso(copia, Simulador(), memoria=memoria) as p:
        p.restaurar()
    despues = _foto(copia)
    assert sorted(k for k, h in antes.items() if despues.get(k) != h) == ["options.txt"]


def test_datapack_en_zip_se_reescribe_conservando_orden_y_fechas(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    zip_ruta = juego / "saves" / "Mundo" / "datapacks" / "dz.zip"
    with zipfile.ZipFile(zip_ruta, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            zipfile.ZipInfo("pack.mcmeta", (2020, 1, 2, 3, 4, 6)), '{"pack":{"pack_format":15,"description":"x"}}'
        )
        z.writestr(zipfile.ZipInfo("data/z/functions/a.mcfunction", (2021, 5, 6, 7, 8, 10)), "say Hello there\n")
        z.writestr(zipfile.ZipInfo("data/z/otro.bin", (2022, 1, 1, 0, 0, 0)), b"\x00\x01binario")
    original = zip_ruta.read_bytes()
    _traducir(juego, memoria)
    with zipfile.ZipFile(zip_ruta) as z:
        assert [i.filename for i in z.infolist()] == ["pack.mcmeta", "data/z/functions/a.mcfunction", "data/z/otro.bin"]
        assert [i.date_time for i in z.infolist()] == [
            (2020, 1, 2, 3, 4, 6),
            (2021, 5, 6, 7, 8, 10),
            (2022, 1, 1, 0, 0, 0),
        ]
        assert z.read("data/z/otro.bin") == b"\x00\x01binario"
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.restaurar()
    assert zip_ruta.read_bytes() == original

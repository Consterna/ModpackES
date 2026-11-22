"""Tope de tamaño al leer entradas de jars y zips (H-004, decisión del usuario: 64 MiB por entrada).

Un jar de pocos KB puede declarar una entrada de cientos de MB («bomba» de compresión). La app no la descomprime:
la salta como si el archivo estuviera dañado, sigue con lo demás y lo avisa en el informe.
"""

from __future__ import annotations

import io
import tracemalloc
import zipfile
from pathlib import Path

import pytest

from traductor_es.fuentes import contenedores, vanilla
from traductor_es.fuentes.contenedores import MAXIMO_ENTRADA, EntradaDemasiadoGrande, Zip, leer_entrada
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

from . import fabrica


@pytest.fixture(autouse=True)
def _limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
    contenedores.DESCARTADAS.clear()


def _jar(ruta: Path, entradas: dict[str, bytes]) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, datos in entradas.items():
            z.writestr(nombre, datos)
    return ruta


def test_el_tope_es_64_mib() -> None:
    assert MAXIMO_ENTRADA == 64 * 2**20


def test_entrada_grande_no_se_ofrece_ni_se_lee(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contenedores, "MAXIMO_ENTRADA", 1000)
    jar = _jar(tmp_path / "m.jar", {"assets/m/lang/en_us.json": b"{" + b" " * 5000 + b"}", "chico.txt": b"hola"})
    z = Zip.abrir(jar)
    try:
        assert z.nombres() == ["chico.txt"]
        assert z.leer("chico.txt") == b"hola"
        with pytest.raises(zipfile.BadZipFile):  # los módulos ya saltan así un jar dañado
            z.leer("assets/m/lang/en_us.json")
    finally:
        z.cerrar()
    assert any("en_us.json" in d and "m.jar" in d for d in contenedores.DESCARTADAS)


def test_leer_entrada_con_nombre_o_con_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contenedores, "MAXIMO_ENTRADA", 10)
    jar = _jar(tmp_path / "a.zip", {"x": b"0123456789", "y": b"0123456789A"})
    with zipfile.ZipFile(jar) as z:
        assert leer_entrada(z, "x") == b"0123456789"  # justo en el tope: se lee
        assert leer_entrada(z, z.getinfo("x")) == b"0123456789"
        with pytest.raises(EntradaDemasiadoGrande):
            leer_entrada(z, "y")


def test_bomba_real_de_65_mib_no_se_descomprime_y_el_resto_se_traduce(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "bueno.jar", fabrica.lang("bueno", "en_us", {"item.bueno.x": "Iron Plate"}))
    _jar(juego / "mods" / "bomba.jar", {"assets/bomba/lang/en_us.json": b"{" + b" " * (65 * 2**20) + b"}"})
    assert (juego / "mods" / "bomba.jar").stat().st_size < 2**20  # ocupa menos de 1 MiB en disco
    tracemalloc.start()
    try:
        with Memoria(":memory:") as m, Proceso(juego, Simulador(), memoria=m) as p:
            analisis = p.analizar()
            informe = p.ejecutar()
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert pico < 40 * 2**20, f"pico de memoria {pico // 2**20} MiB"
    assert analisis.a_traducir >= 1
    for avisos in (analisis.avisos, informe.avisos):
        assert any("Salté 1 archivos de más de 64 MiB" in a and "bomba.jar" in a for a in avisos)
    lang = juego / "resourcepacks" / "Traduccion_ES" / "assets" / "bueno" / "lang" / "es_mx.json"
    assert "«ES» Iron Plate" in lang.read_text(encoding="utf-8")


def test_reescribir_un_datapack_zip_copia_por_trozos_lo_que_no_se_traduce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una entrada binaria más grande que el tope no impide traducir el .zip y vuelve igual byte a byte."""
    from traductor_es.modulos.datos import _reescribir_zip  # pyright: ignore[reportPrivateUsage]

    monkeypatch.setattr(contenedores, "MAXIMO_ENTRADA", 100)
    grande = bytes(range(256)) * 40
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("data/z/functions/a.mcfunction", (2021, 5, 6, 7, 8, 10)), "say Hello\n")
        z.writestr(zipfile.ZipInfo("data/z/structures/big.nbt", (2022, 1, 1, 0, 0, 0)), grande)
    original = buffer.getvalue()
    assert _reescribir_zip(original, {}) == original  # sin cambios: idéntico byte a byte
    nuevo = _reescribir_zip(original, {"data/z/functions/a.mcfunction": "say Hola\n"})
    with zipfile.ZipFile(io.BytesIO(nuevo)) as z:
        assert z.read("data/z/structures/big.nbt") == grande
        assert z.read("data/z/functions/a.mcfunction") == b"say Hola\n"
        assert z.getinfo("data/z/structures/big.nbt").date_time == (2022, 1, 1, 0, 0, 0)

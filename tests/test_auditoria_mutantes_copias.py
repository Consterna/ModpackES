"""Pruebas escritas para matar los mutantes que sobrevivían en `salida/copias.py` (puntaje de mutación 73 %).

Cada una cubre una decisión que ninguna prueba distinguía: el archivo creado por la app que vuelve a traducirse tras
restaurarlo, dos renovaciones de copia en el mismo segundo, una unión que apunta afuera al restaurar y los avisos
con más de cinco archivos.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from traductor_es.salida import copias
from traductor_es.salida.copias import ANTERIORES, CARPETA, Respaldo


def test_archivo_creado_restaurado_a_neutro_se_reconoce_como_de_la_app(tmp_path: Path) -> None:
    nuevo = tmp_path / "config" / "ftbquests" / "lang" / "es_mx.snbt"
    Respaldo(tmp_path).escribir(nuevo, b'{ a: "x" }', neutro=b"{\n}\n")
    Respaldo(tmp_path).restaurar()
    assert nuevo.read_bytes() == b"{\n}\n"
    r = Respaldo(tmp_path)
    assert r.original(nuevo) is None  # el contenido neutro no es un original del modpack
    r.escribir(nuevo, b'{ a: "y" }', neutro=b"{\n}\n")
    assert Respaldo(tmp_path).original(nuevo) is None
    assert not (tmp_path / CARPETA / "respaldo" / "config").exists()  # nunca se copió como si fuera original


def test_un_archivo_neutro_del_modpack_no_se_confunde_con_el_de_la_app(tmp_path: Path) -> None:
    """Si el modpack trae después un archivo distinto del neutro, ese sí es original."""
    nuevo = tmp_path / "lang" / "es_mx.snbt"
    Respaldo(tmp_path).escribir(nuevo, b'{ a: "x" }', neutro=b"{\n}\n")
    Respaldo(tmp_path).restaurar()
    nuevo.write_bytes(b'{ a: "del modpack" }')
    assert Respaldo(tmp_path).original(nuevo) == b'{ a: "del modpack" }'


def test_un_archivo_que_existia_y_vale_lo_mismo_que_el_neutro_no_es_nuestro(tmp_path: Path) -> None:
    ruta = tmp_path / "lang" / "es_es.snbt"
    ruta.parent.mkdir()
    ruta.write_bytes(b"{\n}\n")
    r = Respaldo(tmp_path)
    r.escribir(ruta, b'{ a: "x" }', neutro=b"{\n}\n")
    r.restaurar()
    assert ruta.read_bytes() == b"{\n}\n"
    datos = json.loads((tmp_path / CARPETA / "registro.json").read_text(encoding="utf-8"))
    assert datos["lang/es_es.snbt"]["existia"] is True  # vuelve de la copia, no del contenido neutro


def test_dos_renovaciones_en_el_mismo_segundo_no_se_pisan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Reloj:
        @staticmethod
        def now(tz: object = None) -> object:
            from datetime import UTC, datetime

            return datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)

    monkeypatch.setattr(copias, "datetime", Reloj)
    ruta = tmp_path / "kubejs" / "a.js"
    ruta.parent.mkdir()
    for version in (1, 2, 3):
        ruta.write_bytes(f"ORIGINAL v{version}".encode())  # el modpack se actualiza cada vez
        Respaldo(tmp_path).escribir(ruta, f"TRADUCIDO v{version}".encode())
    carpetas = sorted(p.name for p in (tmp_path / CARPETA / ANTERIORES).iterdir() if p.is_dir())
    assert carpetas == ["20261121T120000Z", "20261121T120000Z-2"]
    guardados = sorted(p.read_bytes() for p in (tmp_path / CARPETA / ANTERIORES).rglob("a.js"))
    assert guardados == [b"ORIGINAL v1", b"ORIGINAL v2"]


@pytest.mark.skipif(os.name != "nt", reason="las uniones (junctions) solo existen en Windows")
@pytest.mark.parametrize("unida", ["juego", "respaldo"])
def test_restaurar_no_sigue_una_union_que_apunta_afuera(tmp_path: Path, unida: str) -> None:
    juego = tmp_path / "inst"
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    ruta = juego / "kubejs" / "a.js"
    ruta.parent.mkdir(parents=True)
    ruta.write_bytes(b"ORIGINAL")
    Respaldo(juego).escribir(ruta, b"TRADUCIDO")
    # Después de traducir, alguien cambia una carpeta por una unión hacia afuera
    carpeta = juego / "kubejs" if unida == "juego" else juego / CARPETA / "respaldo" / "kubejs"
    if unida == "juego":
        (afuera / "a.js").write_bytes(b"TRADUCIDO")  # para que la huella coincida con la de la app
    else:
        (afuera / "a.js").write_bytes(b"COPIA FALSA")
    for hijo in carpeta.iterdir():
        hijo.unlink()
    carpeta.rmdir()
    subprocess.run(["cmd", "/c", "mklink", "/J", str(carpeta), str(afuera)], check=True, capture_output=True)
    try:
        Respaldo(juego).restaurar()
        assert (afuera / "a.js").read_bytes() in (b"TRADUCIDO", b"COPIA FALSA")  # no se escribió afuera
        if unida == "respaldo":
            assert ruta.read_bytes() == b"TRADUCIDO"  # ni se trajo la «copia» de afuera
    finally:
        carpeta.rmdir()


def test_aviso_de_cambiados_con_mas_de_cinco_archivos(tmp_path: Path) -> None:
    r = Respaldo(tmp_path)
    rutas = [tmp_path / "kubejs" / f"{i}.js" for i in range(7)]
    for ruta in rutas:
        ruta.parent.mkdir(exist_ok=True)
        ruta.write_bytes(b"ORIGINAL")
        r.escribir(ruta, b"TRADUCIDO")
    for ruta in rutas:
        ruta.write_bytes(b"ACTUALIZADO")
    r = Respaldo(tmp_path)
    r.restaurar()
    aviso = r.aviso_cambiados()
    assert aviso is not None and "No restauré 7 archivos" in aviso and "y 2 más" in aviso
    assert aviso.count(".js") == 5


def test_aviso_sin_copia_con_mas_de_cinco_archivos(tmp_path: Path) -> None:
    rutas = [tmp_path / "kubejs" / f"{i}.js" for i in range(6)]
    for ruta in rutas:
        ruta.parent.mkdir(exist_ok=True)
        ruta.write_bytes(b"ORIGINAL")
        Respaldo(tmp_path).escribir(ruta, b"TRADUCIDO")
    for copia in (tmp_path / CARPETA / "respaldo" / "kubejs").iterdir():
        copia.unlink()
    with pytest.raises(OSError, match=r"falta la copia de seguridad de 6: .* y 1 más"):
        Respaldo(tmp_path).restaurar()
    assert Respaldo(tmp_path).registrados("kubejs/") == sorted(f"kubejs/{i}.js" for i in range(6))

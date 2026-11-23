"""`traductor_es/anteriores/`: una carpeta por actualización y una poda que solo borra lo que sobra de verdad.

Política (recomendación de `.auditoria/investigacion/anteriores_y_estimador.md`, como `restic forget`): se conserva una
generación si es de las 3 últimas, si tiene menos de 90 días, si no tiene manifiesto o si algo suyo puede ser el
único inglés que queda (`sin_registro`, o en `respaldo/` ya no hay un inglés más nuevo).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from traductor_es.salida import copias
from traductor_es.salida.copias import ANTERIORES, CARPETA, Respaldo


class _Reloj:
    """Un `datetime` que avanza 10 s cada vez que se consulta (una corrida larga)."""

    def __init__(self, inicio: datetime) -> None:
        self.ahora = inicio

    def now(self, tz: object = None) -> datetime:
        self.ahora += timedelta(seconds=10)
        return self.ahora

    @staticmethod
    def strptime(texto: str, formato: str) -> datetime:
        return datetime.strptime(texto, formato)


def _archivos(juego: Path, n: int) -> list[Path]:
    rutas = [juego / "config" / "ftbquests" / "quests" / f"{i}.snbt" for i in range(n)]
    for ruta in rutas:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"ORIGINAL v1")
    return rutas


def _actualizar_y_traducir(juego: Path, rutas: list[Path], version: int) -> None:
    for ruta in rutas:
        ruta.write_bytes(f"ORIGINAL v{version}".encode())  # el modpack se actualizó
    r = Respaldo(juego)
    for ruta in rutas:
        r.escribir(ruta, f"TRADUCIDO v{version}".encode())


def _generaciones(juego: Path) -> list[str]:
    raiz = juego / CARPETA / ANTERIORES
    return sorted(p.name for p in raiz.iterdir() if p.is_dir()) if raiz.is_dir() else []


def _envejecer(juego: Path, dias: int) -> None:
    """Renombra cada generación (y su manifiesto) como si fuera de hace `dias` días, conservando el orden."""
    raiz = juego / CARPETA / ANTERIORES
    for i, nombre in enumerate(sorted(_generaciones(juego))):
        vieja = (datetime.now(UTC) - timedelta(days=dias) + timedelta(minutes=i)).strftime("%Y%m%dT%H%M%SZ")
        (raiz / nombre).rename(raiz / vieja)
        (raiz / f"{nombre}.json").rename(raiz / f"{vieja}.json")


def test_una_corrida_larga_deja_una_sola_carpeta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rutas = _archivos(tmp_path, 5)
    r = Respaldo(tmp_path)
    for ruta in rutas:
        r.escribir(ruta, b"TRADUCIDO v1")
    monkeypatch.setattr(copias, "datetime", _Reloj(datetime(2026, 11, 22, 10, 0, 0, tzinfo=UTC)))
    _actualizar_y_traducir(tmp_path, rutas, 2)  # cada archivo «tarda» 10 s
    assert len(_generaciones(tmp_path)) == 1


def test_el_manifiesto_anota_el_motivo(tmp_path: Path) -> None:
    (ruta,) = _archivos(tmp_path, 1)
    Respaldo(tmp_path).escribir(ruta, b"TRADUCIDO v1")
    _actualizar_y_traducir(tmp_path, [ruta], 2)
    (generacion,) = _generaciones(tmp_path)
    datos = json.loads((tmp_path / CARPETA / ANTERIORES / f"{generacion}.json").read_text(encoding="utf-8"))
    assert datos["archivos"]["config/ftbquests/quests/0.snbt"]["motivo"] == "actualizacion"


def test_sin_registro_el_motivo_es_sin_registro(tmp_path: Path) -> None:
    (ruta,) = _archivos(tmp_path, 1)
    Respaldo(tmp_path).escribir(ruta, b"TRADUCIDO v1")
    for nombre in ("registro.json", "registro.copia.json"):
        (tmp_path / CARPETA / nombre).unlink()
    Respaldo(tmp_path).escribir(ruta, b"TRADUCIDO otra vez")
    (generacion,) = _generaciones(tmp_path)
    datos = json.loads((tmp_path / CARPETA / ANTERIORES / f"{generacion}.json").read_text(encoding="utf-8"))
    assert datos["archivos"]["config/ftbquests/quests/0.snbt"]["motivo"] == "sin_registro"


def _cinco_actualizaciones(juego: Path) -> list[Path]:
    rutas = _archivos(juego, 2)
    r = Respaldo(juego)
    for ruta in rutas:
        r.escribir(ruta, b"TRADUCIDO v1")
    for version in range(2, 7):
        _actualizar_y_traducir(juego, rutas, version)
    assert len(_generaciones(juego)) == 5
    return rutas


def test_la_poda_conserva_las_tres_ultimas_si_son_viejas(tmp_path: Path) -> None:
    _cinco_actualizaciones(tmp_path)
    _envejecer(tmp_path, 200)
    antes = _generaciones(tmp_path)
    poda = Respaldo(tmp_path).podar_anteriores()
    assert sorted(poda.borradas) == antes[:2] and _generaciones(tmp_path) == antes[2:]
    assert poda.bytes > 0
    assert not (tmp_path / CARPETA / ANTERIORES / f"{antes[0]}.json").exists()


def test_la_poda_no_toca_lo_de_menos_de_90_dias(tmp_path: Path) -> None:
    _cinco_actualizaciones(tmp_path)
    _envejecer(tmp_path, 30)
    assert Respaldo(tmp_path).podar_anteriores().borradas == []
    assert len(_generaciones(tmp_path)) == 5


def test_simular_no_borra_nada(tmp_path: Path) -> None:
    _cinco_actualizaciones(tmp_path)
    _envejecer(tmp_path, 200)
    poda = Respaldo(tmp_path).podar_anteriores(simular=True)
    assert len(poda.borradas) == 2 and len(_generaciones(tmp_path)) == 5


def test_conservar_cero_deja_al_menos_una(tmp_path: Path) -> None:
    _cinco_actualizaciones(tmp_path)
    _envejecer(tmp_path, 200)
    Respaldo(tmp_path).podar_anteriores(conservar=0, dias=0)
    assert len(_generaciones(tmp_path)) == 1


def test_la_poda_nunca_borra_lo_que_puede_ser_el_unico_ingles(tmp_path: Path) -> None:
    _cinco_actualizaciones(tmp_path)
    _envejecer(tmp_path, 200)
    raiz = tmp_path / CARPETA / ANTERIORES
    vieja, sin_manifiesto = _generaciones(tmp_path)[:2]
    manifiesto = raiz / f"{vieja}.json"
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    for info in datos["archivos"].values():
        info["motivo"] = "sin_registro"
    manifiesto.write_text(json.dumps(datos), encoding="utf-8")
    (raiz / f"{sin_manifiesto}.json").unlink()  # como las de una versión anterior de la app
    assert Respaldo(tmp_path).podar_anteriores().borradas == []


def test_la_poda_no_borra_si_respaldo_ya_no_tiene_un_ingles_mas_nuevo(tmp_path: Path) -> None:
    rutas = _cinco_actualizaciones(tmp_path)
    _envejecer(tmp_path, 200)
    for ruta in rutas:  # la copia de respaldo desapareció: lo apartado es todo el inglés que queda
        (tmp_path / CARPETA / "respaldo" / ruta.relative_to(tmp_path)).unlink()
    assert Respaldo(tmp_path).podar_anteriores().borradas == []


def test_un_archivo_que_el_manifiesto_no_explica_frena_la_poda(tmp_path: Path) -> None:
    _cinco_actualizaciones(tmp_path)
    _envejecer(tmp_path, 200)
    vieja = _generaciones(tmp_path)[0]
    (tmp_path / CARPETA / ANTERIORES / vieja / "nota_del_usuario.txt").write_text("mío", encoding="utf-8")
    assert vieja not in Respaldo(tmp_path).podar_anteriores().borradas

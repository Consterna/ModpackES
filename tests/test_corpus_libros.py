"""Libros reales: la guía de AE2 descargada y los libros de las instancias del PC (en solo lectura)."""

from __future__ import annotations

import re
import shutil
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.fuentes.lanzadores import InstanciaEncontrada, buscar
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.libros import Libros
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida
from traductor_es.validacion.java import ValidadorJava

from . import fabrica

pytestmark = pytest.mark.corpus
AE2 = Path(__file__).resolve().parent.parent / ".descargas" / "jars" / "appliedenergistics2-26.1.13-beta.jar"
_SOLO_ETIQUETAS = re.compile(r"^\s*(?:</?[A-Za-z][^<>]*>\s*)+$")


class _SoloPack(Libros):
    """En instancias reales no se escriben los libros propios del modpack (irían dentro de la instancia)."""

    def _externos(self) -> dict[tuple[str, ...], dict[str, bytes]]:
        return {}


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _correr(juego: Path, tmp: Path, memoria: Memoria) -> tuple[list[Path], int]:
    with Instancia(juego) as inst:
        pack = PackSalida(inst)
        pack.raiz = tmp / "pack"
        ctx = Contexto(inst, Respaldo(tmp / "sin_uso"), pack=pack)
        resumen = traducir_modulo(_SoloPack(ctx), Traductor(Simulador(), memoria, Glosario()))
    return resumen.archivos, resumen.pendientes


def _validar(archivos: list[Path], validador: ValidadorJava, cp: list[Path]) -> None:
    jsons = [p for p in archivos if p.suffix == ".json"]
    malos = [r for r in validador.validar("json", jsons, cp) if not r.ok]
    assert not malos, malos[:3]
    for p in archivos:
        p.read_bytes().decode("utf-8")  # todo es UTF-8 válido


@pytest.mark.skipif(not AE2.is_file(), reason="Falta el jar de AE2 descargado")
def test_guia_de_ae2(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path / "inst", "26.1.2", "neoforge")
    shutil.copy(AE2, juego / "mods" / AE2.name)
    archivos, pendientes = _correr(juego, tmp_path, memoria)
    guias = [p for p in archivos if p.suffix == ".md"]
    assert len(guias) >= 7 * 100 and pendientes == 0
    with zipfile.ZipFile(AE2) as z:
        for p in guias[:40]:
            relativa = p.relative_to(tmp_path / "pack").as_posix()
            variante = relativa.split("/")[3]
            original = z.read(relativa.replace(variante + "/", "", 1)).decode("utf-8")
            traducido = p.read_text(encoding="utf-8")
            assert traducido.count("\n") == original.count("\n"), relativa  # misma estructura de líneas
            assert [x for x in original.split("\n") if _SOLO_ETIQUETAS.match(x)] == [
                x for x in traducido.split("\n") if _SOLO_ETIQUETAS.match(x)
            ], relativa  # las líneas que son solo etiquetas no se tocan


INSTANCIAS = [e for e in buscar() if e.nombre != "UniversoCraft"]


@pytest.mark.parametrize("encontrada", INSTANCIAS, ids=lambda e: f"{e.lanzador}:{e.nombre}")
def test_libros_de_instancias_reales(
    encontrada: InstanciaEncontrada,
    tmp_path: Path,
    memoria: Memoria,
    validador_java: ValidadorJava,
    cp_gson: list[Path],
) -> None:
    archivos, pendientes = _correr(encontrada.juego, tmp_path, memoria)
    assert pendientes == 0
    _validar(archivos, validador_java, cp_gson)
    assert not (tmp_path / "sin_uso" / "traductor_es").exists()

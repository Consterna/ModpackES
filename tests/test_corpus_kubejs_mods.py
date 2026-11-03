"""Scripts reales de KubeJS (copia de FC4) y el módulo de mods sobre todas las instancias del PC."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.fuentes.lanzadores import InstanciaEncontrada, buscar
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.mods import Mods
from traductor_es.modulos.scripts import ScriptsKubeJS
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida
from traductor_es.validacion.java import ValidadorJava

from . import fabrica

pytestmark = pytest.mark.corpus
FC4 = (
    Path(os.environ.get("APPDATA", Path.home())) / "PrismLauncher" / "instances" / "Farming Crossing 4(1)" / "minecraft"
)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _node_ok(ruta: Path) -> bool:
    node = shutil.which("node")
    assert node
    return subprocess.run([node, "--check", str(ruta)], capture_output=True, check=False).returncode == 0


@pytest.mark.skipif(not (FC4 / "kubejs").is_dir() or shutil.which("node") is None, reason="Falta FC4 o Node.js")
def test_scripts_reales_de_fc4(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    for carpeta in ("client_scripts", "server_scripts", "startup_scripts"):
        if (FC4 / "kubejs" / carpeta).is_dir():
            shutil.copytree(FC4 / "kubejs" / carpeta, juego / "kubejs" / carpeta)
    scripts = sorted((juego / "kubejs").rglob("*.js"))
    antes = {p: p.read_bytes() for p in scripts}
    validos_antes = {p for p in scripts if _node_ok(p)}
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        resumen = traducir_modulo(ScriptsKubeJS(ctx), Traductor(Simulador(), memoria, Glosario()))
        assert resumen.traducidos > 800 and resumen.pendientes == 0, resumen
        for p in resumen.archivos:
            if p in validos_antes:
                assert _node_ok(p), p.name  # sigue siendo JavaScript válido
        ScriptsKubeJS(ctx).restaurar()
    assert {p: p.read_bytes() for p in scripts} == antes


@pytest.mark.parametrize("encontrada", buscar(), ids=lambda e: f"{e.lanzador}:{e.nombre}")
def test_mods_en_instancias_reales(
    encontrada: InstanciaEncontrada,
    tmp_path: Path,
    memoria: Memoria,
    validador_java: ValidadorJava,
    cp_gson: list[Path],
) -> None:
    with Instancia(encontrada.juego) as inst:
        pack = PackSalida(inst)
        pack.raiz = tmp_path / "pack"
        ctx = Contexto(inst, Respaldo(tmp_path / "sin_uso"), pack=pack)
        resumen = traducir_modulo(Mods(ctx), Traductor(Simulador(), memoria, Glosario()))
        legacy = inst.legacy
    assert resumen.pendientes == 0
    if resumen.archivos and not legacy:
        malos = [r for r in validador_java.validar("json", resumen.archivos, cp_gson) if not r.ok]
        assert not malos, malos[:3]

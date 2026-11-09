"""Datos de texto reales (modpacks públicos de .descargas y tu FC4): siempre sobre copias en una carpeta temporal.

Para cada modpack: lo traducido sigue siendo válido (JSON, zips, JS), repetir no cambia nada y restaurar devuelve
los bytes originales. Los modpacks se bajan con `uv run python scripts/descargar_corpus.py`.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.cobertura import revisar_cobertura
from traductor_es.modulos.datos import Datos, buscar_archivos, buscar_zips
from traductor_es.modulos.scripts import ScriptsKubeJS
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo

from . import fabrica

pytestmark = pytest.mark.corpus

RAIZ = Path(__file__).resolve().parent.parent
DESCARGAS = RAIZ / ".descargas"
FC4 = (
    Path(os.environ.get("APPDATA", Path.home())) / "PrismLauncher" / "instances" / "Farming Crossing 4(1)" / "minecraft"
)
#: Lo que se copia de cada modpack: donde viven los datos de texto y los scripts.
CARPETAS = (
    "kubejs",
    "global_packs",
    "datapacks",
    "config/openloader",
    "config/paxi",
    "resourcepacks",
    "resources",
    "saves",
)
LOADERS = {"forge": "forge", "neoforge": "neoforge", "fabric-loader": "fabric", "quilt-loader": "quilt"}


def _packs() -> list[str]:
    return sorted(p.parent.name for p in DESCARGAS.glob("*/resumen.json"))


def _version_y_loader(slug: str) -> tuple[str, str | None]:
    resumen = cast("dict[str, Any]", json.loads((DESCARGAS / slug / "resumen.json").read_text(encoding="utf-8")))
    deps = cast("dict[str, str]", resumen["dependencias"])
    return deps["minecraft"], next((v for k, v in LOADERS.items() if k in deps), None)


def _copiar(origen: Path, juego: Path) -> None:
    for c in CARPETAS:
        if (origen / c).is_dir():
            shutil.copytree(origen / c, juego / c, dirs_exist_ok=True)


def _todos(juego: Path) -> dict[str, bytes]:
    return {p.relative_to(juego).as_posix(): p.read_bytes() for p in juego.rglob("*") if p.is_file()}


def _node() -> str | None:
    return shutil.which("node")


def _js_valido(ruta: Path) -> bool:
    node = _node()
    assert node
    return subprocess.run([node, "--check", str(ruta)], capture_output=True, check=False).returncode == 0


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _verificar(juego: Path, antes: dict[str, bytes]) -> int:
    """Lo cambiado sigue siendo válido. Devuelve cuántos archivos cambiaron."""
    cambiados = 0
    for rel, datos in _todos(juego).items():
        if rel.startswith("traductor_es/") or antes.get(rel) == datos:
            continue
        cambiados += 1
        if rel.endswith(".json"):
            json.loads(datos.decode("utf-8-sig"))
        elif rel.endswith(".mcfunction"):
            assert datos.count(b"\n") == antes[rel].count(b"\n"), rel  # ni se pierden ni se parten líneas
        elif rel.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(datos)) as z, zipfile.ZipFile(io.BytesIO(antes[rel])) as o:
                assert z.testzip() is None and z.namelist() == o.namelist(), rel
        elif rel.endswith(".js") and _node() and _js_valido(juego / rel) is False:
            ruta_antes = juego / rel
            ruta_antes.write_bytes(antes[rel])  # ¿ya era inválido antes?
            assert not _js_valido(ruta_antes), f"{rel} era JavaScript válido y la traducción lo rompió"
            ruta_antes.write_bytes(datos)
    return cambiados


def _probar(origen: Path, version: str, loader: str | None, tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, version, loader)
    _copiar(origen, juego)
    antes = _todos(juego)
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        if not (buscar_archivos(juego) or buscar_zips(juego) or ScriptsKubeJS(ctx).detectar()):
            pytest.skip("Este modpack no trae datos de texto ni scripts")
        traductor = Traductor(Simulador(), memoria, Glosario())
        for modulo in (Datos(ctx), ScriptsKubeJS(ctx)):
            traducir_modulo(modulo, traductor)
        assert _verificar(juego, antes) >= 0
        despues = _todos(juego)
        for modulo in (Datos(ctx), ScriptsKubeJS(ctx)):
            traducir_modulo(modulo, traductor)
        assert _todos(juego) == despues  # repetir no cambia nada
        revisar_cobertura(ctx)  # no debe fallar con ningún modpack
        Datos(ctx).restaurar()
        ScriptsKubeJS(ctx).restaurar()
    restaurado = {k: v for k, v in _todos(juego).items() if not k.startswith("traductor_es/")}
    assert restaurado == {k: v for k, v in antes.items() if not k.startswith("traductor_es/")}


@pytest.mark.parametrize("slug", _packs())
def test_datos_de_modpacks_descargados(slug: str, tmp_path: Path, memoria: Memoria) -> None:
    version, loader = _version_y_loader(slug)
    _probar(DESCARGAS / slug, version, loader, tmp_path, memoria)


@pytest.mark.skipif(not (FC4 / "kubejs").is_dir(), reason="Falta FC4")
def test_datos_de_fc4(tmp_path: Path, memoria: Memoria) -> None:
    _probar(FC4, "1.20.1", "forge", tmp_path, memoria)

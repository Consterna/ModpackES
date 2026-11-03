"""Misiones reales (tu FC4 y modpacks descargados), siempre sobre copias en una carpeta temporal."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import nbt
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo, unidades
from traductor_es.modulos.misiones import FTBQuests
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo
from traductor_es.validacion.java import ValidadorJava

from . import fabrica

pytestmark = pytest.mark.corpus

RAIZ = Path(__file__).resolve().parent.parent
PRISM = Path(os.environ.get("APPDATA", Path.home())) / "PrismLauncher" / "instances"
CASOS = {
    "fc4": (PRISM / "Farming Crossing 4(1)" / "minecraft" / "config" / "ftbquests", "1.20.1", "forge"),
    "bmc5": (RAIZ / ".descargas" / "better-mc-neoforge-bmc5" / "config" / "ftbquests", "1.21.1", "neoforge"),
    "prominence2": (RAIZ / ".descargas" / "prominence-2-fabric" / "config" / "ftbquests", "1.20.1", "fabric"),
    "supernova": (RAIZ / ".descargas" / "supernova-empires-2" / "config" / "ftbquests", "1.12.2", "forge"),
}


def _todos(carpeta: Path) -> dict[Path, bytes]:
    return {p.relative_to(carpeta): p.read_bytes() for p in carpeta.rglob("*") if p.is_file()}


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


@pytest.mark.parametrize("caso", list(CASOS))
def test_misiones_reales(
    caso: str, tmp_path: Path, memoria: Memoria, validador_java: ValidadorJava, cp_ftb_1201: list[Path]
) -> None:
    origen, version, loader = CASOS[caso]
    if not origen.is_dir():
        pytest.skip(f"No está {origen}")
    juego = fabrica.prism(tmp_path, version, loader)
    destino = juego / "config" / "ftbquests"
    shutil.copytree(origen, destino)
    antes = _todos(destino)
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        resumen = traducir_modulo(FTBQuests(ctx), Traductor(Simulador(), memoria, Glosario()))
        assert resumen.traducidos > 0 and resumen.pendientes == 0, resumen
        escritos = resumen.archivos
        # Los SNBT generados los lee el parser real de FTB Library, con la misma estructura que el original
        snbts = [p for p in escritos if p.suffix == ".snbt"]
        if snbts:
            originales = []
            for p in snbts:
                copia = tmp_path / "originales" / p.relative_to(juego)
                copia.parent.mkdir(parents=True, exist_ok=True)
                fuente = antes.get(p.relative_to(destino)) or (destino / "quests" / "lang" / "en_us.snbt").read_bytes()
                copia.write_bytes(fuente)
                originales.append(copia)
            leidos = validador_java.validar("snbt", [*snbts, *originales], cp_ftb_1201)
            malos = [r for r in leidos if not r.ok]
            assert not malos, malos[:3]
            canon = {r.ruta: r.detalle for r in leidos}
            for nuevo, viejo in zip(snbts, originales, strict=True):
                if "lang" not in nuevo.parts:  # en lang/ el archivo nuevo sale del en_us, no del mismo nombre
                    assert len(canon[nuevo].splitlines()) == len(canon[viejo].splitlines()), nuevo.name
        for p in (x for x in escritos if x.suffix == ".nbt"):
            raiz, _ = nbt.leer(p.read_bytes())
            titulos = [c.texto for c in nbt.cadenas(raiz) if c.campo == "title"]
            # Los que tienen texto se tradujeron; los que no (p. ej. «5000 $») quedan igual
            assert all(t.startswith("«ES» ") or not unidades(t) for t in titulos)
        # Segunda pasada: idéntica y sin llamadas al motor
        motor = Simulador()
        traducir_modulo(FTBQuests(ctx), Traductor(motor, memoria, Glosario()))
        assert motor.lotes_recibidos == []
        FTBQuests(ctx).restaurar()
    despues = _todos(destino)
    for ruta, datos in antes.items():
        assert despues[ruta] == datos, ruta  # todo vuelve byte a byte a como estaba
    nuevos = set(despues) - set(antes)
    assert all(despues[r] == b"{\n}\n" for r in nuevos)  # lo que creó la app queda neutro

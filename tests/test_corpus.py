"""Pruebas con las instancias reales del PC, en solo lectura. Lo que se genera va a una carpeta temporal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from traductor_es.formatos import lang_json, lang_legacy
from traductor_es.fuentes.instancia import Instancia
from traductor_es.fuentes.lanzadores import InstanciaEncontrada, buscar
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.salida.resource_pack import PackSalida
from traductor_es.validacion.java import ValidadorJava

pytestmark = pytest.mark.corpus

INSTANCIAS = buscar()


class PackDePrueba(PackSalida):
    """Igual que el pack real, pero escrito fuera de la instancia."""

    def __init__(self, instancia: Instancia, raiz: Path) -> None:
        super().__init__(instancia)
        self.raiz = raiz


def _ids(e: InstanciaEncontrada) -> str:
    return f"{e.lanzador}:{e.nombre}"


@pytest.mark.skipif(not INSTANCIAS, reason="No hay instancias de Minecraft en este PC")
@pytest.mark.parametrize("encontrada", INSTANCIAS, ids=_ids)
def test_instancia_real(
    encontrada: InstanciaEncontrada, tmp_path: Path, validador_java: ValidadorJava, cp_gson: list[Path]
) -> None:
    # Solo lo que la app lee (no las partidas guardadas, que pueden pesar gigas)
    vigiladas = [encontrada.juego / d for d in ("mods", "config", "resourcepacks", "kubejs", "global_packs")]
    antes = {
        p: p.stat().st_mtime_ns for carpeta in vigiladas if carpeta.is_dir() for p in carpeta.rglob("*") if p.is_file()
    }
    if (encontrada.juego / "options.txt").is_file():
        antes[encontrada.juego / "options.txt"] = (encontrada.juego / "options.txt").stat().st_mtime_ns
    with Instancia(encontrada.juego) as inst:
        assert inst.version is not None
        tabla = inst.tabla_idiomas()
        pendientes = tabla.pendientes(VARIANTES)
        pack = PackDePrueba(inst, tmp_path / "pack")
        pack.preparar()
        por_archivo: dict[tuple[str, str], dict[str, str]] = {}
        for p in pendientes:
            for variante in p.faltan:
                por_archivo.setdefault((p.namespace, variante), {})[p.clave] = p.existente or "«ES» " + p.ingles
        escritos = [pack.escribir_lang(ns, v, textos) for (ns, v), textos in por_archivo.items()]
        legacy = inst.legacy
    # El pack se puede leer de vuelta y trae exactamente lo escrito
    for (ns, v), textos in list(por_archivo.items())[:50]:
        ruta = escritos[list(por_archivo).index((ns, v))]
        leido = lang_legacy.leer(ruta.read_bytes()) if legacy else lang_json.leer(ruta.read_bytes())
        assert leido == dict(sorted(textos.items()))
    # Gson (el parser de Minecraft) acepta todos los JSON generados, en modo estricto
    if not legacy:
        jsons = [*escritos, pack.raiz / "pack.mcmeta"]
        malos = [r for r in validador_java.validar("json", jsons, cp_gson) if not r.ok]
        assert not malos, malos[:3]
    meta = json.loads((pack.raiz / "pack.mcmeta").read_text(encoding="utf-8"))["pack"]
    assert ("pack_format" in meta) != ("min_format" in meta)
    # Nada de la instancia se modificó
    despues = {p: p.stat().st_mtime_ns for p in antes if p.exists()}
    assert despues == antes

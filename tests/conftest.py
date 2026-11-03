"""Recursos compartidos de las pruebas. Lo que depende del PC (JDK, Prism, corpus) se salta si no está."""

from __future__ import annotations

import os
from pathlib import Path

import keyring
import pytest
from keyring.backends import fail

from traductor_es.validacion.java import ValidadorJava, biblioteca_mas_nueva, buscar_jdk

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / ".corpus"
PRISM = Path(os.environ.get("APPDATA", Path.home())) / "PrismLauncher"


@pytest.fixture(scope="session")
def validador_java(tmp_path_factory: pytest.TempPathFactory) -> ValidadorJava:
    jdk = buscar_jdk()
    if jdk is None:
        pytest.skip("No hay JDK disponible")
    v = ValidadorJava(jdk, tmp_path_factory.mktemp("clases_java"))
    v.compilar()
    return v


@pytest.fixture(scope="session")
def cp_gson() -> list[Path]:
    gson = biblioteca_mas_nueva(PRISM / "libraries", r"gson-[\d.]+\.jar")
    if gson is None:
        pytest.skip("No encuentro Gson en las bibliotecas de Prism")
    return [gson]


@pytest.fixture(scope="session")
def cp_ftb_1201() -> list[Path]:
    """Classpath del SNBT de FTB Library 1.20.1 (Forge): FTB Library, Minecraft con nombres SRG y log4j."""
    libs = PRISM / "libraries"
    srg = next(iter((libs / "net" / "minecraft" / "client").glob("1.20.1-*/client-1.20.1-*-srg.jar")), None)
    ftb = next(iter(CORPUS.glob("**/mods/ftb-library-forge-2001.*.jar")), None) or next(
        iter((PRISM / "instances").glob("*/minecraft/mods/ftb-library-forge-2001.*.jar")), None
    )
    api = biblioteca_mas_nueva(libs, r"log4j-api-2\.[\d.]+\.jar")
    core = biblioteca_mas_nueva(libs, r"log4j-core-2\.[\d.]+\.jar")
    comunes = [
        biblioteca_mas_nueva(libs, patron)
        for patron in (
            r"fastutil-[\d.]+\.jar",
            r"datafixerupper-[\d.]+\.jar",
            r"guava-[\d.]+-jre\.jar",
            r"failureaccess-[\d.]+\.jar",
            r"commons-lang3-[\d.]+\.jar",
            r"brigadier-[\d.]+\.jar",
            r"slf4j-api-[\d.]+\.jar",
        )
    ]
    if not (srg and ftb and api and core) or any(c is None for c in comunes[:2]):
        pytest.skip("Faltan jars de FTB Library 1.20.1 o de Minecraft SRG")
    return [ftb, srg, api, core, *(c for c in comunes if c is not None)]


@pytest.fixture(autouse=True, scope="session")
def _datos_de_la_app_en_temporal(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Ninguna prueba escribe la memoria, el glosario ni las preferencias reales del usuario."""
    os.environ["TRADUCTOR_ES_DATOS"] = str(tmp_path_factory.mktemp("datos_app"))
    os.environ.pop("GEMINI_API_KEY", None)
    keyring.set_keyring(fail.Keyring())  # ni se lee ni se escribe el almacén de credenciales real

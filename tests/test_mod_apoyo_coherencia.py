"""La tabla de versiones de la app, los proyectos de `mod-runtime/` y los rangos que declaran tienen que coincidir.

Si se añade una versión a `SOPORTADOS` sin que su proyecto la acepte, el jugador instalaría un mod que el juego
rechaza al abrirse; y un proyecto que ninguna entrada usa es un mod que nadie recibe. Esto lo vigila sin necesidad de
compilar nada.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from traductor_es.fuentes.version import Version
from traductor_es.salida.mod_apoyo import IMPOSIBLES, SOPORTADOS

RAIZ = Path(__file__).resolve().parent.parent
PROYECTOS = RAIZ / "mod-runtime"
#: Quilt carga el jar de Fabric, y NeoForge 1.20.1 (un fork de Forge) el de Forge 1.20.1.
FAMILIA_DEL_JAR = {"forge": "forge", "neoforge": "neoforge", "fabric": "fabric", "quilt": "fabric"}


def _propiedades(proyecto: str) -> dict[str, str]:
    texto = (PROYECTOS / proyecto / "gradle.properties").read_text(encoding="utf-8")
    pares = (linea.split("=", 1) for linea in texto.splitlines() if "=" in linea and not linea.startswith("#"))
    return {k.strip(): v.strip() for k, v in pares}


def _rango(proyecto: str) -> str:
    """El rango de Minecraft que declara el proyecto, tal cual (Fabric: `>=a <=b`; Forge y NeoForge: `[a,b)`)."""
    p = _propiedades(proyecto)
    return p.get("minecraft_range") or p.get("minecraft_version_range") or p["minecraft_version"]


def _acepta(rango: str, version: Version) -> bool:
    rango = rango.strip()
    if rango.startswith(("[", "(")):  # intervalo de Maven: [1.21,1.21.4) · [1.21.11]
        abre, cierra = rango[0], rango[-1]
        extremos = [e.strip() for e in rango[1:-1].split(",")]
        if len(extremos) == 1:
            return version == Version.de(extremos[0])
        inferior = Version.de(extremos[0])
        ok = version >= inferior if abre == "[" else version > inferior
        if extremos[1]:
            superior = Version.de(extremos[1])
            ok = ok and (version <= superior if cierra == "]" else version < superior)
        return ok
    if rango.startswith((">=", "<=", ">", "<")):  # rango de Fabric: >=1.20 <=1.20.2
        for condicion in rango.split():
            m = re.fullmatch(r"(>=|<=|>|<)(.+)", condicion)
            assert m, condicion
            limite = Version.de(m.group(2))
            if not {">=": version >= limite, "<=": version <= limite, ">": version > limite, "<": version < limite}[
                m.group(1)
            ]:
                return False
        return True
    return version == Version.de(rango)  # una sola versión


def _proyectos_de_mod_runtime() -> list[str]:
    return sorted(p.name for p in PROYECTOS.iterdir() if (p / "build.gradle").is_file())


def _construir_mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("construir_mod", RAIZ / "scripts" / "construir_mod.py")
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_cada_destino_de_la_tabla_es_un_proyecto_que_se_construye() -> None:
    destinos = set(SOPORTADOS.values())
    proyectos = set(_proyectos_de_mod_runtime())
    assert destinos <= proyectos, f"destinos sin proyecto en mod-runtime/: {sorted(destinos - proyectos)}"
    construibles = set(_construir_mod().PROYECTOS)
    assert construibles == proyectos, (
        f"proyectos que construir_mod.py no conoce o que ya no existen: {sorted(construibles ^ proyectos)}"
    )


def test_ningun_proyecto_queda_sin_usar() -> None:
    sin_usar = set(_proyectos_de_mod_runtime()) - set(SOPORTADOS.values())
    assert not sin_usar, f"proyectos que ninguna versión de la tabla recibe: {sorted(sin_usar)}"


@pytest.mark.parametrize(("clave", "destino"), sorted(SOPORTADOS.items()))
def test_la_version_cae_en_el_rango_de_su_proyecto(clave: tuple[str, tuple[int, ...]], destino: str) -> None:
    loader, partes = clave
    version = Version.de(".".join(str(n) for n in partes))
    rango = _rango(destino)
    assert _acepta(rango, version), f"{loader} {version} usa {destino}, que solo acepta {rango}"
    familia_del_jar = destino.split("-", maxsplit=1)[0]
    esperado = {FAMILIA_DEL_JAR[loader]}
    if (loader, partes) == ("neoforge", (1, 20, 1)):
        esperado = {"forge"}  # NeoForge 1.20.1 carga los mods de Forge 1.20.1
    assert familia_del_jar in esperado, f"{loader} {version} no puede usar el jar {destino}"


def test_lo_imposible_no_esta_tambien_soportado() -> None:
    assert not set(IMPOSIBLES) & set(SOPORTADOS)


@pytest.mark.parametrize(
    ("rango", "version", "esperado"),
    [
        (">=1.20 <=1.20.2", "1.20.1", True),
        (">=1.20 <=1.20.2", "1.20.3", False),
        ("[1.21,1.21.4)", "1.21.3", True),
        ("[1.21,1.21.4)", "1.21.4", False),
        ("[1.21.11]", "1.21.11", True),
        ("[1.21.11]", "1.21.10", False),
        ("1.19.4", "1.19.4", True),
        ("1.19.4", "1.19.3", False),
    ],
)
def test_el_lector_de_rangos(rango: str, version: str, esperado: bool) -> None:
    assert _acepta(rango, Version.de(version)) is esperado

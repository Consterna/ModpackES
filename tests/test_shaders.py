"""Idioma de los shaderpacks: se lee `shaders/lang/en_US.lang` y la traducción va al resource pack (Iris la prefiere)."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import propiedades
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.shaders import ESPACIO, Shaders
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.proceso import Proceso
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica

COMPLEMENTARY = (
    "# Complementary\n"
    "screen.LIGHTING=Lighting\n"
    "option.SHADOW_QUALITY=Shadow Quality\n"
    "option.SHADOW_QUALITY.comment=Higher values look better but cost \\\n"
    "    more performance.\n"
    "value.SHADOW_QUALITY.0=Low\n"
    "option.BLOOM=Bloom\n"
    "option.VERSION=r5.3\n"
)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def test_leer_properties_con_escapes_y_lineas_que_siguen() -> None:
    texto = "﻿! comentario\na=uno\nb : dos\nc tres\nd\\=e=f\ng=\\u00e9xito\\n\nh=primera \\\n   segunda\nvacia=\n"
    assert propiedades.leer(texto) == {
        "a": "uno", "b": "dos", "c": "tres", "d=e": "f", "g": "éxito\n", "h": "primera segunda", "vacia": "",
    }  # fmt: skip


def _instancia(tmp_path: Path, con_iris: bool = True) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1", "fabric")
    if con_iris:
        fabrica.jar(juego / "mods" / "iris-fabric-1.7.0+mc1.20.1.jar", {"fabric.mod.json": "{}"})
    shaders = juego / "shaderpacks"
    fabrica.jar(
        shaders / "Complementary.zip",
        {"shaders/lang/en_US.lang": COMPLEMENTARY, "shaders/lang/es_ES.lang": "option.BLOOM=Resplandor\n"},
    )
    # Otro shader en carpeta: repite «screen.LIGHTING» con el mismo inglés y «option.BLOOM» con otro
    lang = shaders / "BSL" / "shaders" / "lang"
    lang.mkdir(parents=True)
    (lang / "en_US.lang").write_text("screen.LIGHTING=Lighting\noption.BLOOM=Bloom Strength\n", encoding="utf-8")
    return juego


def test_traduce_al_resource_pack_y_respeta_lo_que_choca_y_el_espanol_del_shader(
    tmp_path: Path, memoria: Memoria
) -> None:
    juego = _instancia(tmp_path)
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        modulo = Shaders(ctx)
        assert modulo.detectar()
        enviados = {p.texto for p in modulo.recolectar()}
        resumen = traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        pack = ctx.pack_listo().raiz
    # «option.BLOOM» choca entre los dos shaders (distinto inglés): no se traduce. «r5.3» no es texto.
    assert enviados == {"Lighting", "Shadow Quality", "Higher values look better but cost more performance.", "Low"}
    assert len(resumen.archivos) == len(VARIANTES)
    es_mx = json.loads((pack / "assets" / ESPACIO / "lang" / "es_mx.json").read_text(encoding="utf-8"))
    assert es_mx["option.SHADOW_QUALITY"] == "«ES» Shadow Quality"
    assert es_mx["screen.LIGHTING"] == "«ES» Lighting"
    assert "option.BLOOM" not in es_mx and "option.VERSION" not in es_mx
    # El shaderpack no se toca
    assert not list((juego / "shaderpacks").rglob("*es_mx*"))


def test_el_espanol_que_trae_el_shader_se_copia_a_las_demas_variantes(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "fabric")
    fabrica.jar(juego / "mods" / "iris-1.7.0.jar", {"fabric.mod.json": "{}"})
    fabrica.jar(
        juego / "shaderpacks" / "S.zip",
        {"shaders/lang/en_US.lang": "option.A=Ambient Light\n", "shaders/lang/es_ES.lang": "option.A=Luz ambiental\n"},
    )
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        modulo = Shaders(ctx)
        assert modulo.recolectar() == []  # ya hay español: no se manda nada al motor
        traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        pack = ctx.pack_listo().raiz
    for variante in VARIANTES:
        tabla = json.loads((pack / "assets" / ESPACIO / "lang" / f"{variante}.json").read_text(encoding="utf-8"))
        assert tabla == {"option.A": "Luz ambiental"}


def test_sin_iris_ni_oculus_no_hace_nada(tmp_path: Path) -> None:
    juego = _instancia(tmp_path, con_iris=False)
    with Instancia(juego) as inst:
        modulo = Shaders(Contexto(inst, Respaldo(juego), pack=PackSalida(inst)))
        assert not modulo.detectar()
        assert modulo.recolectar() == []


def test_va_al_final_y_no_cambia_los_demas_modulos(tmp_path: Path, memoria: Memoria) -> None:
    """Las fuentes nuevas van después de las que ya existían: los pedidos de esas no cambian."""
    juego = _instancia(tmp_path)
    fabrica.jar(juego / "mods" / "mod.jar", fabrica.lang("mod", "en_us", {"item.mod.a": "Copper Gear"}))
    proceso = Proceso(juego, Simulador(), memoria=memoria)
    nombres = [m.nombre for _, m in proceso.modulos()]
    assert nombres[-1] == Shaders.nombre
    assert nombres.index("Textos de mods (objetos, bloques, menús)") < nombres.index(Shaders.nombre)

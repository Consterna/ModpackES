"""Casos límite que rompieron otras herramientas de traducción de modpacks
(`.auditoria/investigacion/herramientas_parecidas.md`, sección 4).

Un motor «hostil» devuelve lo que un modelo puede devolver mal (un salto de línea real, llaves nuevas, un «%» suelto,
comillas y barras) y se mira qué llega a los archivos: el `lang/es_mx.snbt` de FTB Quests y el `es_mx.json` del
resource pack. Nada puede dejar un archivo que el juego no lea o un formato que falle.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import snbt
from traductor_es.fuentes import vanilla
from traductor_es.motores.base import Lote
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

from . import fabrica

B = "\\"
EN = {
    "tip.m.lineas": "Line one\nLine two",
    "tip.m.args": "%s gave %s",
    "tip.m.plano": "Plain text",
    "tip.m.porciento": "Boost 50%% now %s",
}
#: Casos 1, 2, 5, 6 y 8: comillas y barras, «\\&» de FTB 2101, «\\n» escapado, la lista con páginas e imágenes
FTB = (
    "{\n"
    f'\tquest.0A1B2C3D4E5F6071.title: "Forbidden {B}{B}& Arcanus"\n'
    f'\tquest.0A1B2C3D4E5F6072.title: "The {B}"Big{B}" Hammer {B}{B} v2"\n'
    '\tquest.0A1B2C3D4E5F6073.quest_desc: ["Page one.", "", "{@pagebreak}", '
    '"{image:atm:textures/q.png width:100 height:50 align:center}", "Page two."]\n'
    f'\tquest.0A1B2C3D4E5F6074.subtitle: "Uno{B}nDos"\n'
    f'\tquest.0A1B2C3D4E5F6075.title: "&6&lGold {B}{B}& Glory"\n'
    '\tquest.0A1B2C3D4E5F6076.subtitle: "{atm9.quest.intro.subtitle}"\n'
    "}\n"
)


class Hostil(Simulador):
    def __init__(self, cambio: Callable[[str], str]) -> None:
        super().__init__()
        self.cambio = cambio

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        respuesta = super().traducir_lote(lote)
        if lote.tarea != "traducir":
            return respuesta
        return {e.id: self.cambio(e.texto) for e in lote.entradas}


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _traducir(tmp_path: Path, memoria: Memoria, cambio: Callable[[str], str]) -> tuple[dict[str, str], str]:
    juego = fabrica.prism(tmp_path, "1.21.1", "neoforge")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", EN))
    lang = juego / "config" / "ftbquests" / "quests" / "lang"
    lang.mkdir(parents=True)
    (lang / "en_us.snbt").write_text(FTB, encoding="utf-8")
    with Proceso(juego, Hostil(cambio), memoria=memoria) as p:
        p.ejecutar()
    js = juego / "resourcepacks" / "Traduccion_ES" / "assets" / "m" / "lang" / "es_mx.json"
    textos: dict[str, str] = json.loads(js.read_text(encoding="utf-8")) if js.is_file() else {}
    return textos, (lang / "es_mx.snbt").read_text(encoding="utf-8")


#: Lo que Minecraft acepta en un texto con formato (`TranslatableContents`): `%s`, `%n$s` y `%%`
_FORMATO_MC = re.compile(r"%(?:(\d+)\$)?([A-Za-z%]|$)")


def _formato_valido(texto: str) -> bool:
    return all(m.group(2) in ("s", "%") for m in _FORMATO_MC.finditer(texto))


def _snbt_igual_salvo_textos(salida: str) -> list[str]:
    """Las claves del lang de FTB salen en el mismo orden y con la lista de la descripción entera."""
    claves = re.findall(r"^\t(quest\.[0-9A-F]+\.\w+):", salida, flags=re.M)
    assert claves == re.findall(r"^\t(quest\.[0-9A-F]+\.\w+):", FTB, flags=re.M)
    return [c.texto for c in snbt.escanear(salida)]


def test_escapes_listas_y_marcadores_quedan_exactos(tmp_path: Path, memoria: Memoria) -> None:
    textos, salida = _traducir(tmp_path, memoria, lambda t: "ES " + t)
    assert f'"ES Forbidden {B}{B}& Arcanus"' in salida
    assert f'"ES The {B}"Big{B}" Hammer {B}{B} v2"' in salida
    assert f'"ES Uno{B}nDos"' in salida and "Uno\nDos" not in salida
    assert f'"ES &6&lGold {B}{B}& Glory"' in salida
    assert (
        '["ES Page one.", "", "{@pagebreak}", "{image:atm:textures/q.png width:100 height:50 align:center}", ' in salida
    )
    assert '"{atm9.quest.intro.subtitle}"' in salida  # una clave de traducción no se toca
    assert len(_snbt_igual_salvo_textos(salida)) == 10
    assert textos["tip.m.lineas"] == "ES Line one\nLine two"
    assert textos["tip.m.porciento"] == "ES Boost 50%% now %s"


#: Lo que un modelo puede agregar y rompería el archivo o el formato
_AGREGADOS = {"salto-real": "\nsegunda", "llaves-nuevas": " {x}", "porciento-pegado": " 50%de"}


@pytest.mark.parametrize("agregado", list(_AGREGADOS.values()), ids=list(_AGREGADOS))
def test_lo_que_romperia_el_archivo_o_el_formato_no_se_escribe(tmp_path: Path, memoria: Memoria, agregado: str) -> None:
    textos, salida = _traducir(tmp_path, memoria, lambda t: t + agregado)
    assert _snbt_igual_salvo_textos(salida) == [c.texto for c in snbt.escanear(FTB)]  # queda en inglés
    for clave, valor in textos.items():
        assert "\n" not in valor or clave == "tip.m.lineas"
        assert "{x}" not in valor
        assert _formato_valido(valor), (clave, valor)


def test_un_porciento_nuevo_con_argumentos_se_escapa(tmp_path: Path, memoria: Memoria) -> None:
    textos, _ = _traducir(tmp_path, memoria, lambda t: t + " un 50 %")
    assert textos["tip.m.args"] == "%s gave %s un 50 %%"
    assert textos["tip.m.porciento"] == "Boost 50%% now %s un 50 %%"
    # Sin argumentos se deja suelto: Minecraft muestra el texto tal cual si el formato no cuadra, y un «%%» se vería
    # doble en lo que un mod lee sin formatear
    assert textos["tip.m.plano"] == "Plain text un 50 %"


def test_comillas_y_barras_del_modelo_se_escapan(tmp_path: Path, memoria: Memoria) -> None:
    textos, salida = _traducir(tmp_path, memoria, lambda t: f'El "gran" {B} ' + t)
    leidos = _snbt_igual_salvo_textos(salida)
    assert f'El "gran" {B} Forbidden {B}& Arcanus' in leidos  # vuelve a leerse igual a lo que dijo el modelo
    assert textos["tip.m.plano"] == f'El "gran" {B} Plain text'

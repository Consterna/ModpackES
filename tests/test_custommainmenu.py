"""CustomMainMenu (1.12): botones, etiquetas y splash en su lugar; claves, fuentes y acciones intactas."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.custommainmenu import CustomMainMenu
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.proceso import Proceso
from traductor_es.salida.copias import Respaldo

from . import fabrica

MENU = {
    "buttons": {
        "singleplayer": {"text": "menu.singleplayer", "action": {"type": "openGui", "gui": "singleplayer"}},
        "discord": {
            "text": "Join our Discord",
            "hoverText": "Chat with the team",
            "action": {"type": "openLink", "link": "https://discord.gg/abc"},
        },
    },
    "labels": {
        "mojang": {"text": "Copyright Mojang AB. Do not distribute!", "posX": 2},
        "mods": {"text": "#modsactive# of #modsloaded# mods active"},
        "version": {"text": "web:https://example.com/version.txt"},
    },
    "other": {"splash-text": {"texts": ["Now with more dragons!", "file:splashes.txt"]}},
}


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _instancia(tmp_path: Path, bom: bool = False) -> Path:
    juego = fabrica.prism(tmp_path, "1.12.2", "forge")
    carpeta = juego / "config" / "CustomMainMenu"
    carpeta.mkdir(parents=True)
    datos = json.dumps(MENU, indent=2).encode("utf-8")
    (carpeta / "mainmenu.json").write_bytes((b"\xef\xbb\xbf" if bom else b"") + datos)
    return juego


def test_traduce_solo_el_texto_visible_y_restaura_byte_por_byte(tmp_path: Path, memoria: Memoria) -> None:
    juego = _instancia(tmp_path, bom=True)
    archivo = juego / "config" / "CustomMainMenu" / "mainmenu.json"
    antes = archivo.read_bytes()
    with Instancia(juego) as inst:
        modulo = CustomMainMenu(Contexto(inst, Respaldo(juego)))
        assert modulo.detectar()
        enviados = {p.texto for p in modulo.recolectar()}
        traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
    assert enviados == {"Join our Discord", "Chat with the team", "Copyright Mojang AB. Do not distribute!",
                        "Now with more dragons!", "{p0} of {p1} mods active"}  # fmt: skip
    crudo = archivo.read_bytes()
    assert crudo.startswith(b"\xef\xbb\xbf")  # el BOM se conserva
    datos = json.loads(crudo.decode("utf-8-sig"))
    assert datos["buttons"]["discord"]["text"] == "«ES» Join our Discord"
    assert datos["buttons"]["singleplayer"]["text"] == "menu.singleplayer"  # clave: la traduce el juego
    assert datos["buttons"]["discord"]["action"]["link"] == "https://discord.gg/abc"
    assert datos["labels"]["version"]["text"] == "web:https://example.com/version.txt"
    assert datos["labels"]["mods"]["text"] == "«ES» #modsactive# of #modsloaded# mods active"  # marcadores intactos
    assert datos["other"]["splash-text"]["texts"] == ["«ES» Now with more dragons!", "file:splashes.txt"]
    with Proceso(juego, Simulador(), memoria=memoria) as proceso:
        proceso.restaurar()
    assert archivo.read_bytes() == antes


def test_sin_carpeta_no_hace_nada(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.12.2", "forge")
    with Instancia(juego) as inst:
        assert not CustomMainMenu(Contexto(inst, Respaldo(juego))).detectar()

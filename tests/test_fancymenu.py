"""FancyMenu: el texto de los botones y textos del menú se traduce en su lugar, sin tocar acciones ni rutas."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.fancymenu import FancyMenu, valores_visibles
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.proceso import Proceso
from traductor_es.salida.copias import Respaldo

from . import fabrica

V3 = """type = fancymenu_layout

layout-meta {
  identifier = title_screen
}

element {
  button_element_executable_block_identifier = abc
  label = Report Issues
  hoverlabel = Report Issues
  description = Join us on Discord!
  element_type = custom_button
  instance_identifier = 1
}

element {
  source = Now Available!
  source_mode = direct
  element_type = splash_text
}

element {
  source = {"placeholder":"mcversion"} ({"placeholder":"loadedmods"} mods loaded)%n%Have fun
  source_mode = direct
  element_type = text_v2
}

element {
  source = %#FF5500%**COBBLE%#%VERSE** by Lumy
  source_mode = direct
  element_type = text_v2
}

element {
  source = [source:local]/config/fancymenu/assets/Hello World.txt
  source_mode = resource
  element_type = text_v2
}

element {
  description = {"placeholder":"local","values":{"key":"menu.quit"}}
  label = Quit
  element_type = vanilla_button
}

element {
  source = [source:local]/config/fancymenu/assets/logo.png
  element_type = image
}
"""

V2 = """type = menu

customization {
  action = addbutton
  value = openlink;https://discord.gg/abc
  label = Join the Discord
  description = Talk with other players
}

customization {
  action = addtext
  value = Welcome to the pack
}
"""


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _instancia(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1", "fabric")
    carpeta = juego / "config" / "fancymenu" / "customization"
    carpeta.mkdir(parents=True)
    (carpeta / "main.txt").write_bytes(V3.replace("\n", "\r\n").encode("utf-8"))  # Windows: CRLF
    (carpeta / "old.txt").write_text(V2, encoding="utf-8")
    return juego


def test_elige_solo_el_texto_visible_segun_el_bloque() -> None:
    valores = [v for _, v in valores_visibles(V3.split("\n"))]
    assert valores == [
        "Report Issues", "Report Issues", "Join us on Discord!", "Now Available!",
        '{"placeholder":"mcversion"} ({"placeholder":"loadedmods"} mods loaded)%n%Have fun',
        "%#FF5500%**COBBLE%#%VERSE** by Lumy",
        '{"placeholder":"local","values":{"key":"menu.quit"}}', "Quit",
    ]  # fmt: skip
    assert [v for _, v in valores_visibles(V2.split("\n"))] == [
        "Join the Discord", "Talk with other players", "Welcome to the pack",
    ]  # fmt: skip


def test_traduce_en_su_lugar_y_restaura_byte_por_byte(tmp_path: Path, memoria: Memoria) -> None:
    juego = _instancia(tmp_path)
    archivo = juego / "config" / "fancymenu" / "customization" / "main.txt"
    antes = archivo.read_bytes()
    antes_v2 = (archivo.parent / "old.txt").read_bytes()
    with Instancia(juego) as inst:
        modulo = FancyMenu(Contexto(inst, Respaldo(juego)))
        resumen = traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
    assert resumen.traducidos == 10
    texto = archivo.read_bytes().decode("utf-8")
    assert "  source = «ES» %#FF5500%**COBBLE%#%VERSE** by Lumy\r\n" in texto  # los colores vuelven exactos
    assert "  label = «ES» Report Issues\r\n" in texto
    assert "  description = «ES» Join us on Discord!\r\n" in texto
    assert "  source = «ES» Now Available!\r\n" in texto
    # los marcadores y el salto vuelven exactos
    assert (
        '  source = «ES» {"placeholder":"mcversion"} ({"placeholder":"loadedmods"} mods loaded)%n%Have fun\r\n' in texto
    )
    # ni rutas, ni la clave local, ni identificadores
    assert "source = [source:local]/config/fancymenu/assets/Hello World.txt" in texto
    assert 'description = {"placeholder":"local","values":{"key":"menu.quit"}}' in texto
    assert "button_element_executable_block_identifier = abc" in texto
    v2 = (archivo.parent / "old.txt").read_text(encoding="utf-8")
    assert "value = openlink;https://discord.gg/abc" in v2 and "value = «ES» Welcome to the pack" in v2
    # restaurar deja los bytes originales
    with Proceso(juego, Simulador(), memoria=memoria) as proceso:
        proceso.restaurar()
    assert archivo.read_bytes() == antes
    assert (archivo.parent / "old.txt").read_bytes() == antes_v2


def test_repetir_no_cambia_nada(tmp_path: Path, memoria: Memoria) -> None:
    juego = _instancia(tmp_path)
    archivo = juego / "config" / "fancymenu" / "customization" / "main.txt"
    copias: list[bytes] = []
    for _ in range(2):
        with Instancia(juego) as inst:
            traducir_modulo(FancyMenu(Contexto(inst, Respaldo(juego))), Traductor(Simulador(), memoria, Glosario()))
        copias.append(archivo.read_bytes())
    assert copias[0] == copias[1]
    assert "«ES» «ES»" not in archivo.read_text(encoding="utf-8")

"""BisectHost Menu: el título y la descripción del banner en su lugar; ids, comentarios y lo demás intactos."""

import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.bisecthost import BisectHost, desmarcar, marcar
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.proceso import Proceso
from traductor_es.salida.copias import Respaldo

from . import fabrica

CONFIG = (
    '#Your partner ID.\r\npartner_id = "6669"\r\npack_id = "18391"\r\n\r\n[modules]\r\n\r\n'
    "\t[modules.server_creator_banner]\r\n\t\tenabled = true\r\n\r\n"
    "\t\t[modules.server_creator_banner.pack]\r\n"
    '\t\t\t#The title to display at the top of the entry.\r\n\t\t\ttitle = "Need a server?"\r\n'
    '\t\t\tdescription = "Use CODE: LunaPixel for 25% OFF!" # cupón\r\n'
    "\t\t\tuse_language_files = false\r\n\r\n"
    "\t[modules.public_server_list.pack]\r\n"
    '\t\ttitle = "Not the banner"\r\n'
)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _instancia(tmp_path: Path, contenido: str) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1", "forge")
    (juego / "config").mkdir(parents=True)
    (juego / "config" / "bhmenu-client.toml").write_bytes(contenido.encode("utf-8"))
    return juego


def test_traduce_el_banner_protege_el_codigo_y_restaura_byte_por_byte(tmp_path: Path, memoria: Memoria) -> None:
    juego = _instancia(tmp_path, CONFIG)
    archivo = juego / "config" / "bhmenu-client.toml"
    with Instancia(juego) as inst:
        modulo = BisectHost(Contexto(inst, Respaldo(juego)))
        assert modulo.detectar()
        assert [p.texto for p in modulo.recolectar()] == ["Need a server?", "Use CODE: {p0} for 25% OFF!"]
        traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
    texto = archivo.read_bytes().decode("utf-8")
    datos = tomllib.loads(texto)
    banner = datos["modules"]["server_creator_banner"]["pack"]
    assert banner["title"] == "«ES» Need a server?"
    assert banner["description"] == "«ES» Use CODE: LunaPixel for 25% OFF!"  # el código llega exacto
    assert datos["modules"]["public_server_list"]["pack"]["title"] == "Not the banner"  # otra tabla: no se toca
    assert datos["partner_id"] == "6669" and "# cupón\r\n" in texto and texto.count("\r\n") == CONFIG.count("\r\n")
    with Proceso(juego, Simulador(), memoria=memoria) as proceso:
        proceso.restaurar()
    assert archivo.read_bytes().decode("utf-8") == CONFIG


def test_con_archivos_de_idioma_no_hace_nada(tmp_path: Path) -> None:
    juego = _instancia(tmp_path, CONFIG.replace("use_language_files = false", "use_language_files = true"))
    with Instancia(juego) as inst:
        assert BisectHost(Contexto(inst, Respaldo(juego))).recolectar() == []


def test_el_codigo_no_se_puede_perder() -> None:
    marcado, codigos = marcar("Use code LUNA25 now")
    assert marcado == "Use code {p0} now" and codigos == ["LUNA25"]
    assert desmarcar("Usa el código {p0} ya", codigos) == "Usa el código LUNA25 ya"
    assert desmarcar("Usa el código ya", codigos) is None  # el motor lo perdió: se deja en inglés

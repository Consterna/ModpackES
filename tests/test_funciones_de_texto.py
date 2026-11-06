"""Funciones del propio script que solo muestran texto: se traduce lo que se les pasa, y nada que pueda ser lógica."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes import vanilla
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.scripts import ScriptsKubeJS
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo

from . import fabrica


@pytest.fixture(autouse=True)
def _sin_lanzadores(monkeypatch: pytest.MonkeyPatch) -> None:
    def ninguno() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", ninguno)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _traducir(tmp_path: Path, memoria: Memoria, src: str) -> tuple[str, int]:
    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = juego / "kubejs" / "server_scripts" / "s.js"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(src, encoding="utf-8")
    with Instancia(juego) as inst:
        resumen = traducir_modulo(
            ScriptsKubeJS(Contexto(inst, Respaldo(juego))), Traductor(Simulador(), memoria, Glosario())
        )
    return ruta.read_text("utf-8"), resumen.traducidos


# Parámetros que solo se muestran, directamente o después de partirlos en líneas (como el tooltip de Create de un modpack real)
TEXTO_PURO = r"""
function aviso(player, msg) { player.tell(msg) }
const consejo = (evento, objeto, texto) => {
  texto = texto.trim()
  const lineas = texto.split('\n')
  lineas.forEach(linea => {
    evento.add(objeto, Text.of(linea).gold())
  })
}
const decir = (p, quien, frase) => { p.tell(`${quien}: ${frase}`) }
aviso(player, 'Welcome back to the farm')
consejo(e, 'minecraft:stone', 'Hold shift to see the summary\nIt can be mined with a pickaxe')
decir(player, 'Laly', 'The museum opens at dawn')
"""


def test_funciones_que_solo_muestran_texto(tmp_path: Path, memoria: Memoria) -> None:
    nuevo, n = _traducir(tmp_path, memoria, TEXTO_PURO)
    assert "aviso(player, '«ES» Welcome back to the farm')" in nuevo
    assert "'«ES» Hold shift to see the summary\\nIt can be mined with a pickaxe'" in nuevo
    assert "'«ES» The museum opens at dawn'" in nuevo  # `quien` y `frase` se muestran juntos en la plantilla
    assert "'minecraft:stone'" in nuevo and n >= 3


# Cada función usa su parámetro como lógica de algún modo: ninguna debe tocarse
PELIGROSAS = r"""
function comparar(p, texto) { if (texto == 'Open the door now') p.tell(texto) }
function buscar(p, texto) { if (texto.includes('door')) p.tell(texto) }
function guardar(p, texto) { p.persistentData.put(texto, 1); p.tell(texto) }
function devolver(texto) { return texto }
function mostrar_y_clave(p, texto) { p.tell(texto); p.data[texto] = true }
function por_plantilla(p, texto) { p.runCommand(`give @s ${texto}`) ; p.tell(texto) }
function como_valor(p, texto) { p.tell(texto) }
const alias = como_valor
function repetida(p, texto) { p.tell(texto) }
function repetida(p, texto) { p.tell(texto) }
comparar(player, 'Open the door now')
buscar(player, 'Look at the door here')
guardar(player, 'Some key with spaces')
devolver('Return this phrase please')
mostrar_y_clave(player, 'Another key with spaces')
por_plantilla(player, 'Some item with spaces')
como_valor(player, 'Called through a value')
repetida(player, 'Defined twice in the file')
"""


def test_si_el_parametro_es_logica_no_se_toca_nada(tmp_path: Path, memoria: Memoria) -> None:
    nuevo, n = _traducir(tmp_path, memoria, PELIGROSAS)
    assert nuevo == PELIGROSAS and n == 0


def test_un_metodo_con_el_mismo_nombre_no_es_la_funcion_del_script(tmp_path: Path, memoria: Memoria) -> None:
    src = "function aviso(p, msg) { p.tell(msg) }\ninventario.aviso(player, 'This is another object method')\n"
    nuevo, n = _traducir(tmp_path, memoria, src)
    assert nuevo == src and n == 0


def test_solo_la_posicion_del_parametro_y_nunca_ids(tmp_path: Path, memoria: Memoria) -> None:
    src = (
        "function aviso(p, msg, id) { p.tell(msg) }\naviso(player, 'Something to show here', 'quest id with spaces')\n"
    )
    nuevo, _ = _traducir(tmp_path, memoria, src)
    assert "'«ES» Something to show here'" in nuevo and "'quest id with spaces'" in nuevo


def test_el_id_que_va_en_una_plantilla_no_se_toca_pero_el_nombre_si(tmp_path: Path, memoria: Memoria) -> None:
    src = (
        "function crear(id, nombre) {\n"
        "  event.create(id).displayName(nombre).model(`kubejs:block/${id}`)\n"
        "}\n"
        "crear('plushie with spaces', 'Taidum Plushie')\n"
    )
    nuevo, _ = _traducir(tmp_path, memoria, src)
    assert "'plushie with spaces'" in nuevo and "'«ES» Taidum Plushie'" in nuevo

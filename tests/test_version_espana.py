"""Versión aparte para España: es_es recibe su propia traducción y lo demás sigue al dialecto elegido."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.__main__ import main
from traductor_es.formatos import snbt
from traductor_es.fuentes import vanilla
from traductor_es.motores.base import Lote
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import ETIQUETA_ESPANA, Proceso

from . import fabrica


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    def ninguna() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", ninguna)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


class PorDialecto(Simulador):
    """Marca cada traducción con el dialecto que pidió el pedido: «MX» o «ESP»."""

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.prefijo = "«ESP» " if "España" in lote.dialecto else "«MX» "
        return super().traducir_lote(lote)


def _modpack(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.21.1", "neoforge")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench"}))
    lang = juego / "config" / "ftbquests" / "quests" / "lang"
    lang.mkdir(parents=True)
    (lang / "en_us.snbt").write_text('{\n\tquest.A.title: "Find the hidden cave"\n}\n', encoding="utf-8")
    script = juego / "kubejs" / "client_scripts" / "t.js"
    script.parent.mkdir(parents=True)
    script.write_text("ItemEvents.tooltip(e => { e.add('m:wrench', 'Rotates blocks') })\n", encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _lang(juego: Path, variante: str) -> dict[str, str]:
    ruta = juego / "resourcepacks" / "Traduccion_ES" / "assets" / "m" / "lang" / f"{variante}.json"
    return json.loads(ruta.read_text("utf-8"))


def _mision(juego: Path, variante: str) -> str:
    ruta = juego / "config" / "ftbquests" / "quests" / "lang" / f"{variante}.snbt"
    return {c.campo: c.texto for c in snbt.escanear(ruta.read_text("utf-8"))}["quest.A.title"]


def test_es_es_recibe_su_propia_traduccion(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    with Proceso(juego, PorDialecto(), memoria=memoria, tambien_es_es=True) as p:
        analisis = p.analizar()
        espana = [m for m in analisis.modulos if m.nombre.endswith(ETIQUETA_ESPANA)]
        assert {m.grupo for m in espana} == {"mods", "misiones"}  # los scripts tienen un solo idioma
        assert all(m.textos == 0 and m.a_traducir > 0 for m in espana)  # suma al costo, no a los textos
        informe = p.ejecutar()
    assert _lang(juego, "es_mx")["item.m.wrench"] == "«MX» Wrench"
    assert _lang(juego, "es_ar")["item.m.wrench"] == "«MX» Wrench"  # las variantes de Latinoamérica siguen a es_mx
    assert _lang(juego, "es_es")["item.m.wrench"] == "«ESP» Wrench"
    assert _mision(juego, "es_mx") == "«MX» Find the hidden cave"
    assert _mision(juego, "es_es") == "«ESP» Find the hidden cave"
    # El script se traduce dentro de su archivo: un solo idioma, el elegido
    assert "«MX» Rotates blocks" in (juego / "kubejs" / "client_scripts" / "t.js").read_text("utf-8")
    assert any(m.nombre.endswith(ETIQUETA_ESPANA) for m in informe.modulos)
    # Las dos versiones quedan en la memoria, cada una en su dialecto
    assert memoria.obtener("Wrench", "es_mx", "ui") == "«MX» Wrench"
    assert memoria.obtener("Wrench", "es_es", "ui") == "«ESP» Wrench"


def test_repetir_no_vuelve_a_pedir_nada(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    with Proceso(juego, PorDialecto(), memoria=memoria, tambien_es_es=True) as p:
        p.ejecutar()
    motor = PorDialecto()
    with Proceso(juego, motor, memoria=memoria, tambien_es_es=True) as p:
        p.ejecutar()
    assert motor.lotes_recibidos == []  # todo sale de la memoria
    assert _lang(juego, "es_es")["item.m.wrench"] == "«ESP» Wrench"  # el pack no se vació entre pasadas
    assert _lang(juego, "es_mx")["item.m.wrench"] == "«MX» Wrench"


def test_sin_la_opcion_es_es_copia_el_dialecto_elegido(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    with Proceso(juego, PorDialecto(), memoria=memoria) as p:
        p.ejecutar()
    assert _lang(juego, "es_es")["item.m.wrench"] == "«MX» Wrench"
    assert _mision(juego, "es_es") == "«MX» Find the hidden cave"


def test_con_el_dialecto_espana_la_opcion_no_hace_nada(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    with Proceso(juego, PorDialecto(), "es_es", memoria=memoria, tambien_es_es=True) as p:
        assert not p.tambien_es_es
        p.ejecutar()
    assert _lang(juego, "es_mx")["item.m.wrench"] == "«ESP» Wrench"


def test_linea_de_comandos(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    juego = _modpack(tmp_path)
    assert main(["analizar", str(juego), "--tambien-es-es"]) == 0
    assert ETIQUETA_ESPANA.strip() in capsys.readouterr().out


def test_la_version_de_espana_recibe_la_latinoamericana_como_referencia(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    motor = PorDialecto()
    with Proceso(juego, motor, memoria=memoria, tambien_es_es=True) as p:
        p.ejecutar()
    pistas = [e.pista for lote in motor.lotes_recibidos if "España" in lote.dialecto for e in lote.entradas]
    assert pistas and all("en Latinoamérica" in pista for pista in pistas)
    assert any("««MX» Find the hidden cave»" in pista for pista in pistas)
    # La pasada principal no recibe nada de esto
    principales = [e.pista for lote in motor.lotes_recibidos if "España" not in lote.dialecto for e in lote.entradas]
    assert not any("en Latinoamérica" in pista for pista in principales)

"""Calidad, modo por lotes, el orquestador de punta a punta y la línea de comandos."""

import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from traductor_es.__main__ import main
from traductor_es.fuentes import vanilla
from traductor_es.motores.base import Lote
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import desenmascarar, enmascarar
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.proceso import Proceso
from traductor_es.validacion.calidad import revisar_glosario, validar

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


def test_validar() -> None:
    assert validar("Iron Plate", "Placa de hierro") is None
    assert validar("Hello", "  ") == "vacía"
    assert validar("Craft a table", "Fabrica\nuna mesa") == "salto de línea nuevo"
    assert validar("Place the block on the ground", "x") == "largo raro"
    texto = "Place the item into the machine and wait for it"
    assert validar(texto, texto) == "sin traducir"
    assert validar("Put it in the box and you will see", "Pon the item into the box and you will see it") == (
        "inglés residual"
    )
    assert validar("Create", "Create") is None  # nombres propios iguales: aceptados


def test_marcador_con_espacios_se_repara() -> None:
    m = enmascarar("Costs %s coins")
    assert desenmascarar("Cuesta ⟦ 0 ⟧ monedas", m.tokens) == "Cuesta %s monedas"


def test_revisar_glosario() -> None:
    r = revisar_glosario(
        {"Use a Crafting Table": "Usa una mesa de crafteo"}, {"Crafting Table": "Mesa de trabajo"}, ["Crafting Table"]
    )
    assert r.inconsistentes == {"Crafting Table": 1} and "Crafting Table (1)" in str(r)


class PorLotes(Simulador):
    def __init__(self) -> None:
        super().__init__()
        self.trabajos: list[int] = []

    def traducir_varios(self, lotes: Sequence[Lote]) -> list[dict[str, str]]:
        self.trabajos.append(len(lotes))
        return [self.traducir_lote(lote) for lote in lotes]


def test_modo_por_lotes(memoria: Memoria) -> None:
    motor = PorLotes()
    t = Traductor(motor, memoria, Glosario(), limite_entradas=2, usar_lotes=True)
    r = t.traducir([f"Text number {i}" for i in range(5)], "ui")
    assert len(r.traducciones) == 5 and motor.trabajos == [3]  # un solo trabajo con 3 lotes


def _modpack(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(
        juego / "mods" / "m.jar",
        {
            **fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench", "item.m.gear": "Gear"}),
            "assets/m/patchouli_books/guide/en_us/entries/e.json": {"name": "Using the Wrench"},
        },
    )
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text('{ title: "Wrench" description: ["Craft your first tool."] }', encoding="utf-8")
    script = juego / "kubejs" / "client_scripts" / "t.js"
    script.parent.mkdir(parents=True)
    script.write_text("ItemEvents.tooltip(e => { e.add('m:wrench', 'Rotates blocks') })\n", encoding="utf-8")
    fabrica.opciones(juego, ["vanilla", "file/MinecraftLocalizer"], "en_us")
    return juego


def test_proceso_de_punta_a_punta(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    motor = Simulador()
    with Proceso(juego, motor, memoria=memoria) as p:
        analisis = p.analizar()
        assert not (juego / "resourcepacks").exists() and not (juego / "traductor_es").exists()  # analizar no escribe
        assert [m.grupo for m in analisis.modulos] == ["mods", "libros", "misiones", "scripts"]
        informe = p.ejecutar()
    pack = juego / "resourcepacks" / "Traduccion_ES" / "assets" / "m"
    assert json.loads((pack / "lang" / "es_mx.json").read_text("utf-8"))["item.m.wrench"] == "«ES» Wrench"
    # El título de la misión es el nombre del objeto: sale del glosario (mismo nombre) y no va al motor
    assert 'title: "«ES» Wrench"' in (juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt").read_text(
        "utf-8"
    )
    enviados = [e.texto for lote in motor.lotes_recibidos for e in lote.entradas]
    assert enviados.count("Wrench") == 1
    assert "«ES» Rotates blocks" in (juego / "kubejs" / "client_scripts" / "t.js").read_text("utf-8")
    opciones = (juego / "options.txt").read_text("utf-8")
    assert '"file/Traduccion_ES"' in opciones and "lang:es_mx" in opciones
    assert any("MinecraftLocalizer" in a for a in informe.avisos)
    assert informe.costo("gemini-3.8-flash", False) is not None and informe.costo("desconocido", False) is None
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        restaurados = p.restaurar()
    assert len(restaurados) == 2
    assert "Rotates blocks'" in (juego / "kubejs" / "client_scripts" / "t.js").read_text("utf-8")


def test_linea_de_comandos(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    juego = _modpack(tmp_path)
    assert main(["analizar", str(juego)]) == 0
    salida = capsys.readouterr().out
    assert "Minecraft 1.20.1" in salida and "Costo estimado con gemini-3.8-flash" in salida
    assert main(["traducir", str(juego), "--simular", "--no-activar"]) == 0
    assert "«ES» Rotates blocks" in (juego / "kubejs" / "client_scripts" / "t.js").read_text("utf-8")
    assert "lang:en_us" in (juego / "options.txt").read_text("utf-8")
    assert main(["traducir", str(juego)]) == 1  # sin clave: error claro
    assert "Falta la clave" in capsys.readouterr().out
    assert main(["restaurar", str(juego)]) == 0
    assert main(["analizar", str(tmp_path / "no-existe")]) == 1


def test_simular_no_ensucia_la_memoria_real(tmp_path: Path) -> None:
    """Si «ES …» quedara en la memoria, la próxima traducción de verdad lo reutilizaría sin preguntar al motor."""
    from traductor_es import configuracion

    juego = _modpack(tmp_path)
    assert main(["traducir", str(juego), "--simular", "--no-activar"]) == 0
    assert "«ES» Rotates blocks" in (juego / "kubejs" / "client_scripts" / "t.js").read_text("utf-8")
    with Memoria(configuracion.ruta_memoria()) as memoria:
        assert memoria.cantidad() == 0


class PorLotesQueDana(PorLotes):
    """Por lotes devuelve los códigos dañados; en modo normal, bien."""

    def traducir_varios(self, lotes: Sequence[Lote]) -> list[dict[str, str]]:
        self.trabajos.append(len(lotes))
        return [{e.id: "roto" for e in lote.entradas} for lote in lotes]


def test_reintento_va_en_modo_normal(memoria: Memoria) -> None:
    motor = PorLotesQueDana()
    t = Traductor(motor, memoria, Glosario(), usar_lotes=True)
    r = t.traducir(["Costs %s coins"], "ui")
    assert motor.trabajos == [1]  # un solo trabajo por lotes; el reintento fue normal
    assert r.traducciones == {"Costs %s coins": "«ES» Costs %s coins"}


def test_solo_nombres_van_al_glosario() -> None:
    from traductor_es.modulos.mods import es_nombre

    assert es_nombre("item.create.wrench") and es_nombre("block.minecraft.stone") and es_nombre("entity.x.osprey")
    assert not es_nombre("key.mouse.right") and not es_nombre("gui.all") and not es_nombre("item.x.wrench.tooltip")


@pytest.mark.parametrize(("version", "antes", "despues"), [("1.20.1", "es_es", "es_es"), ("1.20.1", "en_us", "es_mx"),
                                                          ("1.10.2", "en_US", "es_MX")])  # fmt: skip
def test_idioma_del_juego(tmp_path: Path, memoria: Memoria, version: str, antes: str, despues: str) -> None:
    juego = fabrica.prism(tmp_path, version)
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"a": "Wrench"}, legacy=version < "1.13"))
    fabrica.opciones(juego, ["vanilla"], antes)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        p.ejecutar()
    assert f"lang:{despues}\n" in (juego / "options.txt").read_text("utf-8")


def test_tablas_y_libros_se_leen_una_vez(tmp_path: Path, memoria: Memoria) -> None:
    juego = _modpack(tmp_path)
    with Proceso(juego, Simulador(), memoria=memoria) as p:
        assert p.instancia.tabla_idiomas() is p.instancia.tabla_idiomas()
        libros = next(m for g, m in p.modulos() if g == "libros")
        lecturas: list[int] = []
        original = libros._leer_grupos  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]

        def contar() -> object:
            lecturas.append(1)
            return original()  # pyright: ignore[reportUnknownVariableType]

        libros._leer_grupos = contar  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        libros.describir()
        libros.recolectar()
        assert lecturas == []  # ya se había leído al detectarlo

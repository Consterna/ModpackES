"""Control de calidad determinista: arreglos seguros, dudas y textos del juego que no deben marcarse."""

from __future__ import annotations

import pytest

from traductor_es.validacion.qa import arreglos, dudas, revisar


def _arreglo(original: str, traduccion: str, dialecto: str = "es_mx") -> tuple[str, list[str]]:
    texto, hallazgos = revisar(original, traduccion, dialecto=dialecto)
    return texto, arreglos(hallazgos)


# ---------------------------------------------------------------- arreglos


@pytest.mark.parametrize(
    ("original", "traduccion", "esperado", "codigo"),
    [
        ("Are you sure?", "Estás seguro?", "¿Estás seguro?", "signo_apertura"),
        ("Watch out!", "§cCuidado!", "§c¡Cuidado!", "signo_apertura"),  # después del código de color
        ("Energy:", "Energía", "Energía:", "puntuacion_final"),
        ("Loading...", "Cargando…", "Cargando...", "puntuacion_final"),  # el juego usa «...»
        ("Waiting...", "Esperando", "Esperando...", "puntuacion_final"),
        ("Iron  Gear", "Engranaje de hierro", "Engranaje de hierro", None),  # nada que arreglar
        ("Place it here", "Colócalo  aquí", "Colócalo aquí", "espacios"),
        ("Place it, then wait", "Colócalo , luego espera", "Colócalo, luego espera", "espacios"),
        ("Craft the table", "Fabrica la la mesa", "Fabrica la mesa", "palabra_doble"),
        ("Opens on Monday", "Abre el Lunes", "Abre el lunes", "mes_dia"),
    ],
)
def test_arreglos(original: str, traduccion: str, esperado: str, codigo: str | None) -> None:
    texto, hechos = _arreglo(original, traduccion)
    assert texto == esperado
    assert hechos == ([codigo] if codigo else [])


def test_comillas_segun_el_dialecto() -> None:
    assert _arreglo('Press "E"', 'Pulsa "E"', "es_es")[0] == "Pulsa «E»"
    assert _arreglo('Press "E"', "Presiona «E»", "es_mx")[0] == 'Presiona "E"'
    # Si el original no tiene comillas, no se toca lo que el modelo destacó
    assert _arreglo("Press E", "Presiona «E»", "es_mx")[0] == "Presiona «E»"


def test_los_arreglos_no_tocan_los_codigos() -> None:
    # «$(l)» y «%s» se protegen: los espacios y signos se arreglan alrededor, no dentro
    texto, _ = _arreglo("Use $(l)this$() on %s?", "Usa  $(l)esto$() en %s?")
    assert texto == "¿Usa $(l)esto$() en %s?"


def test_un_texto_en_ingles_no_se_decora() -> None:
    texto, hallazgos = revisar("Welcome back, %s!", "«ES» Welcome back, %s!")
    assert "¡" not in texto and not arreglos(hallazgos)


def test_varias_frases_sin_signo_de_apertura_quedan_como_duda() -> None:
    texto, hallazgos = revisar("Done. Want more?", "Listo. Quieres más?")
    assert texto == "Listo. Quieres más?" and dudas(hallazgos) == ["signo_apertura"]


# ---------------------------------------------------------------- dudas


@pytest.mark.parametrize(
    ("original", "traduccion", "codigo"),
    [
        ("Costs 64 coins", "Cuesta 32 monedas", "numeros"),
        ("Tier 3 machine", "Máquina de nivel III", "numeros"),
        ("Hold (shift) to see", "Mantén (shift para ver", "pareja"),
        ("Place the block", "Coloque el bloque", "usted"),
        ("Click on the block", "Haz clic on the bloque", "ingles"),
        (
            "Mine the ore first. Then smelt it. Finally craft the tool.",
            "Mina primero el mineral.",
            "omision",
        ),
    ],
)
def test_dudas(original: str, traduccion: str, codigo: str) -> None:
    _, hallazgos = revisar(original, traduccion)
    assert codigo in dudas(hallazgos)


@pytest.mark.parametrize(
    ("original", "traduccion"),
    [
        # Convenciones del español del propio juego: no deben marcarse
        ("Gave %s %s to %s", "%3$s recibió %1$s de %2$s"),
        ("Say that 3 times fast", "Dilo tres veces rápido"),  # cifra escrita con letras
        ("Costs 1,000 coins", "Cuesta 1.000 monedas"),  # otro separador de miles
        ("Used in machines (e.g. the Charger). Very useful.", "Se usa en máquinas (p. ej., el cargador). Muy útil."),
        ("Mine the ore. Smelt it.", "Mina el mineral y fúndelo."),  # unir dos frases es legítimo
        ("Spawns in the End", "Aparece en el End"),
        ("Crafting Table", "Mesa de trabajo"),
        ("Tier I spellbooks. It also allows more.", "Grimorios de nivel I. También permite más."),
    ],
)
def test_textos_correctos_no_se_marcan(original: str, traduccion: str) -> None:
    texto, hallazgos = revisar(original, traduccion)
    assert texto == traduccion and not dudas(hallazgos)


def test_mayusculas_de_titulo_en_nombres_solo_se_informan() -> None:
    texto, hallazgos = revisar("Diamond Sword", "Espada de Diamante", rol="nombre")
    assert texto == "Espada de Diamante"  # no se cambia: puede ser un término propio del pack
    assert any(h.codigo == "mayusculas_titulo" and h.gravedad == "info" for h in hallazgos)
    _, sin_aviso = revisar("Witherproof Glass", "Vidrio a prueba de Wither", rol="nombre")
    assert any(h.codigo == "mayusculas_titulo" for h in sin_aviso)  # «Wither» es nombre propio: solo información

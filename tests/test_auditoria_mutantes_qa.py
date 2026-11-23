"""Bordes del control de calidad (`validacion/qa.py`): cada prueba detecta una mutación que antes sobrevivía.

Corrida de mutación: `logs/fase-03/mutacion_qa.log` (62,4 % antes de estas pruebas).
"""

from __future__ import annotations

import pytest

from traductor_es.validacion.qa import Hallazgo, arreglos, dudas, revisar


def _codigos(original: str, traduccion: str, **kw: str) -> tuple[str, list[str], list[str]]:
    texto, hallazgos = revisar(original, traduccion, **kw)
    return texto, arreglos(hallazgos), dudas(hallazgos)


def _info(original: str, traduccion: str, **kw: str) -> list[str]:
    _, hallazgos = revisar(original, traduccion, **kw)
    return [h.codigo for h in hallazgos if h.gravedad == "info" and not h.arreglado]


def test_una_marca_no_es_un_arreglo() -> None:
    assert Hallazgo("x", "duda").arreglado is False
    _, hallazgos = revisar("Iron 3", "Hierro 4")
    assert [h.arreglado for h in hallazgos if h.codigo == "numeros"] == [False]


def test_caracter_invisible_que_ya_trae_el_original_se_deja() -> None:
    assert revisar("a\u200bb", "c\u200bd")[0] == "c\u200bd"
    assert revisar("ab", "c\u200bd")[0] == "cd"


@pytest.mark.parametrize(
    ("traduccion", "hay_duda"),
    [
        ("Usa the pico", True),  # 3 palabras, 1 inglesa: pocas palabras, basta una
        ("Usa the pico ya", True),  # 4 palabras: todavía basta una
        ("Usa the pico de hierro", False),  # 5 palabras y una sola inglesa: puede ser un nombre
        ("Usa the pico with hierro", True),  # dos inglesas
    ],
)
def test_palabras_inglesas_en_el_borde(traduccion: str, hay_duda: bool) -> None:
    assert ("ingles" in _codigos("Use the pickaxe", traduccion)[2]) is hay_duda


def test_signo_de_apertura_despues_de_un_codigo_inicial() -> None:
    texto, hechos, _ = _codigos("§aReady?", "§aListo?")
    assert texto == "§a¿Listo?" and "signo_apertura" in hechos


def test_signo_de_apertura_en_dos_frases_es_duda() -> None:
    texto, hechos, faltan = _codigos("Done. Ready?", "Hecho. Listo?")
    assert texto == "Hecho. Listo?" and "signo_apertura" in faltan and "signo_apertura" not in hechos


def test_un_texto_que_quedo_a_medias_en_ingles_no_se_decora() -> None:
    # la mitad exacta de las palabras (de 3 letras o más) son del original: se trata como inglés
    texto, hechos, _ = _codigos("Ready steady?", "Ready listo?")
    assert texto == "Ready listo?" and "signo_apertura" not in hechos
    # menos de la mitad: es español y se arregla
    texto, hechos, _ = _codigos("Ready steady?", "Ready listo para ir?")
    assert texto == "¿Ready listo para ir?"


def test_palabras_de_dos_letras_no_cuentan_para_parecer_ingles() -> None:
    texto, hechos, _ = _codigos("Go up now?", "Ve up ya ahora?")  # «up» tiene dos letras: no cuenta
    assert texto == "¿Ve up ya ahora?" and "signo_apertura" in hechos


def test_puntos_suspensivos_y_dos_puntos_finales() -> None:
    assert revisar("Loading...", "Cargando")[0] == "Cargando..."
    assert revisar("Loading...", "Cargando…")[0] == "Cargando..."
    assert revisar("Loading...", "¿Cargando?")[0] == "¿Cargando?"  # ya cierra con otro signo
    assert revisar("Ingredients:", "Ingredientes.")[0] == "Ingredientes:"
    assert revisar("Ingredients:", "Ingredientes")[0] == "Ingredientes:"


@pytest.mark.parametrize(
    ("original", "traduccion", "marca"),
    [
        ("Craft it.", "Fabrícalo", True),
        ("Craft it", "Fabrícalo.", True),
        ("Craft it!", "¡Fabrícalo!", False),
        ("Craft it.", "Fabrícalo…", False),
        ("Craft it", "Fabrícalo", False),
    ],
)
def test_punto_final_que_no_coincide(original: str, traduccion: str, marca: bool) -> None:
    assert ("puntuacion_final" in _info(original, traduccion)) is marca


@pytest.mark.parametrize(
    ("traduccion", "esperado"),
    [
        ("Llega el Lunes", "Llega el lunes"),
        ("Lunes llega", "Lunes llega"),  # al principio queda en mayúscula
        ("Hecho. Lunes llega", "Hecho. Lunes llega"),
        ("¿Lunes?", "¿Lunes?"),
        ("Dato: Lunes", "Dato: Lunes"),
    ],
)
def test_dias_en_minuscula_salvo_al_empezar_una_frase(traduccion: str, esperado: str) -> None:
    assert revisar("It arrives on Monday", traduccion)[0] == esperado


def test_comillas_del_dialecto_solo_con_los_mismos_pares() -> None:
    assert revisar('Say "hi"', 'Di "hola"', dialecto="es_es")[0] == "Di «hola»"
    assert revisar("Say “hi”", "Di «hola»", dialecto="es_mx")[0] == 'Di "hola"'
    assert revisar('Say "hi"', 'Di "hola" y "adiós"', dialecto="es_es")[0] == 'Di "hola" y "adiós"'
    assert revisar("Say hi", 'Di "hola"', dialecto="es_es")[0] == 'Di "hola"'  # el original no tenía comillas


@pytest.mark.parametrize(
    ("original", "traduccion", "hay_duda"),
    [
        ('Say "hi"', 'Di "hola', True),
        ('Say "hi', 'Di "hola', False),  # el original ya venía impar
        ('Say "hi"', 'Di "hola"', False),
    ],
)
def test_comillas_sin_pareja(original: str, traduccion: str, hay_duda: bool) -> None:
    assert ("pareja" in _codigos(original, traduccion)[2]) is hay_duda


def test_omision_por_largo_en_el_borde() -> None:
    cuarenta = "a" * 40
    assert "omision" in _codigos(cuarenta, "b" * 19)[2]  # menos de la mitad de 40
    assert "omision" not in _codigos(cuarenta, "b" * 20)[2]
    assert "omision" not in _codigos("a" * 39, "b" * 5)[2]  # un original corto no cuenta


def test_omision_por_frases_en_el_borde() -> None:
    original = "One here. Two here. Three here. Four here."
    assert "omision" in _codigos(original, "Uno aquí. Dos aquí, tres aquí y cuatro aquí también ahora sí.")[2]
    assert "omision" not in _codigos(original, "Uno aquí. Dos aquí. Tres aquí y cuatro aquí también ahora.")[2]


@pytest.mark.parametrize(
    ("largo", "ambito", "marca"),
    [(26, "ui", False), (27, "ui", True), (40, "mision", False)],
)
def test_largo_de_un_texto_de_interfaz(largo: int, ambito: str, marca: bool) -> None:
    # original de 10 letras: el tope es 1,6 × 10 + 10 = 26
    assert ("largo" in _info("a" * 10, "b" * largo, ambito=ambito)) is marca


@pytest.mark.parametrize(
    ("traduccion", "marca"),
    [
        ("Espada de Diamante", True),
        ("Espada de diamante", False),
        ("Espada de TNT", False),  # siglas: no cuentan
        ("Diamante", False),  # la primera palabra siempre va en mayúscula
        ("Espada de Diamond", False),  # una palabra que viene del original
    ],
)
def test_mayusculas_de_titulo_en_un_nombre(traduccion: str, marca: bool) -> None:
    assert ("mayusculas_titulo" in _info("Diamond Sword", traduccion, rol="nombre")) is marca
    assert "mayusculas_titulo" not in _info("Diamond Sword", traduccion)  # solo en nombres

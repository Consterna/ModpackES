"""Medición más rigurosa: intervalo de confianza, consistencia de términos y traducciones guardadas."""

from __future__ import annotations

from traductor_es.motores.simulador import Simulador
from traductor_es.validacion import medicion


def test_el_intervalo_rodea_al_promedio_y_se_estrecha_con_mas_datos() -> None:
    pocos = [60.0, 70.0, 80.0, 65.0, 75.0]
    muchos = pocos * 20
    ic_pocos, ic_muchos = medicion.intervalo(pocos), medicion.intervalo(muchos)
    assert ic_pocos is not None and ic_muchos is not None
    assert ic_pocos[0] < 70 < ic_pocos[1]
    assert (ic_muchos[1] - ic_muchos[0]) < (ic_pocos[1] - ic_pocos[0])


def test_sin_datos_suficientes_no_hay_intervalo() -> None:
    assert medicion.intervalo([50.0, 60.0]) is None


def test_el_intervalo_es_reproducible() -> None:
    datos = [float(x) for x in range(40, 80)]
    assert medicion.intervalo(datos) == medicion.intervalo(datos)


def test_nombres_traducidos_igual_dan_consistencia_alta() -> None:
    pares = [
        ("Moon Berries Pie", "Pastel de bayas lunares"),
        ("Moon Berries Jam", "Mermelada de bayas lunares"),
        ("Moon Berries Tart", "Tarta de bayas lunares"),
        ("Moon Berries Juice", "Jugo de bayas lunares"),
        ("Iron Sword", "Espada de hierro"),
    ]
    nivel, evaluados = medicion.consistencia(pares)
    assert evaluados >= 1
    assert nivel > 0.95


def test_nombres_traducidos_distinto_bajan_la_consistencia() -> None:
    parejos = [
        ("Moon Berries Pie", "Pastel de bayas lunares"),
        ("Moon Berries Jam", "Mermelada de bayas lunares"),
        ("Moon Berries Tart", "Tarta de bayas lunares"),
        ("Moon Berries Juice", "Jugo de bayas lunares"),
        ("Iron Sword", "Espada de hierro"),
    ]
    revueltos = [
        ("Moon Berries Pie", "Pastel de bayas lunares"),
        ("Moon Berries Jam", "Mermelada de moras selenitas"),
        ("Moon Berries Tart", "Tarta de arándanos de luna"),
        ("Moon Berries Juice", "Jugo de bayas de luna"),
        ("Iron Sword", "Espada de hierro"),
    ]
    assert medicion.consistencia(revueltos)[0] < medicion.consistencia(parejos)[0]


def test_sin_terminos_repetidos_no_se_evalua_nada() -> None:
    assert medicion.consistencia([("Iron Sword", "Espada de hierro"), ("Gold Axe", "Hacha de oro")]) == (0.0, 0)


def test_la_medicion_guarda_las_traducciones_y_el_intervalo() -> None:
    casos = [medicion.Caso("ui", f"Moon Berries Thing {i}", f"Cosa de bayas lunares {i}") for i in range(8)]
    banco = medicion.Banco("es_mx", {}, casos)
    resultado = medicion.medir(Simulador(), banco)[0]
    assert len(resultado.traducciones) == resultado.traducidos == 8
    assert {"ambito", "original", "referencia", "traduccion"} <= set(resultado.traducciones[0])
    assert resultado.chrf_intervalo is not None
    assert "IC 95 %" in resultado.tabla()

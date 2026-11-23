"""Bordes de la detección de términos repetidos y nombres propios (`nucleo/terminos.py`): cada prueba detecta una
mutación que antes sobrevivía (`logs/fase-03/mutacion_terminos.log`, 68,4 %)."""

from __future__ import annotations

from traductor_es.nucleo.terminos import nombres_propios, repetidos


def _cuatro_veces(*nombres: str) -> list[str]:
    return [f"{n} {extra}" for n in nombres for extra in ("Sword", "Pickaxe", "Axe", "Shovel")]


def test_un_nombre_tiene_de_una_a_cinco_palabras() -> None:
    cinco = [f"Big Old Moon Stone {x}" for x in ("Sword", "Pickaxe", "Axe", "Shovel")]
    seis = [f"Very Big Old Moon Stone {x}" for x in ("Sword", "Pickaxe", "Axe", "Shovel")]
    assert repetidos(cinco)  # cinco palabras: es un nombre (sale el término más largo, «Old Moon Stone»)
    assert repetidos(seis) == []  # seis palabras: no es un nombre


def test_conectores_solo_en_medio() -> None:
    assert "Pie of the Moon" not in repetidos(["Pie of the Moon"] * 4)  # un solo nombre distinto
    medio = [f"Pie of the Moon {x}" for x in ("Sword", "Pickaxe", "Axe", "Shovel")]
    assert "Pie of the Moon" not in repetidos(medio)  # cuatro palabras: más que un término
    assert not any(t.startswith(("of ", "the ")) or t.endswith((" of", " the")) for t in repetidos(medio))
    assert repetidos([f"of Moon {x}" for x in ("Sword", "Pickaxe", "Axe", "Shovel")]) == []  # «of» al principio
    assert repetidos([f"Moon {x} of" for x in ("Sword", "Pickaxe", "Axe", "Shovel")]) == []  # y al final


def test_minimo_de_cuatro_nombres_distintos() -> None:
    assert repetidos(_cuatro_veces("Moonstone")) == ["Moonstone"]
    tres = [f"Moonstone {x}" for x in ("Sword", "Pickaxe", "Axe")]
    assert repetidos(tres) == []


def test_terminos_de_hasta_tres_palabras_y_cuatro_letras() -> None:
    assert repetidos(_cuatro_veces("Dark Moon Stone")) == ["Dark Moon Stone"]
    assert repetidos(_cuatro_veces("Big Dark Moon Stone")) == ["Dark Moon Stone", "Big Dark Moon"]
    assert repetidos(_cuatro_veces("Ore")) == []  # tres letras: muy corto para ser un término


def _nombres(cuantos: int, base: str) -> list[str]:
    """Palabras en Title Case distintas (sin cifras: «Term01» no es una palabra de un nombre)."""
    return [base + chr(97 + i // 26) + chr(97 + i % 26) for i in range(cuantos)]


def test_tope_de_terminos() -> None:
    nombres = _nombres(40, "Zor")
    textos = [n + " " + x for n in nombres for x in ("Sword", "Pickaxe", "Axe", "Shovel")]
    assert len(repetidos(textos)) == 30
    assert len(repetidos(textos, maximo=5)) == 5


def test_nombres_propios_en_el_borde() -> None:
    frases = ["Defeat the Arachnarch now", "The Arachnarch lunges at you"]
    assert nombres_propios(frases) == ["Arachnarch"]
    assert nombres_propios(frases[:1]) == []  # aparece en un solo texto
    assert nombres_propios(["Kill Arachnarch", "Kill Arachnarch"]) == []  # dos palabras: no es una frase
    assert nombres_propios(["Defeat the Bob now", "Kill the Bob here"]) == []  # tres letras
    assert nombres_propios(["Defeat the Bobo now", "Kill the Bobo here"]) == ["Bobo"]


def test_una_palabra_suelta_al_empezar_una_frase_no_cuenta() -> None:
    assert nombres_propios(["Note: Arachnarch is near", "Done. Arachnarch waits now"]) == []
    assert nombres_propios(["Note: Bronze Dungeons are near", "Done. Bronze Dungeons wait"]) == ["Bronze Dungeons"]


def test_tope_de_nombres_propios() -> None:
    textos = [f"Defeat the {n} now" for n in _nombres(70, "Bos")] + [f"Kill the {n} again" for n in _nombres(70, "Bos")]
    assert len(nombres_propios(textos)) == 60

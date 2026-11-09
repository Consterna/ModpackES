"""Casos límite del núcleo: memoria, glosario y traductor con entradas raras, motores que se portan mal y UTF-8."""

import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.motores.base import ErrorFatal, Lote
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import desenmascarar, enmascarar, es_traducible, separar_bordes
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor

ESPECIALES = "Ñandú sí, ¿cómo estás? ¡Ágüita! 日本語 😀 §a%s §r%d {0} ${x}"


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


# ------------------------------------------------------------------ memoria
def test_memoria_guarda_y_lee_utf8_en_disco(tmp_path: Path) -> None:
    ruta = tmp_path / "datos" / "memoria.db"
    with Memoria(ruta) as m:
        m.guardar({ESPECIALES: "Ñandú ¡sí! §a%s"}, "es_mx", "ui", "prueba")
        assert m.obtener(ESPECIALES, "es_mx", "ui") == "Ñandú ¡sí! §a%s"
    with Memoria(ruta) as m:  # se vuelve a abrir: persiste y sigue siendo UTF-8
        assert m.obtener(ESPECIALES, "es_mx", "ui") == "Ñandú ¡sí! §a%s"
        assert m.cantidad() == 1


def test_memoria_buscar_no_trata_comodines_como_comodines(memoria: Memoria) -> None:
    memoria.guardar({"100% real": "100 % real", "abc": "abc", "a_c": "a_c", "a!c": "a!c"}, "es_mx", "ui", "p")
    assert [c.origen for c in memoria.buscar("%", "es_mx")] == ["100% real"]
    assert [c.origen for c in memoria.buscar("a_c", "es_mx")] == ["a_c"]
    assert [c.origen for c in memoria.buscar("a!c", "es_mx")] == ["a!c"]


def test_memoria_con_inyeccion_sql_en_el_texto(memoria: Memoria) -> None:
    raro = "'; DROP TABLE traducciones; --"
    memoria.guardar({raro: "x"}, "es_mx", "ui", "p")
    assert memoria.obtener(raro, "es_mx", "ui") == "x" and memoria.cantidad() == 1
    assert memoria.buscar(raro, "es_mx")[0].origen == raro


def test_memoria_desde_varios_hilos(memoria: Memoria) -> None:
    errores: list[BaseException] = []

    def trabajar(n: int) -> None:
        try:
            for i in range(40):
                memoria.guardar({f"texto {n}-{i}": f"texto {n}-{i} ñ"}, "es_mx", "ui", "p")
                assert memoria.obtener(f"texto {n}-{i}", "es_mx", "ui") == f"texto {n}-{i} ñ"
        except BaseException as e:
            errores.append(e)

    hilos = [threading.Thread(target=trabajar, args=(n,)) for n in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert not errores and memoria.cantidad() == 8 * 40


def test_correccion_manda_y_se_puede_quitar(memoria: Memoria) -> None:
    memoria.guardar({"Hello": "Hola"}, "es_mx", "ui", "p")
    memoria.corregir("Hello", "es_mx", "¡Buenas!")
    assert memoria.correccion("Hello", "es_mx") == "¡Buenas!" and memoria.correcciones("es_mx") == {"Hello": "¡Buenas!"}
    memoria.quitar_correccion("Hello", "es_mx")
    assert memoria.correccion("Hello", "es_mx") is None


def test_memoria_corrupta_da_un_error_claro(tmp_path: Path) -> None:
    ruta = tmp_path / "memoria.db"
    ruta.write_bytes(b"esto no es una base de datos sqlite" * 50)
    with pytest.raises(sqlite3.DatabaseError):
        Memoria(ruta)


# ------------------------------------------------------------------ glosario
@pytest.mark.parametrize(
    "termino", ["C++", "(Test)", "a.b", "Tom's [Storage]", "50% off", "back\\slash", "$HOME", "x|y"]
)
def test_glosario_con_caracteres_de_regex(termino: str) -> None:
    g = Glosario()
    g.agregar_pares({"k": termino}, {"k": "traducido"})
    g.fijar({termino + " extra": "fijo"})
    assert isinstance(g.relevantes([f"use {termino} here and {termino} extra"]), dict)


def test_glosario_respeta_palabras_completas() -> None:
    g = Glosario()
    g.agregar_pares({"a": "Wheat", "b": "Iron Ingot"}, {"a": "Trigo", "b": "Lingote de hierro"})
    assert g.relevantes(["Wheat bread", "Iron Ingot"]) == {"Wheat": "Trigo", "Iron Ingot": "Lingote de hierro"}
    assert g.relevantes(["Wheatgrass", "Ironwork"]) == {}  # no son palabras completas
    assert g.relevantes([]) == {}


# ------------------------------------------------------------------ máscara y UTF-8
def test_mascara_ida_y_vuelta_con_especiales() -> None:
    m = enmascarar(ESPECIALES)
    assert desenmascarar(m.texto, m.tokens) == ESPECIALES
    assert "Ñ" in m.texto and "😀" in m.texto and "日本語" in m.texto  # lo que no es código se queda legible


@pytest.mark.parametrize("texto", ["", " ", "\n", "§a", "%s", "{0}", "<br>", "https://x.y/z", "12345", "---"])
def test_textos_sin_nada_que_traducir(texto: str) -> None:
    assert not es_traducible(texto)
    assert separar_bordes(texto)[1] in ("", texto.strip())


# ------------------------------------------------------------------ traductor con motores que se portan mal
class _Motor:
    nombre = "malo"

    def __init__(self, respuesta: object) -> None:
        self.respuesta = respuesta
        self.llamadas = 0

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.llamadas += 1
        r = self.respuesta
        if callable(r):
            return r(lote)  # type: ignore[no-any-return]
        return r  # type: ignore[return-value]


def test_traductor_con_lista_vacia_y_duplicados(memoria: Memoria) -> None:
    t = Traductor(Simulador(), memoria, Glosario())
    assert t.traducir([], "ui").traducciones == {}
    r = t.traducir(["Hello world", "Hello world", "  Hello world  "], "ui")
    assert r.traducciones["Hello world"] == "«ES» Hello world"
    assert r.traducciones["  Hello world  "] == "  «ES» Hello world  "  # los bordes se conservan


def test_traductor_con_codigos_y_especiales(memoria: Memoria) -> None:
    t = Traductor(Simulador(), memoria, Glosario())
    textos = ["§aYou have %d items in %s", "Press {0} to open the menu ¡ya!", "Ñandú ${nombre} says §chello there"]
    r = t.traducir(textos, "ui")
    for original in textos:
        assert enmascarar(original).tokens == enmascarar(r.traducciones[original]).tokens  # mismos códigos
        assert "«ES»" in r.traducciones[original]


def test_motor_que_pierde_los_codigos_se_descarta(memoria: Memoria) -> None:
    def sin_codigos(lote: Lote) -> dict[str, str]:
        return {e.id: "Texto sin marcadores" for e in lote.entradas}

    motor = _Motor(sin_codigos)
    r = Traductor(motor, memoria, Glosario()).traducir(["§aHello %s there"], "ui")
    assert "§aHello %s there" not in r.traducciones or r.traducciones["§aHello %s there"] == "§aHello %s there"
    assert motor.llamadas >= 1  # reintentó y no aceptó la traducción rota


@pytest.mark.parametrize("respuesta", [{}, {"id-que-no-existe": "x"}, {"0": ""}])
def test_motor_que_omite_o_inventa_ids(memoria: Memoria, respuesta: dict[str, str]) -> None:
    r = Traductor(_Motor(respuesta), memoria, Glosario()).traducir(["Hello brave world"], "ui")
    assert r.traducciones.get("Hello brave world", "Hello brave world") == "Hello brave world"  # queda en inglés


def test_error_fatal_del_motor_se_propaga(memoria: Memoria) -> None:
    def falla(_lote: Lote) -> dict[str, str]:
        raise ErrorFatal("clave inválida")

    with pytest.raises(ErrorFatal):
        Traductor(_Motor(falla), memoria, Glosario()).traducir(["Hello brave world"], "ui")


def test_texto_muy_largo_se_traduce_sin_perder_nada(memoria: Memoria) -> None:
    largo = " ".join(f"Palabra{i}" for i in range(4000))
    r = Traductor(Simulador(), memoria, Glosario()).traducir([largo], "libro")
    assert r.traducciones[largo] == "«ES» " + largo


def test_memoria_danada_da_un_error_claro_en_el_proceso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from traductor_es.proceso import Proceso

    from . import fabrica

    datos = tmp_path / "datos"
    datos.mkdir()
    (datos / "memoria.db").write_bytes(b"basura" * 100)
    monkeypatch.setenv("TRADUCTOR_ES_DATOS", str(datos))
    juego = fabrica.prism(tmp_path, "1.20.1")
    with pytest.raises(ErrorFatal, match="memoria de traducciones está dañada"):
        Proceso(juego, Simulador())

"""Pruebas de los hallazgos de la revisión de la fase 1."""

from pathlib import Path

import pytest

from traductor_es.formatos import lang_legacy
from traductor_es.formatos.snbt import des_escapar, escapar
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import desenmascarar, enmascarar
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.validacion.java import ValidadorJava, buscar_jdk, version_java


def test_barra_mas_salto_real_queda_protegido() -> None:
    texto = des_escapar("Linea\\\nsigue", '"')
    m = enmascarar(texto)
    assert "\n" not in m.texto
    restaurado = desenmascarar(m.texto, m.tokens)
    assert restaurado is not None
    assert escapar(restaurado, '"') == "Linea\\\nsigue"


def test_pistas_llegan_aunque_el_texto_tenga_espacios() -> None:
    motor = Simulador()
    with Memoria(":memory:") as mem:
        Traductor(motor, mem, Glosario()).traducir(["  Iron Plate "], "ui", {"  Iron Plate ": "item.x.plate"})
    assert motor.lotes_recibidos[0].entradas[0].pista == "item.x.plate"


def test_reintento_no_reinicia_la_barra() -> None:
    avances: list[tuple[int, int]] = []

    def avanzar(hechos: int, total: int) -> None:
        avances.append((hechos, total))

    with Memoria(":memory:") as mem:
        t = Traductor(Simulador(danar=1.0), mem, Glosario(), progreso=avanzar)
        t.traducir(["Cost %s", "Pay %d"], "ui")
    assert avances[-1] == (2, 2)
    assert all(total == 2 for _, total in avances)


def test_lang_antiguo_solo_numeral_en_columna_cero_es_comentario() -> None:
    assert lang_legacy.leer(b"#c=1\n//x=y\n #a=b\n") == {"//x": "y", " #a": "b"}


def test_version_java(tmp_path: Path) -> None:
    for texto, esperado in [('JAVA_VERSION="21.0.7"', 21), ('JAVA_VERSION="1.8.0_402"', 8), ("nada", 0)]:
        (tmp_path / "release").write_text(texto, encoding="utf-8")
        assert version_java(tmp_path) == esperado
    assert version_java(tmp_path / "no-existe") == 0


def _jdk_falso(carpeta: Path, version: str) -> Path:
    (carpeta / "bin").mkdir(parents=True)
    for nombre in ("java.exe", "javac.exe"):
        (carpeta / "bin" / nombre).write_bytes(b"")
    (carpeta / "release").write_text(f'JAVA_VERSION="{version}"', encoding="utf-8")
    return carpeta


def test_elige_el_jdk_mas_nuevo_y_descarta_viejos(tmp_path: Path) -> None:
    viejo = _jdk_falso(tmp_path / "a-jdk8", "1.8.0_1")
    nuevo = _jdk_falso(tmp_path / "z-jdk99", "99.0.1")
    assert buscar_jdk([viejo, nuevo]) == nuevo
    elegido = buscar_jdk([viejo])
    assert elegido != viejo


@pytest.mark.java
def test_rutas_con_caracteres_no_ansi(validador_java: ValidadorJava, cp_gson: list[Path], tmp_path: Path) -> None:
    carpeta = tmp_path / "prueba_日本語_ñ"
    carpeta.mkdir()
    archivos: list[Path] = []
    for i in range(400):  # muchas rutas largas: antes podían pasar el límite de la línea de comandos
        ruta = carpeta / (f"{'x' * 120}_{i}.json")
        ruta.write_text('{"a": "b"}', encoding="utf-8")
        archivos.append(ruta)
    resultados = validador_java.validar("json", archivos, cp_gson)
    assert len(resultados) == 400
    assert all(r.ok for r in resultados), resultados[0].detalle
    assert resultados[0].ruta == archivos[0]

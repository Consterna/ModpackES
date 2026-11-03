from pathlib import Path

import pytest

from traductor_es.formatos.snbt import escanear, reemplazar
from traductor_es.validacion.java import ValidadorJava

pytestmark = pytest.mark.java


def escribir(carpeta: Path, nombre: str, contenido: str) -> Path:
    ruta = carpeta / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_json_estricto(validador_java: ValidadorJava, cp_gson: list[Path], tmp_path: Path) -> None:
    bueno = escribir(tmp_path, "bueno.json", '{"a": "Hola \\"mundo\\"", "b": "ñ"}')
    comentario = escribir(tmp_path, "comentario.json", '{\n// x\n"a": "b"}')
    coma = escribir(tmp_path, "coma.json", '{"a": "b",}')
    extra = escribir(tmp_path, "extra.json", '{"a": "b"} {}')
    r = {x.ruta.name: x for x in validador_java.validar("json", [bueno, comentario, coma, extra], cp_gson)}
    assert r["bueno.json"].ok and '"Hola \\"mundo\\""' in r["bueno.json"].detalle
    assert not r["comentario.json"].ok
    assert not r["coma.json"].ok
    assert not r["extra.json"].ok


SNBT = """{
\ttitle: "Getting Started"
\tquests: [{
\t\tdescription: ["Line \\"one\\"", "", "{image:a:b.png width:10}"]
\t\tx: 0.5d
\t\tid: "38597CE6BB709431"
\t}]
}
"""


def test_snbt_con_el_parser_de_ftb(validador_java: ValidadorJava, cp_ftb_1201: list[Path], tmp_path: Path) -> None:
    original = escribir(tmp_path, "original.snbt", SNBT)
    cadenas = escanear(SNBT)
    nuevos = {c.inicio: f'«ES» "{c.texto}" \\ ñ' for c in cadenas if c.campo in ("title", "description") and c.texto}
    traducido = escribir(tmp_path, "traducido.snbt", reemplazar(SNBT, cadenas, nuevos))
    roto = escribir(tmp_path, "roto.snbt", SNBT.replace('"Getting Started"', '"Getting Started'))
    r = {x.ruta.name: x for x in validador_java.validar("snbt", [original, traducido, roto], cp_ftb_1201)}
    assert r["original.snbt"].ok, r["original.snbt"].detalle
    assert r["traducido.snbt"].ok, r["traducido.snbt"].detalle
    assert not r["roto.snbt"].ok
    # Misma estructura: solo cambian las líneas con texto traducido
    a, b = r["original.snbt"].detalle.splitlines(), r["traducido.snbt"].detalle.splitlines()
    assert len(a) == len(b)
    assert '«ES» \\"Getting Started\\" \\\\ ñ' in r["traducido.snbt"].detalle

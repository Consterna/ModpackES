"""Datos de texto en cualquier sitio y versión: se descubren por su estructura, no por la carpeta de un modpack."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.formatos import componente
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.datos import Datos, buscar_archivos, clasificar
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.salida.copias import Respaldo

from . import fabrica


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


@pytest.mark.parametrize(
    ("cuerpo", "esperado"),
    [
        ('{"text":"Hi","color":"red"}', ["Hi"]),
        ('["",{"text":"Hi "},{"text":"there"}]', ["Hi ", "there"]),
        ('"Hi"', ["Hi"]),
        ('{text:"Hi",color:"red"}', ["Hi"]),  # SNBT, desde 1.21.5
        ('["",{text:"Aa"},{text:"Bb",extra:["Cc"]}]', ["Aa", "Bb", "Cc"]),
        ('{translate:"chat.type.text",with:["Steve"],color:"red"}', []),
        ('{"score":{"name":"@p","objective":"x"}}', []),
        ("esto no es un componente", None),
    ],
)
def test_componente_json_y_snbt(cuerpo: str, esperado: list[str] | None) -> None:
    assert componente.unidades(cuerpo) == esperado


def test_componente_snbt_conserva_el_formato() -> None:
    cuerpo = '{text:"Hi", color:"red", hover_event:{action:"show_text", value:"Hola"}}'
    nuevo = componente.reconstruir(cuerpo, {"Hi": "Hola, amigo", "Hola": "no debe usarse"})
    assert nuevo == '{text:"Hola, amigo", color:"red", hover_event:{action:"show_text", value:"Hola"}}'


@pytest.mark.parametrize(
    ("ruta", "formato"),
    [
        ("kubejs/data/a/functions/x.mcfunction", "función"),
        ("global_packs/required_data/p/data/a/function/sub/x.mcfunction", "función"),  # 1.21: «function»
        ("datapacks/p/data/a/advancement/x.json", "logro"),
        ("saves/w/datapacks/p/data/a/advancements/b/x.json", "logro"),
        ("kubejs/assets/a/tips/t.json", "tip"),
        ("resourcepacks/p/assets/a/tips/t.json", "tip"),
        ("kubejs/data/tipsmod/tips/t.json", "tip"),
        ("kubejs/data/a/recipes/x.json", None),
        ("kubejs/data/a/functions/x.txt", None),
        ("config/functions/x.mcfunction", None),  # sin «data»: no es un datapack
        ("assets/a/lang/en_us.json", None),
    ],
)
def test_clasificar_por_estructura(ruta: str, formato: str | None) -> None:
    resultado = clasificar(Path(ruta))
    assert (resultado.nombre if resultado else None) == formato


def _escribir(base: Path, ruta: str, texto: str) -> Path:
    p = base / ruta
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8", newline="")
    return p


def test_descubre_en_cualquier_carpeta_e_ignora_lo_que_no_toca(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fn = 'tellraw @a {"text":"Hi"}\n'
    buenos = [
        "kubejs/data/a/functions/x.mcfunction",
        "global_packs/required_data/p/data/a/functions/x.mcfunction",
        "datapacks/p/data/a/functions/x.mcfunction",
        "saves/Mundo/datapacks/p/data/a/functions/x.mcfunction",
        "config/openloader/data/p/data/a/functions/x.mcfunction",
    ]
    malos = [
        "mods/m/data/a/functions/x.mcfunction",  # los jars no se tocan
        "saves/Mundo/region/data/a/functions/x.mcfunction",  # de un mundo solo importan sus datapacks
        "resourcepacks/Traduccion_ES/data/a/functions/x.mcfunction",  # lo que escribe la app
        "traductor_es/respaldo/kubejs/data/a/functions/x.mcfunction",  # las copias de seguridad
        "logs/data/a/functions/x.mcfunction",
    ]
    for r in (*buenos, *malos):
        _escribir(juego, r, fn)
    encontrados = {p.relative_to(juego).as_posix() for p, _ in buscar_archivos(juego)}
    assert encontrados == set(buenos)


def test_traduce_logros_snbt_funciones_y_tips(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.21.5")
    fn = _escribir(
        juego, "datapacks/p/data/a/function/x.mcfunction", 'tellraw @a {text:"Hello",color:"gold"}\nsay Bye\n'
    )
    logro = _escribir(
        juego,
        "kubejs/data/a/advancement/x.json",
        json.dumps({"display": {"title": "Big Win", "description": {"translate": "k.d"}}, "criteria": {}}),
    )
    tip1 = _escribir(juego, "kubejs/assets/a/tips/t1.json", json.dumps({"tip": {"text": "Eat your greens."}}))
    tip2 = _escribir(
        juego, "kubejs/data/tipsmod/tips/t2.json", json.dumps({"tips": [{"text": "Sleep in beds.", "category": "x"}]})
    )
    negativo = _escribir(juego, "kubejs/data/a/recipes/r.json", json.dumps({"result": {"item": "Big Win"}}))
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        modulo = Datos(ctx)
        assert modulo.describir() == "4 archivos de datos"
        resumen = traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        assert resumen.pendientes == 0 and len(resumen.archivos) == 4
        assert fn.read_text("utf-8") == 'tellraw @a {text:"«ES» Hello",color:"gold"}\nsay «ES» Bye\n'
        assert json.loads(logro.read_text("utf-8"))["display"] == {
            "title": "«ES» Big Win",
            "description": {"translate": "k.d"},
        }
        assert json.loads(tip1.read_text("utf-8")) == {"tip": {"text": "«ES» Eat your greens."}}
        assert json.loads(tip2.read_text("utf-8"))["tips"] == [{"text": "«ES» Sleep in beds.", "category": "x"}]
        assert "«ES»" not in negativo.read_text("utf-8")
        # Repetir no cambia nada, y restaurar devuelve los originales
        antes = {p: p.read_bytes() for p in (fn, logro, tip1, tip2)}
        traducir_modulo(Datos(ctx), Traductor(Simulador(), memoria, Glosario()))
        assert {p: p.read_bytes() for p in antes} == antes
        assert len(Datos(ctx).restaurar()) == 4
    assert fn.read_text("utf-8") == 'tellraw @a {text:"Hello",color:"gold"}\nsay Bye\n'
    assert json.loads(tip1.read_text("utf-8")) == {"tip": {"text": "Eat your greens."}}


def test_archivo_ilegible_se_deja_igual(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    roto = _escribir(juego, "kubejs/data/a/advancements/roto.json", '{"display": {"title": "Hi",}')
    avisos: list[str] = []
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), registro=avisos.append)
        traducir_modulo(Datos(ctx), Traductor(Simulador(), memoria, Glosario()))
    assert roto.read_text("utf-8") == '{"display": {"title": "Hi",}' and any("roto.json" in a for a in avisos)


def test_datapack_comprimido_se_traduce_y_se_restaura(tmp_path: Path, memoria: Memoria) -> None:
    import io
    import zipfile

    juego = fabrica.prism(tmp_path, "1.20.1")
    ruta = juego / "global_packs" / "required_data" / "mi pack v1.zip"
    ruta.parent.mkdir(parents=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.mcmeta", '{"pack": {"pack_format": 15, "description": "Hello pack"}}')
        z.writestr("data/a/functions/x.mcfunction", 'tellraw @a {"text":"Hello there"}\n')
        z.writestr("data/a/recipes/r.json", '{"result": "Hello there"}')
        z.writestr("data/a/advancements/g.json", json.dumps({"display": {"title": "Big Win"}}))
    original = ruta.read_bytes()
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego))
        modulo = Datos(ctx)
        assert modulo.describir() == "2 archivos de datos"
        resumen = traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        assert resumen.traducidos == 2 and resumen.archivos == [ruta]
        with zipfile.ZipFile(io.BytesIO(ruta.read_bytes())) as z:
            assert z.testzip() is None
            assert z.namelist() == [
                "pack.mcmeta",
                "data/a/functions/x.mcfunction",
                "data/a/recipes/r.json",
                "data/a/advancements/g.json",
            ]
            assert "«ES» Hello there" in z.read("data/a/functions/x.mcfunction").decode()
            assert json.loads(z.read("data/a/advancements/g.json"))["display"]["title"] == "«ES» Big Win"
            assert "«ES»" not in z.read("data/a/recipes/r.json").decode() + z.read("pack.mcmeta").decode()
        despues = ruta.read_bytes()
        traducir_modulo(Datos(ctx), Traductor(Simulador(), memoria, Glosario()))
        assert ruta.read_bytes() == despues  # repetir no cambia nada
        assert Datos(ctx).restaurar() == [ruta]
    assert ruta.read_bytes() == original

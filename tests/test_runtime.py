"""Texto del código de los mods: la tabla para el mod de apoyo y su instalación en mods/."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.__main__ import main
from traductor_es.fuentes import vanilla
from traductor_es.fuentes.instancia import Instancia
from traductor_es.modulos.base import Contexto, traducir_modulo
from traductor_es.modulos.runtime import RUTA_TABLA, TextoDeJava
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.dialectos import VARIANTES
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.mascara import enmascarar
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import Traductor
from traductor_es.proceso import Proceso
from traductor_es.salida import mod_apoyo
from traductor_es.salida.copias import Respaldo
from traductor_es.salida.resource_pack import PackSalida

from . import fabrica
from .test_cobertura import _clase  # pyright: ignore[reportPrivateUsage]

FRASES = {
    "A": "You can't use chat, you've been muted by an admin!",
    "B": "Click §ahere§r to open the menu %s now",
    "C": "§cThe market isn't open today, come back later!",
}


@pytest.fixture(autouse=True)
def _sin_lanzadores(monkeypatch: pytest.MonkeyPatch) -> None:
    def ninguno() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", ninguno)


@pytest.fixture
def memoria() -> Iterator[Memoria]:
    with Memoria(":memory:") as m:
        yield m


def _instancia_con_mod(tmp_path: Path, version: str = "1.20.1", loader: str | None = "forge") -> Path:
    juego = fabrica.prism(tmp_path, version, loader)
    fabrica.jar(
        juego / "mods" / "m.jar",
        {
            "com/m/Chat.class": _clase("literal", *FRASES.values()),
            "com/m/Otra.class": _clase("nada", "Another English sentence here"),  # no construye texto
        },
    )
    return juego


def test_tabla_con_las_frases_del_codigo(tmp_path: Path, memoria: Memoria) -> None:
    juego = _instancia_con_mod(tmp_path)
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        modulo = TextoDeJava(ctx)
        resumen = traducir_modulo(modulo, Traductor(Simulador(), memoria, Glosario()))
        pack = ctx.pack_listo().raiz
    assert resumen.traducidos == 3 and len(resumen.archivos) == len(VARIANTES)
    for variante in VARIANTES:
        crudo = (pack / RUTA_TABLA.format(variante=variante)).read_bytes()
        tabla = json.loads(crudo.decode("utf-8"))
        assert set(tabla) == set(FRASES.values())  # la clave es el inglés exacto
        for ingles, espanol in tabla.items():
            assert espanol.startswith("«ES» ")
            assert sorted(enmascarar(espanol).tokens) == sorted(enmascarar(ingles).tokens)  # §a, §r y %s intactos
        assert "Another English sentence here" not in json.dumps(tabla)


def test_sin_frases_no_crea_nada(tmp_path: Path, memoria: Memoria) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.a": "Iron Plate"}))
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst))
        resumen = traducir_modulo(TextoDeJava(ctx), Traductor(Simulador(), memoria, Glosario()))
    assert resumen.archivos == [] and not (juego / "resourcepacks" / "Traduccion_ES" / "assets").exists()


def test_proceso_solo_incluye_el_modulo_si_se_pide(tmp_path: Path, memoria: Memoria) -> None:
    juego = _instancia_con_mod(tmp_path)
    with Proceso(juego, Simulador(), memoria=memoria, grupos=["mods"]) as p:
        assert not any(isinstance(m, TextoDeJava) for _, m in p.modulos())
        sin = p.analizar()
    with Proceso(juego, Simulador(), memoria=memoria, grupos=["mods"], texto_java=True) as p:
        assert any(isinstance(m, TextoDeJava) for _, m in p.modulos())
        con = p.analizar()
        p.ejecutar(activar=False, poner_idioma=False)
    assert con.a_traducir == sin.a_traducir + 3
    assert (juego / "resourcepacks" / "Traduccion_ES" / RUTA_TABLA.format(variante="es_mx")).is_file()


# ------------------------------------------------------------------ mod de apoyo
def _jars(tmp_path: Path, *nombres: str) -> Path:
    carpeta = tmp_path / "empaquetados"
    carpeta.mkdir()
    for n in nombres:
        (carpeta / n).write_bytes(b"PK-" + n.encode())
    return carpeta


def test_mod_de_apoyo_solo_para_lo_soportado(tmp_path: Path) -> None:
    casos = [
        ("1.19.2", "forge", "forge-1.19.2"),
        ("1.20.1", "forge", "forge-1.20.1"),
        ("1.21.1", "neoforge", "neoforge-1.21.1"),
        ("1.19.4", "fabric", "fabric-1.19.4"),
        ("1.20.1", "fabric", "fabric-1.20.1"),
        ("1.21.1", "fabric", "fabric-1.21.1"),
        ("1.21.4", "fabric", "fabric-1.21.4"),
        ("1.20", "fabric", "fabric-1.20.1"),  # un jar sirve para varias versiones vecinas
        ("1.20.2", "fabric", "fabric-1.20.1"),
        ("1.21", "fabric", "fabric-1.21.1"),
        ("1.21.2", "fabric", "fabric-1.21.4"),
        ("1.21.3", "fabric", "fabric-1.21.4"),
        ("1.21.5", "fabric", "fabric-1.21.5"),
        ("1.21.8", "fabric", "fabric-1.21.5"),
        ("1.21.10", "fabric", "fabric-1.21.5"),
        ("1.21.11", "fabric", "fabric-1.21.11"),
        ("26.1", "fabric", "fabric-26.1"),
        ("26.1.2", "fabric", "fabric-26.1"),
        ("26.2", "fabric", "fabric-26.1"),
        ("26.3", "fabric", "fabric-26.1"),
        ("26.4", "fabric", None),  # todavía solo tiene snapshots
        ("1.20.3", "fabric", "fabric-1.20.4"),
        ("1.20.4", "fabric", "fabric-1.20.4"),
        ("1.20.5", "fabric", "fabric-1.20.6"),
        ("1.20.6", "fabric", "fabric-1.20.6"),
        ("1.19.3", "fabric", None),  # sin jar probado para esa versión
        ("1.20.1", "quilt", "fabric-1.20.1"),  # Quilt carga los mods de Fabric
        ("1.21.1", "quilt", "fabric-1.21.1"),
        ("1.19.4", "quilt", "fabric-1.19.4"),
        ("1.20.3", "quilt", None),  # no hay Quilted Fabric API para esa versión
        ("1.21.4", "quilt", None),
        ("1.21.12", "fabric", None),
        ("1.19.2", "fabric", None),  # Fabric API no tiene evento de chat en esa versión
        ("1.18.2", "fabric", None),
        ("1.18.2", "forge", "forge-1.18.2"),
        ("1.21.4", "neoforge", "neoforge-1.21.4"),
        ("1.21", "neoforge", "neoforge-1.21.1"),
        ("1.21.3", "neoforge", "neoforge-1.21.1"),
        ("1.21.5", "neoforge", "neoforge-1.21.5"),
        ("1.21.8", "neoforge", "neoforge-1.21.5"),
        ("1.21.10", "neoforge", "neoforge-1.21.5"),
        ("1.21.11", "neoforge", "neoforge-1.21.11"),
        ("1.20.4", "neoforge", None),
        ("26.1", "neoforge", "neoforge-26.1"),
        ("26.3", "neoforge", "neoforge-26.1"),
        ("1.20.1", "neoforge", "forge-1.20.1"),  # NeoForge 1.20.1 carga los mods de Forge
        ("1.12.2", "forge", None),
        ("1.16.5", "forge", "forge-1.16.5"),
        ("1.16.5", "fabric", None),
        ("1.17.1", "forge", "forge-1.17.1"),
        ("1.19.4", "forge", None),
    ]
    for i, (version, loader, esperado) in enumerate(casos):
        juego = fabrica.prism(tmp_path / str(i), version, loader)
        with Instancia(juego) as inst:
            assert mod_apoyo.destino_de(inst) == esperado


def test_instalar_reemplaza_versiones_y_respeta_otros_mods(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "forge")
    (juego / "mods" / "otro-mod.jar").write_bytes(b"otro")
    (juego / "mods" / "modpackes_runtime-forge-1.20.1-0.0.9.jar").write_bytes(b"viejo")
    carpeta = _jars(tmp_path, "modpackes_runtime-forge-1.20.1-0.1.0.jar", "modpackes_runtime-forge-1.20.1-0.0.9.jar")
    with Instancia(juego) as inst:
        final = mod_apoyo.instalar(inst, carpeta)
        assert final.name == "modpackes_runtime-forge-1.20.1-0.1.0.jar" and final.read_bytes().startswith(b"PK-")
        assert [p.name for p in mod_apoyo.instalados(inst)] == [final.name]  # la versión vieja ya no está
        assert (juego / "mods" / "otro-mod.jar").read_bytes() == b"otro"
        assert mod_apoyo.quitar(inst) == [final] and mod_apoyo.quitar(inst) == []
    assert (juego / "mods" / "otro-mod.jar").is_file()  # nunca toca otro mod


def test_instalar_con_errores_claros(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path / "a", "1.12.2", "forge")
    with Instancia(juego) as inst, pytest.raises(ValueError, match="Todavía no hay mod de apoyo"):
        mod_apoyo.instalar(inst, tmp_path)
    for i, version in enumerate(("1.16.5", "1.18.2", "1.19.2")):  # se dice por qué no, no solo «todavía»
        imposible = fabrica.prism(tmp_path / f"c{i}", version, "fabric")
        with Instancia(imposible) as inst, pytest.raises(ValueError, match="no tiene en esa versión un evento"):
            mod_apoyo.instalar(inst, tmp_path)
    juego2 = fabrica.prism(tmp_path / "b", "1.20.1", "forge")
    with Instancia(juego2) as inst, pytest.raises(ValueError, match="no trae el mod de apoyo"):
        mod_apoyo.instalar(inst, tmp_path / "no_hay")


def test_cli_instalar_runtime_sin_soporte(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    juego = fabrica.prism(tmp_path, "1.20.4", "neoforge")
    assert main(["instalar-runtime", str(juego.parent)]) != 0
    assert "Todavía no hay mod de apoyo" in capsys.readouterr().out  # los errores van por la salida normal
    assert main(["instalar-runtime", str(juego.parent), "--quitar"]) == 0
    assert "No había mod de apoyo" in capsys.readouterr().out


def test_plantillas_con_datos_variables_y_orden(tmp_path: Path, memoria: Memoria) -> None:
    from traductor_es.motores.base import Lote

    class Reordena(Simulador):
        """Traduce bien, salvo una frase donde cambia el orden de los datos."""

        def traducir_lote(self, lote: Lote) -> dict[str, str]:
            salida = super().traducir_lote(lote)
            for e in lote.entradas:
                if "gave" in e.texto:  # «⟦0⟧ gave ⟦1⟧ coins» → los marcadores al revés
                    salida[e.id] = "⟦1⟧ monedas de ⟦0⟧"
            return salida

    juego = fabrica.prism(tmp_path, "1.20.1", "forge")
    fabrica.jar(
        juego / "mods" / "m.jar",
        {"com/m/Chat.class": _clase("literal", "Hello %s, welcome back to the farm!", "%s gave %d coins to the shop")},
    )
    avisos: list[str] = []
    with Instancia(juego) as inst:
        ctx = Contexto(inst, Respaldo(juego), pack=PackSalida(inst), registro=avisos.append)
        modulo = TextoDeJava(ctx)
        piezas = modulo.recolectar()
        assert all("marcadores" in p.pista for p in piezas)  # el motor sabe que debe respetar el orden
        resumen = traducir_modulo(modulo, Traductor(Reordena(), memoria, Glosario()))
        pack = ctx.pack_listo().raiz
    tabla = json.loads((pack / RUTA_TABLA.format(variante="es_mx")).read_text("utf-8"))
    assert tabla == {"Hello %s, welcome back to the farm!": "«ES» Hello %s, welcome back to the farm!"}
    assert resumen.traducidos == 1 and resumen.pendientes == 1 and any("cambió el orden" in a for a in avisos)


def test_estado_del_mod_de_apoyo(tmp_path: Path) -> None:
    sin_soporte = fabrica.prism(tmp_path / "a", "1.20.4", "neoforge")
    with Instancia(sin_soporte) as inst:
        assert "no hay mod de apoyo" in mod_apoyo.estado(inst)[0].lower()
    juego = fabrica.prism(tmp_path / "b", "1.20.1", "forge")
    carpeta = _jars(tmp_path, "modpackes_runtime-forge-1.20.1-0.1.0.jar")
    with Instancia(juego) as inst:
        texto = " ".join(mod_apoyo.estado(inst, tmp_path / "vacia"))
        assert "NO lo trae" in texto and "No está instalado" in texto and "Todavía no hay tabla" in texto
        mod_apoyo.instalar(inst, carpeta)
        tabla = juego / "resourcepacks" / "Traduccion_ES" / "assets" / "modpackes_runtime" / "textos" / "es_mx.json"
        tabla.parent.mkdir(parents=True)
        tabla.write_text("{}", encoding="utf-8")
        texto = " ".join(mod_apoyo.estado(inst, carpeta))
        assert "lo trae" in texto and "modpackes_runtime-forge-1.20.1-0.1.0.jar" in texto and "Todo listo" in texto


def test_cli_cobertura_en_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    juego = _instancia_con_mod(tmp_path)
    assert main(["cobertura", str(juego.parent), "--java", "--json"]) == 0
    salida = capsys.readouterr().out
    datos = json.loads(salida)  # solo JSON: sin cabecera ni líneas de texto
    assert any(h["categoria"] == "java" and "You can't use chat" in " ".join(h["ejemplos"]) for h in datos)


def test_estado_en_quilt_avisa_que_es_el_mod_de_fabric(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "quilt")
    with Instancia(juego) as inst:
        texto = " ".join(mod_apoyo.estado(inst, tmp_path / "vacia"))
    assert "fabric-1.20.1" in texto and "Quilted Fabric API" in texto and "no se ha probado en Quilt" in texto


def test_estado_en_neoforge_1_20_1_avisa_que_es_el_mod_de_forge(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "neoforge")
    with Instancia(juego) as inst:
        texto = " ".join(mod_apoyo.estado(inst, tmp_path / "vacia"))
    assert "forge-1.20.1" in texto and "fork de Forge" in texto and "no se ha probado" in texto


def test_estado_avisa_si_el_jar_instalado_es_de_otra_version(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.21.1", "fabric")
    (juego / "mods" / "modpackes_runtime-fabric-1.20.1-0.1.0.jar").write_bytes(b"viejo")
    pack = juego / "resourcepacks" / "Traduccion_ES" / "assets" / "modpackes_runtime" / "textos"
    pack.mkdir(parents=True)
    (pack / "es_mx.json").write_text("{}", encoding="utf-8")
    with Instancia(juego) as inst:
        texto = " ".join(mod_apoyo.estado(inst, tmp_path / "vacia"))
    assert "no es el de esta versión (fabric-1.21.1)" in texto and "Todo listo" not in texto


def test_instalar_no_borra_el_mod_viejo_si_la_copia_falla(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", "forge")
    viejo = juego / "mods" / "modpackes_runtime-forge-1.20.1-0.0.9.jar"
    viejo.write_bytes(b"viejo")
    carpeta = _jars(tmp_path, "modpackes_runtime-forge-1.20.1-0.1.0.jar")

    def copia_que_falla(*_a: object, **_k: object) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(mod_apoyo.shutil, "copyfile", copia_que_falla)
    with Instancia(juego) as inst, pytest.raises(OSError, match="disco lleno"):
        mod_apoyo.instalar(inst, carpeta)
    assert viejo.read_bytes() == b"viejo"  # el que ya funcionaba sigue ahí

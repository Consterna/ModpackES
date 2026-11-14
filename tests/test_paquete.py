"""Paquete de traducción (.modpackes.zip), importar resource packs y el pack listo para publicar."""

import json
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from traductor_es import configuracion
from traductor_es.__main__ import main
from traductor_es.fuentes import vanilla
from traductor_es.fuentes.modpack import DatosModpack, datos_del_modpack
from traductor_es.fuentes.version import rango_publicable
from traductor_es.motores.base import Lote
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Fila, Memoria
from traductor_es.proceso import Proceso
from traductor_es.salida import exportar, paquete
from traductor_es.salida.resource_pack import leer_marca

from . import fabrica

TEXTOS = {"item.m.wrench": "Wrench", "item.m.gear": "Iron Gear", "item.m.plate": "Copper Plate"}


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    def ninguna() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", ninguna)


class MotorDePrueba(Simulador):
    """Como el simulador, pero con nombre de motor real: lo que traduce sí se comparte en un paquete."""

    @property
    def nombre(self) -> str:
        return "prueba:modelo-1"


class SinLlamadas(Simulador):
    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        raise AssertionError("aplicar un paquete no puede llamar al motor")


def _instancia(base: Path, nombre: str = "Pack", textos: dict[str, str] = TEXTOS, version: str = "1.20.1") -> Path:
    juego = fabrica.prism(base, version, nombre=nombre)
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", textos))
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _lang_escrito(juego: Path, idioma: str = "es_mx") -> dict[str, str]:
    ruta = juego / "resourcepacks" / "Traduccion_ES" / "assets" / "m" / "lang" / f"{idioma}.json"
    return json.loads(ruta.read_text("utf-8"))


def _traducir_y_exportar(tmp_path: Path, memoria: Memoria) -> Path:
    juego = _instancia(tmp_path / "a")
    memoria.guardar({"Sin relación con el pack": "Nada que ver"}, "es_mx", "ui", "prueba:modelo-1")
    memoria.corregir("Wrench", "es_mx", "Llave inglesa")
    memoria.corregir("Otra cosa", "es_mx", "Otra corrección")
    configuracion.guardar_glosario_usuario({"Gear": "Engranaje"})
    with Proceso(juego, MotorDePrueba(), grupos=["mods"], memoria=memoria) as p:
        p.ejecutar()
        destino = tmp_path / "salida" / "pack.modpackes.zip"
        resumen = paquete.exportar_paquete(p, destino, revisado=True)
    assert resumen.memoria == 2 and resumen.correcciones == 1 and resumen.glosario == 1
    assert resumen.modelos == ["prueba:modelo-1"] and "2 traducciones" in str(resumen)
    return destino


# ------------------------------------------------------------------ exportar e importar un paquete
def test_el_paquete_lleva_solo_lo_que_usa_el_modpack(tmp_path: Path) -> None:
    with Memoria(":memory:") as memoria:
        destino = _traducir_y_exportar(tmp_path, memoria)
    with zipfile.ZipFile(destino) as z:
        assert set(z.namelist()) == {"modpackes.json", "memoria.json", "correcciones.json", "glosario.json"}
        meta = json.loads(z.read("modpackes.json"))
        filas = json.loads(z.read("memoria.json"))
        correcciones = json.loads(z.read("correcciones.json"))
    assert meta["formato"] == paquete.FORMATO and meta["dialecto"] == "es_mx" and meta["revisado"] is True
    assert meta["modpack"]["nombre"] == "Pack" and meta["minecraft"] == "1.20.1"
    assert meta["modelos"] == ["prueba:modelo-1"]
    assert {f["origen"] for f in filas} == {"Iron Gear", "Copper Plate"}  # «Wrench» va como corrección
    assert correcciones == {"Wrench": "Llave inglesa"}  # la corrección de otro texto no viaja


def test_importar_aplica_sin_llamar_al_motor(tmp_path: Path) -> None:
    with Memoria(":memory:") as memoria:
        destino = _traducir_y_exportar(tmp_path, memoria)
    configuracion.guardar_glosario_usuario({"Gear": "Rueda dentada", "Plate": "Placa"})
    otra = _instancia(tmp_path / "b")
    motor = SinLlamadas()
    with Memoria(":memory:") as memoria, Proceso(otra, motor, grupos=["mods"], memoria=memoria) as p:
        resumen, informe = paquete.aplicar(p, destino)
        assert memoria.correccion("Wrench", "es_mx") == "Llave inglesa"
        assert memoria.obtener("Iron Gear", "es_mx", "ui") == "«ES» Iron Gear"
    assert resumen.memoria == 2 and resumen.correcciones == 1 and resumen.glosario == 0
    assert resumen.conservados == 1  # «Gear» del usuario se queda como estaba
    assert configuracion.leer_glosario_usuario() == {"Gear": "Rueda dentada", "Plate": "Placa"}
    assert _lang_escrito(otra)["item.m.wrench"] == "Llave inglesa"
    assert informe.modulos and not informe.avisos
    assert leer_marca(otra / "resourcepacks" / "Traduccion_ES")["motores"] == ["prueba:modelo-1"]
    assert 'file/Traduccion_ES"' in (otra / "options.txt").read_text("utf-8")


def test_importar_avisa_si_el_modpack_o_la_version_no_coinciden(tmp_path: Path) -> None:
    with Memoria(":memory:") as memoria:
        destino = _traducir_y_exportar(tmp_path, memoria)
    otra = _instancia(tmp_path / "b", nombre="Otro", version="1.20.4")
    with Memoria(":memory:") as memoria, Proceso(otra, SinLlamadas(), grupos=["mods"], memoria=memoria) as p:
        resumen, informe = paquete.aplicar(p, destino, activar=False)
    assert any("«Pack»" in a for a in resumen.avisos) and any("Minecraft 1.20.1" in a for a in resumen.avisos)
    assert informe.avisos[: len(resumen.avisos)] == resumen.avisos


def _paquete_a_mano(ruta: Path, meta: Mapping[str, object], filas: Sequence[object] = (), **otros: object) -> Path:
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("modpackes.json", json.dumps(meta))
        z.writestr("memoria.json", json.dumps(list(filas)))
        for nombre, datos in otros.items():
            z.writestr(f"{nombre}.json", json.dumps(datos))
    return ruta


def test_un_paquete_roto_o_ajeno_no_entra_a_la_memoria(tmp_path: Path) -> None:
    juego = _instancia(tmp_path / "a")
    meta = {"formato": 1, "dialecto": "es_mx", "modpack": {"nombre": "Pack"}, "minecraft": "1.20.1"}
    filas = [
        {"origen": "Iron Gear", "ambito": "ui", "traduccion": "Engranaje de hierro", "motor": "x"},
        {"origen": "Costs %s", "ambito": "ui", "traduccion": "Cuesta", "motor": "x"},  # perdió un código
        {"origen": "Copper Plate", "ambito": "../otro", "traduccion": "Placa", "motor": "x"},  # ámbito raro
        {"origen": "Copper Plate", "ambito": "ui", "traduccion": "   ", "motor": "x"},  # vacía
        {"origen": "Copper Plate", "ambito": "ui", "traduccion": "x" * 30_000, "motor": "x"},  # enorme
        "no es un objeto",
    ]
    ruta = _paquete_a_mano(
        tmp_path / "raro.modpackes.zip", meta, filas,
        correcciones={"Wrench": "Llave", "Costs %s": "Cuesta"}, glosario={"Gear": 5, "": "vacío", "Plate": "Placa"},
    )  # fmt: skip
    with Memoria(":memory:") as memoria, Proceso(juego, SinLlamadas(), grupos=["mods"], memoria=memoria) as p:
        resumen = paquete.importar(p, ruta)
        assert memoria.cantidad() == 1 and memoria.correcciones("es_mx") == {"Wrench": "Llave"}
    assert resumen.memoria == 1 and resumen.correcciones == 1 and resumen.glosario == 1
    assert resumen.descartados == 8 and "8 textos dañados" in str(resumen)
    assert configuracion.leer_glosario_usuario() == {"Plate": "Placa"}


@pytest.mark.parametrize(
    ("meta", "error"),
    [
        ({"formato": 99, "dialecto": "es_mx"}, "más nueva"),
        ({"formato": 1, "dialecto": "es_ar"}, "dialecto"),
        ({"formato": "1", "dialecto": "es_mx"}, "no es un paquete"),
        ({"formato": 1, "dialecto": "es_es"}, "elige ese dialecto"),
    ],
)
def test_paquetes_que_no_se_importan(tmp_path: Path, meta: dict[str, object], error: str) -> None:
    juego = _instancia(tmp_path / "a")
    ruta = _paquete_a_mano(tmp_path / "p.modpackes.zip", meta)
    with (
        Memoria(":memory:") as memoria,
        Proceso(juego, SinLlamadas(), grupos=["mods"], memoria=memoria) as p,
        pytest.raises(ValueError, match=error),
    ):
        paquete.importar(p, ruta)


def test_exportar_sin_nada_traducido_avisa(tmp_path: Path) -> None:
    juego = _instancia(tmp_path / "a")
    with Memoria(":memory:") as memoria, Proceso(juego, Simulador(), grupos=["mods"], memoria=memoria) as p:
        with pytest.raises(ValueError, match="traduce primero"):
            paquete.exportar_paquete(p, tmp_path / "x.modpackes.zip")
        assert not (tmp_path / "x.modpackes.zip").exists()


def test_memoria_filas_e_importar() -> None:
    with Memoria(":memory:") as m:
        m.guardar({"A": "a", "B": "b"}, "es_mx", "ui", "motor:1")
        filas = m.filas([("A", "ui"), ("A", "ui"), ("A", "mision"), ("C", "ui")], "es_mx")
        assert filas == [Fila("A", "ui", "a", "motor:1")]
        assert m.importar([Fila("C", "libro", "c", "otro")], "es_es") == 1
        assert m.obtener("C", "es_es", "libro") == "c" and m.obtener("C", "es_mx", "libro") is None


# ------------------------------------------------------------------ importar un resource pack
def _resource_pack(textos: dict[str, str], idioma: str = "es_es") -> dict[str, bytes | str | Mapping[str, object]]:
    archivos: dict[str, bytes | str | Mapping[str, object]] = {"pack.mcmeta": {"pack": {"pack_format": 15}}}
    archivos.update(fabrica.lang("m", idioma, textos))
    return archivos


def test_importar_un_resource_pack_que_no_esta_activo(tmp_path: Path) -> None:
    juego = _instancia(tmp_path / "a")
    zip_pack = fabrica.jar(
        tmp_path / "descargas" / "Español.zip",
        _resource_pack({"item.m.wrench": "Llave inglesa", "item.m.gear": "Iron Gear", "item.otro.x": "Otra"}),
    )
    with Memoria(":memory:") as memoria, Proceso(juego, SinLlamadas(), grupos=["mods"], memoria=memoria) as p:
        resumen, _informe = paquete.aplicar(p, zip_pack)
        assert memoria.obtener("Wrench", "es_mx", "ui") == "Llave inglesa"
    assert resumen.origen == "resource pack" and resumen.memoria == 1
    assert resumen.descartados == 1  # «Iron Gear» venía sin traducir
    assert _lang_escrito(juego)["item.m.wrench"] == "Llave inglesa"
    assert "Iron Gear" not in _lang_escrito(juego).values()  # lo que el pack no tradujo no se inventa
    assert leer_marca(juego / "resourcepacks" / "Traduccion_ES")["motores"] == ["pack:Español.zip"]


def test_importar_un_resource_pack_en_carpeta_aunque_lo_haya_hecho_la_app(tmp_path: Path) -> None:
    juego = _instancia(tmp_path / "a")
    carpeta = tmp_path / "Traduccion_vieja"
    for nombre, contenido in _resource_pack({"item.m.plate": "Placa de cobre"}, "es_mx").items():
        destino = carpeta / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido if isinstance(contenido, bytes) else json.dumps(contenido).encode())
    (carpeta / "traductor_es.json").write_text("{}", encoding="utf-8")  # la marca de los packs de la app
    with Memoria(":memory:") as memoria, Proceso(juego, SinLlamadas(), grupos=["mods"], memoria=memoria) as p:
        assert paquete.importar(p, carpeta).memoria == 1
    with Memoria(":memory:") as memoria, Proceso(juego, SinLlamadas(), grupos=["mods"], memoria=memoria) as p:
        with pytest.raises(ValueError, match="no tiene textos en español"):
            paquete.importar(p, fabrica.jar(tmp_path / "vacio.zip", _resource_pack({}, "es_mx")))
        with pytest.raises(ValueError, match="no es un resource pack"):
            paquete.importar(p, fabrica.jar(tmp_path / "raro.zip", {"x.txt": "x"}))
        with pytest.raises(ValueError, match="No sé importar"):
            paquete.importar(p, (tmp_path / "notas.txt"))


# ------------------------------------------------------------------ pack listo para publicar
def test_el_pack_publicado_lleva_icono_leeme_y_formatos(tmp_path: Path) -> None:
    juego = _instancia(tmp_path / "a", version="1.20.4")
    (juego / "config").mkdir()
    (juego / "config" / "bcc-common.json").write_text(
        json.dumps({"modpackName": {"value": "Mi Pack"}, "modpackVersion": {"value": "2.1.0"}}), encoding="utf-8"
    )
    with Memoria(":memory:") as memoria, Proceso(juego, MotorDePrueba(), grupos=["mods"], memoria=memoria) as p:
        p.ejecutar()
    nombre = exportar.nombre_sugerido(juego)
    assert nombre == "Traduccion_ES_Mi_Pack_2.1.0.zip"
    n = exportar.exportar_pack(juego, tmp_path / nombre, revisado=False)
    with zipfile.ZipFile(tmp_path / nombre) as z:
        nombres = set(z.namelist())
        assert n == len(nombres) and {"pack.png", "LEEME.txt", "pack.mcmeta"} <= nombres
        assert z.read("pack.png").startswith(b"\x89PNG")
        meta = json.loads(z.read("pack.mcmeta"))["pack"]
        leeme = z.read("LEEME.txt").decode("utf-8")
        marca = json.loads(z.read("traductor_es.json"))
    assert "indice" in leer_marca(juego / "resourcepacks" / "Traduccion_ES")  # el índice de cambios sí está en local
    assert "indice" not in marca and marca["motores"] == ["prueba:modelo-1"]  # pero no viaja con el pack
    assert meta["pack_format"] == 22 and meta["supported_formats"] == [18, 32]
    assert "Mi Pack 2.1.0" in meta["description"]
    assert "traducción automática" in leeme and "Nadie la revisó" in leeme
    assert "prueba (modelo-1)" in leeme and "MI PACK 2.1.0" in leeme and "1 mods: m" in leeme


@pytest.mark.parametrize(
    ("formato", "rango"),
    [(15, None), (18, (18, 32)), (22, (18, 32)), (34, (34, 64)), (64, (34, 64)), (65, None), (5, None)],
)
def test_rango_publicable(formato: int, rango: tuple[int, int] | None) -> None:
    assert rango_publicable(formato) == rango


def test_mcmeta_publicable_respeta_lo_que_no_entiende() -> None:
    datos = DatosModpack("P", "1")
    assert exportar.mcmeta_publicable(b"no es json", datos) == b"no es json"
    assert exportar.mcmeta_publicable(b"[]", datos) == b"[]"
    nuevo = json.loads(exportar.mcmeta_publicable(b'{"pack": {"min_format": 75, "max_format": 75}}', datos))
    assert "supported_formats" not in nuevo["pack"] and nuevo["pack"]["description"].endswith("P 1")


# ------------------------------------------------------------------ nombre y versión del modpack
def test_datos_del_modpack_de_varias_fuentes(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1", nombre="Carpeta")
    assert datos_del_modpack(juego) == DatosModpack("Carpeta")
    cfg = juego.parent / "instance.cfg"
    cfg.write_text("name=Mi instancia\nManagedPackName=Pack Oficial\nManagedPackVersionName=v3\n", encoding="utf-8")
    assert datos_del_modpack(juego) == DatosModpack("Pack Oficial", "v3")
    (juego / "config").mkdir()
    toml = '[general]\nmodpackName = "Desde BCC"\nmodpackVersion = "CHANGE_ME"\n'
    (juego / "config" / "bcc-common.toml").write_text(toml, encoding="utf-8")
    assert datos_del_modpack(juego) == DatosModpack("Desde BCC", "v3")  # la versión sin cambiar no cuenta


def test_datos_del_modpack_de_curseforge_y_modrinth(tmp_path: Path) -> None:
    juego = fabrica.curseforge(tmp_path, "1.20.1", "forge", nombre="CF")
    datos = json.loads((juego / "minecraftinstance.json").read_text("utf-8"))
    datos["manifest"] = {"name": "All the Things", "version": "1.4"}
    (juego / "minecraftinstance.json").write_text(json.dumps(datos), encoding="utf-8")
    assert datos_del_modpack(juego) == DatosModpack("All the Things", "1.4")
    suelto = tmp_path / "suelto" / ".minecraft"
    suelto.mkdir(parents=True)
    (suelto / "modrinth.index.json").write_text(json.dumps({"name": "MR", "versionId": "v9"}), encoding="utf-8")
    assert datos_del_modpack(suelto) == DatosModpack("MR", "v9")
    assert paquete.nombre_de_archivo(DatosModpack("A/B: c", "1.0?")) == "A_B_c_1.0.modpackes.zip"


# ------------------------------------------------------------------ línea de comandos
def test_linea_de_comandos_exporta_e_importa(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    juego = _instancia(tmp_path / "a")
    with Memoria(configuracion.ruta_memoria()) as memoria:
        memoria.guardar({"Wrench": "Llave inglesa", "Iron Gear": "Engranaje de hierro"}, "es_mx", "ui", "gemini:x")
    destino = tmp_path / "p.modpackes.zip"
    assert main(["paquete", "exportar", str(juego), str(destino), "--revisado"]) == 0
    assert "2 traducciones" in capsys.readouterr().out
    configuracion.ruta_memoria().unlink()
    otra = _instancia(tmp_path / "b")
    assert main(["paquete", "importar", str(otra), str(destino), "--no-activar"]) == 0
    salida = capsys.readouterr().out
    assert "Importado (paquete): 2 traducciones" in salida and "1 sigue en inglés" in salida
    assert _lang_escrito(otra)["item.m.gear"] == "Engranaje de hierro"
    assert "vanilla" in (otra / "options.txt").read_text("utf-8")
    assert main(["exportar", str(otra), str(tmp_path / "pub.zip"), "--revisado"]) == 0
    with zipfile.ZipFile(tmp_path / "pub.zip") as z:
        assert "Una persona la revisó" in z.read("LEEME.txt").decode("utf-8")
        assert "gemini (x)" in z.read("LEEME.txt").decode("utf-8")
    assert main(["exportar", str(otra), str(tmp_path / "kit.zip"), "--kit"]) == 0
    assert main(["paquete", "importar", str(otra)]) == 1
    assert "Uso: paquete importar" in capsys.readouterr().out


def test_el_kit_de_servidor_lleva_el_pack_publicable(tmp_path: Path) -> None:
    import io

    juego = _instancia(tmp_path / "a")
    with Memoria(":memory:") as memoria, Proceso(juego, MotorDePrueba(), grupos=["mods"], memoria=memoria) as p:
        p.ejecutar()
    exportar.exportar_kit_servidor(juego, tmp_path / "kit.zip")
    with zipfile.ZipFile(tmp_path / "kit.zip") as kit:
        interno = zipfile.ZipFile(io.BytesIO(kit.read("Traduccion_ES.zip")))
    with interno:
        assert {"pack.png", "LEEME.txt", "pack.mcmeta"} <= set(interno.namelist())
        assert "prueba (modelo-1)" in interno.read("LEEME.txt").decode("utf-8")


class PorDialecto(MotorDePrueba):
    """Marca cada traducción con el dialecto del pedido: «MX» o «ESP»."""

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.prefijo = "«ESP» " if "España" in lote.dialecto else "«MX» "
        return super().traducir_lote(lote)


def test_el_paquete_lleva_la_version_de_espana_y_aplicarlo_la_escribe(tmp_path: Path) -> None:
    origen = _instancia(tmp_path / "a")
    destino = tmp_path / "pack.modpackes.zip"
    with Memoria(":memory:") as memoria:
        with Proceso(origen, PorDialecto(), memoria=memoria, tambien_es_es=True) as p:
            p.ejecutar()
        with Proceso(origen, Simulador(), memoria=memoria) as p:
            resumen = paquete.exportar_paquete(p, destino)
    assert resumen.espana == len(TEXTOS) and "versión de España" in str(resumen)
    with zipfile.ZipFile(destino) as zf:
        meta = json.loads(zf.read("modpackes.json"))
        assert meta["version_espana"]["memoria"] == len(TEXTOS)
        assert "memoria_es_es.json" in zf.namelist()
    # Otra persona, otra instancia, memoria vacía y sin pedir la versión de España: el paquete la trae
    otra = _instancia(tmp_path / "b")
    with Memoria(":memory:") as memoria, Proceso(otra, SinLlamadas(), memoria=memoria) as p:
        importado, _ = paquete.aplicar(p, destino)
    assert importado.espana == len(TEXTOS)
    assert _lang_escrito(otra, "es_mx")["item.m.wrench"] == "«MX» Wrench"
    assert _lang_escrito(otra, "es_ar")["item.m.wrench"] == "«MX» Wrench"
    assert _lang_escrito(otra, "es_es")["item.m.wrench"] == "«ESP» Wrench"


def test_un_paquete_sin_version_de_espana_sigue_como_antes(tmp_path: Path) -> None:
    origen = _instancia(tmp_path / "a")
    destino = tmp_path / "pack.modpackes.zip"
    with Memoria(":memory:") as memoria, Proceso(origen, PorDialecto(), memoria=memoria) as p:
        p.ejecutar()
        paquete.exportar_paquete(p, destino)
    with zipfile.ZipFile(destino) as zf:
        assert "memoria_es_es.json" not in zf.namelist()
        assert "version_espana" not in json.loads(zf.read("modpackes.json"))
    otra = _instancia(tmp_path / "b")
    with Memoria(":memory:") as memoria, Proceso(otra, SinLlamadas(), memoria=memoria) as p:
        importado, _ = paquete.aplicar(p, destino)
    assert importado.espana == 0
    assert _lang_escrito(otra, "es_es")["item.m.wrench"] == "«MX» Wrench"

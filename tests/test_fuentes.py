import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es.fuentes import deteccion, lanzadores, opciones, vanilla
from traductor_es.fuentes.contenedores import Carpeta, abrir_mod
from traductor_es.fuentes.instancia import Instancia
from traductor_es.fuentes.recursos import MARCA
from traductor_es.fuentes.version import Version, formato_datos, formato_desde_jar, formato_recursos, mcmeta
from traductor_es.nucleo.dialectos import VARIANTES

from . import fabrica

# ---------------------------------------------------------------- versiones y formatos


def test_orden_de_versiones() -> None:
    assert Version.de("26.1") > Version.de("1.21.11") > Version.de("1.21.9") > Version.de("1.21")
    assert Version.de("1.20") == Version.de("1.20.0")
    assert Version.de("1.12.2-forge").texto == "1.12.2"
    with pytest.raises(ValueError):
        Version.de("beta")


@pytest.mark.parametrize(
    ("version", "recursos", "datos"),
    [
        ("1.7.10", (1, 0), None), ("1.12.2", (3, 0), None), ("1.16.5", (6, 0), (6, 0)), ("1.18.2", (8, 0), (9, 0)),
        ("1.19.2", (9, 0), (10, 0)), ("1.20.1", (15, 0), (15, 0)), ("1.20.4", (22, 0), (26, 0)),
        ("1.21.1", (34, 0), (48, 0)), ("1.21.8", (64, 0), (81, 0)), ("1.21.11", (75, 0), (94, 1)),
        ("26.1.2", (84, 0), (101, 1)), ("26.3", (97, 1), (121, 0)),
    ],
)  # fmt: skip
def test_tabla_de_formatos(version: str, recursos: tuple[int, int], datos: tuple[int, int] | None) -> None:
    v = Version.de(version)
    assert formato_recursos(v) == recursos
    assert formato_datos(v) == datos


def test_formato_desde_el_jar_del_juego() -> None:
    assert formato_desde_jar(b'{"pack_version": 6}', "resource") == (6, 0)
    assert formato_desde_jar(b'{"pack_version": {"resource": 15, "data": 15}}', "data") == (15, 0)
    nuevo = b'{"pack_version": {"resource_major": 75, "resource_minor": 0, "data_major": 94, "data_minor": 1}}'
    assert formato_desde_jar(nuevo, "resource") == (75, 0)
    assert formato_desde_jar(nuevo, "data") == (94, 1)
    assert formato_desde_jar(b"no json", "resource") is None


def test_mcmeta_segun_version() -> None:
    assert mcmeta((15, 0), "x") == {"pack": {"description": "x", "pack_format": 15}}
    assert mcmeta((75, 0), "x") == {"pack": {"description": "x", "min_format": 75, "max_format": 75}}
    assert mcmeta((97, 1), "x")["pack"]["min_format"] == [97, 1]
    assert mcmeta((81, 0), "x", "data") == {"pack": {"description": "x", "pack_format": 81}}
    assert "min_format" in mcmeta((94, 1), "x", "data")["pack"]


# ---------------------------------------------------------------- contenedores


def test_jars_anidados(tmp_path: Path) -> None:
    ruta = fabrica.jar(
        tmp_path / "padre.jar",
        {"a.txt": "x"},
        {"META-INF/jars/hijo.jar": {"assets/hijo/lang/en_us.json": "{}"}, "META-INF/jarjar/otro.jar": {"b.txt": "y"}},
    )
    contenedores = list(abrir_mod(ruta))
    try:
        assert [c.nombre for c in contenedores] == ["padre.jar", "padre.jar!/hijo.jar", "padre.jar!/otro.jar"]
        assert contenedores[1].nombres() == ["assets/hijo/lang/en_us.json"]
    finally:
        for c in contenedores:
            c.cerrar()


def test_jar_corrupto_se_ignora(tmp_path: Path) -> None:
    roto = tmp_path / "roto.jar"
    roto.write_bytes(b"no es un zip")
    assert list(abrir_mod(roto)) == []


def test_carpeta_con_prefijo(tmp_path: Path) -> None:
    (tmp_path / "kubejs" / "lang").mkdir(parents=True)
    (tmp_path / "kubejs" / "lang" / "en_us.json").write_text("{}", encoding="utf-8")
    c = Carpeta(tmp_path, "kubejs", prefijo="assets/")
    assert c.nombres() == ["assets/kubejs/lang/en_us.json"]
    assert c.leer("assets/kubejs/lang/en_us.json") == b"{}"
    with pytest.raises(KeyError):
        c.leer("otra/cosa")


# ---------------------------------------------------------------- detección


def test_deteccion_prism(tmp_path: Path) -> None:
    for loader in ("forge", "neoforge", "fabric", "quilt"):
        juego = fabrica.prism(tmp_path / loader, "1.21.1", loader)
        d = deteccion.detectar(juego, [])
        assert (d.version, d.loader) == (Version.de("1.21.1"), loader)


def test_deteccion_curseforge(tmp_path: Path) -> None:
    juego = fabrica.curseforge(tmp_path, "1.16.5", "forge")
    d = deteccion.detectar(juego, [])
    assert (str(d.version), d.loader) == ("1.16.5", "forge")


@pytest.mark.parametrize(
    ("log", "version", "loader"),
    [
        ("[main/INFO]: Loading Minecraft 1.21.1 with Fabric Loader 0.16.0", "1.21.1", "fabric"),
        ("[main/INFO]: Loading Minecraft 1.20.1 with Quilt Loader 0.26", "1.20.1", "quilt"),
        ("ModLauncher running: args [--fml.forgeVersion, 47.2.0, --fml.mcVersion, 1.20.1]", "1.20.1", "forge"),
        ("args [--fml.neoForgeVersion, 21.1.77, --fml.mcVersion, 1.21.1]", "1.21.1", "neoforge"),
        ("[FML]: MinecraftForge v14.23.5.2860 Initialized\n[FML]: Minecraft 1.12.2", "1.12.2", "forge"),
    ],
)
def test_deteccion_por_log(tmp_path: Path, log: str, version: str, loader: str) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "latest.log").write_text(log, encoding="utf-8")
    d = deteccion.detectar(tmp_path, [])
    assert (str(d.version), d.loader, d.origen) == (version, loader, "logs/latest.log")


def test_deteccion_por_metadatos_de_mods(tmp_path: Path) -> None:
    toml = '[[dependencies.x]]\nmodId="minecraft"\nversionRange="[1.21.1,1.22)"\n'
    jars = [
        fabrica.jar(tmp_path / "a.jar", {"META-INF/neoforge.mods.toml": toml}),
        fabrica.jar(tmp_path / "b.jar", {"META-INF/neoforge.mods.toml": toml}),
        fabrica.jar(tmp_path / "c.jar", {"fabric.mod.json": json.dumps({"depends": {"minecraft": ["~1.20.1"]}})}),
    ]
    d = deteccion.detectar(tmp_path, jars)
    assert (str(d.version), d.loader) == ("1.21.1", "neoforge")
    viejos = [fabrica.jar(tmp_path / "v.jar", {"mcmod.info": json.dumps([{"modid": "x", "mcversion": "1.7.10"}])})]
    d = deteccion.detectar(tmp_path, viejos)
    assert (str(d.version), d.loader) == ("1.7.10", "forge")


def test_deteccion_por_nombres(tmp_path: Path) -> None:
    jars = [tmp_path / "jei-1.19.2-11.jar", tmp_path / "create-1.19.2-0.5.jar", tmp_path / "x-26.1.jar"]
    d = deteccion.detectar(tmp_path, jars)
    assert str(d.version) == "1.19.2" and d.origen == "nombres de los jars"


def test_sin_version_falla_con_mensaje(tmp_path: Path) -> None:
    (tmp_path / "mods").mkdir()
    with pytest.raises(ValueError, match="versión de Minecraft"):
        Instancia(tmp_path)
    with pytest.raises(ValueError, match="No encuentro"):
        Instancia(tmp_path / "nada")


# ---------------------------------------------------------------- opciones


def test_opciones(tmp_path: Path) -> None:
    fabrica.opciones(tmp_path, ["vanilla", "mod_resources", "file/A.zip", "file/B"], "ES_MX")
    o = opciones.leer(tmp_path)
    assert (o.idioma, o.packs, o.con_prefijo) == ("es_mx", ("A.zip", "B"), True)
    assert opciones.leer(tmp_path / "nada") == opciones.Opciones()


# ---------------------------------------------------------------- tabla de idiomas


def _modpack(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(
        juego / "mods" / "mod.jar",
        {
            **fabrica.lang("m", "en_us", {"a": "Iron Plate", "b": "Gold", "c": "Copper", "d": "Same", "e": "%s"}),
            **fabrica.lang("m", "es_es", {"a": "Placa de hierro", "b": "Oro", "c": "Cobre", "d": "Same"}),
            **fabrica.lang("m", "es_mx", {"a": "Placa de hierro"}),
            "assets/m/lang/en_us.lang": "a=No se usa en 1.20",
        },
        {"META-INF/jarjar/lib.jar": fabrica.lang("lib", "en_us", {"x": "Library text"})},
    )
    packs = juego / "resourcepacks"
    fabrica.jar(
        packs / "Renombra.zip", {"pack.mcmeta": "{}", **fabrica.lang("m", "en_us", {"b": "Shiny Gold", "c": "Copper"})}
    )
    fabrica.jar(packs / "Apagado.zip", {"pack.mcmeta": "{}", **fabrica.lang("m", "en_us", {"a": "Ignorado"})})
    fabrica.jar(packs / "Nuestro.zip", {MARCA: "{}", **fabrica.lang("m", "es_mx", {"b": "No leer"})})
    (juego / "kubejs" / "assets" / "kubejs" / "lang").mkdir(parents=True)
    (juego / "kubejs" / "assets" / "kubejs" / "lang" / "en_us.json").write_text('{"item.kubejs.x": "Ticket"}', "utf-8")
    fabrica.opciones(juego, ["vanilla", "file/Renombra.zip", "file/Nuestro.zip", "file/NoExiste.zip"])
    return juego


def test_tabla_con_prioridades_y_validez(tmp_path: Path) -> None:
    juego = _modpack(tmp_path)
    with Instancia(juego) as inst:
        tabla = inst.tabla_idiomas()
        assert inst.version == Version.de("1.20.1") and inst.loader == "forge"
        assert (
            tabla.textos("m", "en_us")["a"] == "Iron Plate"
        )  # el .lang se ignora en 1.13+ y el pack apagado no cuenta
        assert tabla.textos("m", "en_us")["b"] == "Shiny Gold"  # el pack activo manda
        assert tabla.es_valida("m", "es_es", "a")
        assert not tabla.es_valida("m", "es_es", "b")  # el pack cambió el inglés: «Oro» ya no corresponde
        assert tabla.es_valida("m", "es_es", "c")  # el pack repite el mismo inglés: «Cobre» sigue valiendo
        assert not tabla.es_valida("m", "es_es", "d")  # copia del inglés
        assert "b" not in tabla.textos("m", "es_mx")  # el pack generado por la app no se lee
        assert tabla.textos("lib", "en_us") == {"x": "Library text"}  # jar anidado
        assert tabla.textos("kubejs", "en_us") == {"item.kubejs.x": "Ticket"}
        pendientes = {(p.namespace, p.clave): p for p in tabla.pendientes(VARIANTES)}
    assert ("m", "e") not in pendientes  # sin texto traducible
    assert pendientes[("m", "a")].existente == "Placa de hierro"
    assert set(pendientes[("m", "a")].faltan) == set(VARIANTES) - {"es_es", "es_mx"}
    assert pendientes[("m", "b")].existente is None and pendientes[("m", "b")].ingles == "Shiny Gold"
    assert pendientes[("lib", "x")].faltan == VARIANTES


def test_legacy_usa_solo_lang(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.12.2")
    fabrica.jar(
        juego / "mods" / "viejo.jar",
        {**fabrica.lang("v", "en_US", {"a": "Old Item"}, legacy=True), **fabrica.lang("v", "en_us", {"a": "JSON"})},
    )
    fabrica.jar(juego / "mods" / "1.12.2" / "extra.jar", fabrica.lang("w", "en_us", {"b": "Extra"}, legacy=True))
    with Instancia(juego) as inst:
        assert inst.legacy
        tabla = inst.tabla_idiomas()
        assert tabla.textos("v", "en_us") == {"a": "Old Item"}
        assert tabla.textos("w", "en_us") == {"b": "Extra"}  # mods/<versión>/ de Forge antiguo


def test_vanilla_oficial_igual_al_ingles_es_valido(tmp_path: Path) -> None:
    raiz = tmp_path / "launcher"
    fabrica.jar(
        raiz / "versions" / "1.20.1" / "1.20.1.jar",
        {
            "version.json": {"pack_version": {"resource": 15, "data": 15}},
            "assets/minecraft/lang/en_us.json": {"menu.title": "Minecraft", "item.x": "Stone"},
        },
    )
    (raiz / "versions" / "1.20.1" / "1.20.1.json").write_text('{"assetIndex": {"id": "5"}}', encoding="utf-8")
    contenido = json.dumps({"menu.title": "Minecraft", "item.x": "Piedra"}).encode()
    import hashlib

    h = hashlib.sha1(contenido).hexdigest()
    (raiz / "assets" / "objects" / h[:2]).mkdir(parents=True)
    (raiz / "assets" / "objects" / h[:2] / h).write_bytes(contenido)
    (raiz / "assets" / "indexes").mkdir(parents=True)
    objetos = {"objects": {"minecraft/lang/es_mx.json": {"hash": h, "size": len(contenido)}}}
    (raiz / "assets" / "indexes" / "5.json").write_text(json.dumps(objetos), encoding="utf-8")
    v = vanilla.cargar(Version.de("1.20.1"), ["en_us", "es_mx", "es_es"], [tmp_path / "otro", raiz])
    assert v.formato_recursos == (15, 0)
    assert v.textos["es_mx"] == {"menu.title": "Minecraft", "item.x": "Piedra"}
    assert "es_es" not in v.textos


def test_lanzadores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    appdata, home = tmp_path / "appdata", tmp_path / "home"
    fabrica.prism(appdata / "PrismLauncher" / "instances", "1.20.1", nombre="Uno")
    (appdata / "PrismLauncher" / "instances" / ".tmp").mkdir()
    fabrica.curseforge(home / "curseforge" / "minecraft" / "Instances", "1.19.2", "forge", nombre="Dos")
    (appdata / "ModrinthApp" / "profiles" / "Tres" / "mods").mkdir(parents=True)
    (appdata / ".minecraft" / "mods").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    encontradas = {(e.lanzador, e.nombre) for e in lanzadores.buscar()}
    assert encontradas == {
        ("Prism Launcher", "Uno"),
        ("CurseForge", "Dos"),
        ("Modrinth", "Tres"),
        ("Launcher oficial", ".minecraft"),
    }


def test_lanzador_ilegible_no_impide_ver_los_demas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Una carpeta sin permiso (o en una red caída) no puede tumbar la ventana al abrirla."""
    appdata, home = tmp_path / "appdata", tmp_path / "home"
    fabrica.prism(appdata / "PrismLauncher" / "instances", "1.20.1", nombre="Uno")
    (appdata / "ModrinthApp" / "profiles" / "Tres" / "mods").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    listar = Path.iterdir

    def iterdir(self: Path) -> Iterator[Path]:
        if self.name == "profiles":
            raise PermissionError("Acceso denegado")
        return listar(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    assert {(e.lanzador, e.nombre) for e in lanzadores.buscar()} == {("Prism Launcher", "Uno")}


def test_existente_prefiere_las_variantes_elegidas(tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(
        juego / "mods" / "m.jar",
        {
            **fabrica.lang("m", "en_us", {"a": "Computer"}),
            **fabrica.lang("m", "es_ar", {"a": "Computadora (AR)"}),
            **fabrica.lang("m", "es_es", {"a": "Ordenador"}),
        },
    )
    with Instancia(juego) as inst:
        tabla = inst.tabla_idiomas()
        assert tabla.pendientes(VARIANTES)[0].existente == "Ordenador"
        assert tabla.pendientes(VARIANTES, preferidas=("es_ar",))[0].existente == "Computadora (AR)"

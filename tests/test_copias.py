from pathlib import Path

from traductor_es.salida.copias import Respaldo


def test_traducir_restaurar_y_volver_a_traducir(tmp_path: Path) -> None:
    archivo = tmp_path / "config" / "q.snbt"
    archivo.parent.mkdir(parents=True)
    archivo.write_bytes(b"ingles v1")
    r = Respaldo(tmp_path)
    assert r.original(archivo) == b"ingles v1"
    r.escribir(archivo, b"espanol v1")
    # Segunda ejecución: el original sigue siendo el inglés, aunque el archivo ya esté traducido
    assert Respaldo(tmp_path).original(archivo) == b"ingles v1"
    assert Respaldo(tmp_path).restaurar() == [archivo]
    assert archivo.read_bytes() == b"ingles v1"
    assert Respaldo(tmp_path).restaurar() == []  # nada más que restaurar


def test_actualizacion_del_modpack_renueva_la_copia(tmp_path: Path) -> None:
    archivo = tmp_path / "q.json"
    archivo.write_bytes(b"ingles v1")
    r = Respaldo(tmp_path)
    r.original(archivo)
    r.escribir(archivo, b"espanol v1")
    archivo.write_bytes(b"ingles v2")  # el modpack se actualizó y pisó la traducción
    r = Respaldo(tmp_path)
    assert r.original(archivo) == b"ingles v2"
    r.escribir(archivo, b"espanol v2")
    r.restaurar()
    assert archivo.read_bytes() == b"ingles v2"


def test_archivo_creado_queda_neutro_al_restaurar(tmp_path: Path) -> None:
    nuevo = tmp_path / "lang" / "es_mx.snbt"
    r = Respaldo(tmp_path)
    assert r.original(nuevo) is None
    r.escribir(nuevo, b'{ a: "x" }', neutro=b"{\n}\n")
    assert Respaldo(tmp_path).original(nuevo) is None  # sigue sin «original»: lo creó la app
    Respaldo(tmp_path).restaurar()
    assert nuevo.read_bytes() == b"{\n}\n"


def test_archivo_del_modpack_escrito_sin_pedir_original(tmp_path: Path) -> None:
    existente = tmp_path / "lang" / "es_es.snbt"
    existente.parent.mkdir()
    existente.write_bytes(b"del modpack")
    r = Respaldo(tmp_path)
    r.escribir(existente, b"completado")
    assert r.original(existente) == b"del modpack"
    r.restaurar()
    assert existente.read_bytes() == b"del modpack"


def test_restaurar_por_prefijo(tmp_path: Path) -> None:
    a, b = tmp_path / "config" / "ftbquests" / "a", tmp_path / "kubejs" / "b"
    for x in (a, b):
        x.parent.mkdir(parents=True)
        x.write_bytes(b"orig")
    r = Respaldo(tmp_path)
    r.escribir(a, b"x")
    r.escribir(b, b"y")
    assert r.restaurar("config/ftbquests/") == [a]
    assert b.read_bytes() == b"y" and r.registrados() == ["kubejs/b"]


def test_cambio_despues_de_restaurar_renueva_la_copia(tmp_path: Path) -> None:
    archivo = tmp_path / "q.json"
    archivo.write_bytes(b"v1")
    r = Respaldo(tmp_path)
    r.escribir(archivo, b"es1")
    r.restaurar()
    archivo.write_bytes(b"v2")  # el modpack se actualiza después de restaurar
    r = Respaldo(tmp_path)
    assert r.original(archivo) == b"v2"
    r.escribir(archivo, b"es2")
    r.restaurar()
    assert archivo.read_bytes() == b"v2"


def test_original_solo_lee(tmp_path: Path) -> None:
    archivo = tmp_path / "q.json"
    archivo.write_bytes(b"v1")
    assert Respaldo(tmp_path).original(archivo) == b"v1"
    assert not (tmp_path / "traductor_es").exists()

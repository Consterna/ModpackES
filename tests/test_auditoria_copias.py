"""Copias de seguridad ante un registro hostil y ante cortes en cada escritura.

Promesa del producto: «Restaurar devuelve los bytes originales» y nada se escribe fuera de la instancia.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from traductor_es.salida.copias import Respaldo


class Corte(Exception):
    """Simula que el proceso muere (o el disco se llena) justo en una escritura."""


@pytest.fixture
def juego(tmp_path: Path) -> Path:
    raiz = tmp_path / "instancias" / "Pack" / "minecraft"
    (raiz / "traductor_es").mkdir(parents=True)
    return raiz


def _registro(juego: Path, datos: dict[str, Any]) -> None:
    (juego / "traductor_es" / "registro.json").write_text(json.dumps(datos), encoding="utf-8")


@pytest.mark.parametrize(
    "clave",
    [
        "../../carga/x.txt",
        "../fuera.txt",
        "kubejs/../../../fuera.txt",
        "C:/Windows/fuera.txt",
        "C:fuera.txt",
        "/fuera.txt",
        "//servidor/recurso/fuera.txt",
        "kubejs\\..\\..\\..\\fuera.txt",
    ],
)
def test_registro_con_claves_que_salen_de_la_instancia_no_escribe_fuera(juego: Path, clave: str) -> None:
    # Un modpack malicioso trae su propio traductor_es/registro.json y el «original» dentro de la instancia
    (juego / "carga").mkdir()
    (juego / "carga" / "x.txt").write_bytes(b"CONTENIDO DEL ATACANTE")
    _registro(juego, {clave: {"existia": True, "escrito": "abc"}, "kubejs/bien.js": {"existia": False}})
    antes = {p: p.read_bytes() for p in juego.parent.parent.rglob("*") if p.is_file()}
    r = Respaldo(juego)
    assert clave not in r.registrados()
    r.restaurar()
    despues = {p: p.read_bytes() for p in juego.parent.parent.rglob("*") if p.is_file()}
    nuevos = {p for p in despues if p not in antes and not p.is_relative_to(juego / "traductor_es")}
    assert nuevos == set()
    assert not (juego / clave).exists() or (juego / clave).resolve().is_relative_to(juego.resolve())


def test_registro_hostil_no_borra_ni_vacia_archivos_de_fuera(juego: Path) -> None:
    victima = juego.parent / "importante.txt"
    victima.write_bytes(b"datos del usuario")
    _registro(juego, {"../importante.txt": {"existia": False, "escrito": "abc", "neutro": ""}})
    Respaldo(juego).restaurar()
    assert victima.read_bytes() == b"datos del usuario"


def test_registro_legitimo_sigue_funcionando(juego: Path) -> None:
    archivo = juego / "kubejs" / "a.js"
    archivo.parent.mkdir()
    archivo.write_bytes(b"ORIGINAL")
    Respaldo(juego).escribir(archivo, b"TRADUCIDO")
    assert Respaldo(juego).registrados() == ["kubejs/a.js"]
    Respaldo(juego).restaurar()
    assert archivo.read_bytes() == b"ORIGINAL"


def _cortar_en(monkeypatch: pytest.MonkeyPatch, n: int) -> Callable[[], int]:
    """Hace que la n-ésima escritura de archivo (write_bytes, write_text o replace) falle. Devuelve el contador."""
    cuenta = [0]
    originales = {nombre: getattr(Path, nombre) for nombre in ("write_bytes", "write_text", "replace")}

    def envolver(nombre: str) -> Callable[..., Any]:
        def nueva(self: Path, *args: Any, **kwargs: Any) -> Any:
            cuenta[0] += 1
            if cuenta[0] == n:
                if nombre == "write_bytes":  # escritura a medias: la mitad de los bytes y luego el corte
                    datos: bytes = args[0]
                    originales["write_bytes"](self, datos[: len(datos) // 2])
                raise Corte(f"corte en la escritura {n} ({nombre} {self.name})")
            return originales[nombre](self, *args, **kwargs)

        return nueva

    for nombre in originales:
        monkeypatch.setattr(Path, nombre, envolver(nombre))
    return lambda: cuenta[0]


def _escrituras_de(tarea: Callable[[], None], monkeypatch: pytest.MonkeyPatch) -> int:
    contar = _cortar_en(monkeypatch, 10**9)
    tarea()
    monkeypatch.undo()
    return contar()


def _preparar(juego: Path) -> Path:
    archivo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    archivo.parent.mkdir(parents=True)
    archivo.write_bytes(b"ORIGINAL en ingles")
    return archivo


def _iterar_cortes(juego: Path, monkeypatch: pytest.MonkeyPatch, previas: int) -> Iterator[tuple[int, Path]]:
    """Para cada punto de escritura de un `escribir`, deja la instancia cortada ahí y la entrega para revisarla."""
    base = juego.parent

    def nueva_instancia(i: int) -> tuple[Path, Path]:
        destino = base / f"corte{i}"
        destino.mkdir()
        archivo = _preparar(destino)
        for k in range(previas):  # traducciones completas anteriores
            Respaldo(destino).escribir(archivo, f"TRADUCIDO {k}".encode())
        return destino, archivo

    sonda, archivo_sonda = nueva_instancia(0)
    total = _escrituras_de(lambda: Respaldo(sonda).escribir(archivo_sonda, b"TRADUCIDO nuevo"), monkeypatch)
    assert total >= 1
    for n in range(1, total + 1):
        destino, archivo = nueva_instancia(n)
        _cortar_en(monkeypatch, n)
        with pytest.raises(Corte):
            Respaldo(destino).escribir(archivo, b"TRADUCIDO nuevo")
        monkeypatch.undo()
        yield n, archivo


@pytest.mark.parametrize("previas", [0, 1, 2])
def test_corte_en_cada_escritura_y_luego_restaurar_devuelve_el_original(
    juego: Path, monkeypatch: pytest.MonkeyPatch, previas: int
) -> None:
    for n, archivo in _iterar_cortes(juego, monkeypatch, previas):
        destino = archivo.parents[4]
        Respaldo(destino).restaurar()
        assert archivo.read_bytes() == b"ORIGINAL en ingles", f"corte en la escritura {n}"


@pytest.mark.parametrize("previas", [0, 1, 2])
def test_corte_en_cada_escritura_y_luego_reanudar_conserva_el_original(
    juego: Path, monkeypatch: pytest.MonkeyPatch, previas: int
) -> None:
    for n, archivo in _iterar_cortes(juego, monkeypatch, previas):
        destino = archivo.parents[4]
        r = Respaldo(destino)  # la corrida siguiente (otro proceso) vuelve a leer el original y traduce
        assert r.original(archivo) == b"ORIGINAL en ingles", f"corte en la escritura {n}"
        r.escribir(archivo, b"TRADUCIDO de nuevo")
        assert archivo.read_bytes() == b"TRADUCIDO de nuevo"
        Respaldo(destino).restaurar()
        assert archivo.read_bytes() == b"ORIGINAL en ingles", f"corte en la escritura {n}"


def test_registro_corrupto_no_hace_perder_el_original_si_la_copia_sigue(juego: Path) -> None:
    """Documenta el límite del diseño: sin registro, lo traducido pasa por original (ver H-003 del informe)."""
    archivo = juego / "kubejs" / "a.js"
    archivo.parent.mkdir()
    archivo.write_bytes(b"ORIGINAL")
    Respaldo(juego).escribir(archivo, b"TRADUCIDO")
    (juego / "traductor_es" / "registro.json").write_bytes(b"\x00\x00basura")
    # La copia del original sigue en su sitio aunque el registro se dañó
    assert (juego / "traductor_es" / "respaldo" / "kubejs" / "a.js").read_bytes() == b"ORIGINAL"


def test_kit_de_servidor_no_mete_archivos_de_fuera_con_un_registro_hostil(juego: Path) -> None:
    from traductor_es.salida.exportar import exportar_kit_servidor

    secreto = juego.parent / "secreto.txt"
    secreto.write_bytes(b"datos personales")
    archivo = juego / "config" / "ftbquests" / "quests" / "a.snbt"
    archivo.parent.mkdir(parents=True)
    archivo.write_bytes(b"ORIGINAL")
    Respaldo(juego).escribir(archivo, b"TRADUCIDO")
    datos = json.loads((juego / "traductor_es" / "registro.json").read_text(encoding="utf-8"))
    datos["config/../../secreto.txt"] = {"existia": True, "escrito": "abc"}
    _registro(juego, datos)
    destino = juego.parent / "kit.zip"
    exportar_kit_servidor(juego, destino)
    import zipfile

    with zipfile.ZipFile(destino) as z:
        nombres = z.namelist()
        assert "config/ftbquests/quests/a.snbt" in nombres
        assert all(b"datos personales" not in z.read(n) for n in nombres)


def test_corte_antes_de_crear_un_archivo_nuevo_no_vacia_el_que_trae_despues_el_modpack(
    juego: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regresión encontrada por la verificación independiente del arreglo de H-002."""
    nuevo = juego / "config" / "ftbquests" / "lang" / "es_mx.snbt"
    nuevo.parent.mkdir(parents=True)
    _cortar_en(monkeypatch, 2)  # 1: el registro con la huella pendiente; 2: el archivo temporal
    with pytest.raises(Corte):
        Respaldo(juego).escribir(nuevo, b"TRADUCIDO", neutro=b"{}\n")
    monkeypatch.undo()
    for temporal in nuevo.parent.glob("*.tmp"):
        temporal.unlink()
    assert not nuevo.exists()
    nuevo.write_bytes(b"DEL MODPACK ACTUALIZADO")  # una actualización trae ese archivo
    Respaldo(juego).restaurar()
    assert nuevo.read_bytes() == b"DEL MODPACK ACTUALIZADO"
    assert Respaldo(juego).registrados() == []

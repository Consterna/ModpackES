"""El respaldo nunca pisa un original ni restaura a ciegas (decisión del usuario tras la auditoría, H-003 y H-013).

- Al renovar una copia (el modpack cambió), la vieja se aparta en `traductor_es/anteriores/`.
- Si `registro.json` se daña o se borra, se usa su copia (`registro.copia.json`).
- Restaurar no sobrescribe un archivo que cambió después de traducir: lo deja y avisa.
- Nada se escribe a través de una unión que salga de la instancia (H-012) y no quedan temporales (H-014).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from traductor_es.salida.copias import ANTERIORES, CARPETA, Respaldo


@pytest.fixture
def juego(tmp_path: Path) -> Path:
    raiz = tmp_path / "instancia" / "minecraft"
    raiz.mkdir(parents=True)
    return raiz


def _archivo(juego: Path, contenido: bytes = b"ORIGINAL v1") -> Path:
    ruta = juego / "config" / "ftbquests" / "quests" / "a.snbt"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


def _anteriores(juego: Path) -> list[bytes]:
    carpeta = juego / CARPETA / ANTERIORES
    return sorted(p.read_bytes() for p in carpeta.rglob("*") if p.is_file()) if carpeta.is_dir() else []


def test_restaurar_no_pisa_lo_que_actualizo_el_modpack_y_avisa(juego: Path) -> None:
    ruta = _archivo(juego)
    Respaldo(juego).escribir(ruta, b"TRADUCIDO")
    ruta.write_bytes(b"ORIGINAL v2 del modpack actualizado")
    r = Respaldo(juego)
    assert r.restaurar() == []
    assert ruta.read_bytes() == b"ORIGINAL v2 del modpack actualizado"
    assert r.cambiados == ["config/ftbquests/quests/a.snbt"]
    aviso = r.aviso_cambiados()
    assert aviso is not None and "cambiaron después de traducirlos" in aviso and "a.snbt" in aviso
    # Ya no queda registrado: una traducción nueva toma lo de ahora como original
    assert Respaldo(juego).registrados() == []


def test_restaurar_no_pisa_una_edicion_a_mano_y_el_proceso_lo_avisa(juego: Path) -> None:
    from traductor_es.motores.simulador import Simulador
    from traductor_es.nucleo.memoria import Memoria
    from traductor_es.proceso import Proceso

    from . import fabrica

    instancia = fabrica.prism(juego.parent.parent / "otra", "1.20.1")
    capitulo = instancia / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text('{ title: "Wrench" description: ["Craft your first tool."] }', encoding="utf-8")
    with Memoria(":memory:") as m:
        with Proceso(instancia, Simulador(), memoria=m) as p:
            p.ejecutar()
        capitulo.write_text('{ title: "Llave" description: ["Mi versión a mano."] }', encoding="utf-8")
        avisos: list[str] = []
        with Proceso(instancia, Simulador(), memoria=m, registro=avisos.append) as p:
            p.restaurar()
    assert "Mi versión a mano." in capitulo.read_text(encoding="utf-8")
    assert any("No restauré 1 archivos" in a for a in avisos)


def test_restaurar_recrea_lo_que_el_usuario_borro(juego: Path) -> None:
    ruta = _archivo(juego)
    Respaldo(juego).escribir(ruta, b"TRADUCIDO")
    ruta.unlink()
    assert Respaldo(juego).restaurar() == [ruta]
    assert ruta.read_bytes() == b"ORIGINAL v1"


def test_renovar_la_copia_aparta_la_vieja_en_anteriores(juego: Path) -> None:
    ruta = _archivo(juego)
    Respaldo(juego).escribir(ruta, b"TRADUCIDO v1")
    ruta.write_bytes(b"ORIGINAL v2")  # el modpack se actualizó
    Respaldo(juego).escribir(ruta, b"TRADUCIDO v2")
    assert (juego / CARPETA / "respaldo" / "config" / "ftbquests" / "quests" / "a.snbt").read_bytes() == b"ORIGINAL v2"
    assert _anteriores(juego) == [b"ORIGINAL v1"]
    Respaldo(juego).restaurar()
    assert ruta.read_bytes() == b"ORIGINAL v2"


@pytest.mark.parametrize("como", ["danado", "borrado"])
def test_registro_danado_o_borrado_se_recupera_con_su_copia(juego: Path, como: str) -> None:
    ruta = _archivo(juego)
    Respaldo(juego).escribir(ruta, b"TRADUCIDO 1")
    Respaldo(juego).escribir(ruta, b"TRADUCIDO 2")
    registro = juego / CARPETA / "registro.json"
    if como == "danado":
        registro.write_bytes(b"\x00basura")
    else:
        registro.unlink()
    r = Respaldo(juego)
    assert r.original(ruta) == b"ORIGINAL v1"
    r.escribir(ruta, b"TRADUCIDO 3")
    Respaldo(juego).restaurar()
    assert ruta.read_bytes() == b"ORIGINAL v1"


@pytest.mark.parametrize("como", ["danado", "borrado"])
def test_sin_ningun_registro_el_original_no_se_pierde(juego: Path, como: str) -> None:
    """Sin registro ni su copia no se puede saber qué es original, pero el inglés queda en anteriores."""
    ruta = _archivo(juego)
    Respaldo(juego).escribir(ruta, b"TRADUCIDO")
    (juego / CARPETA / "registro.copia.json").unlink()
    registro = juego / CARPETA / "registro.json"
    if como == "danado":
        registro.write_bytes(b"{")
    else:
        registro.unlink()
    Respaldo(juego).escribir(ruta, b"TRADUCIDO otra vez")
    assert b"ORIGINAL v1" in _anteriores(juego)


def test_no_quedan_temporales_tras_restaurar_una_escritura_cortada(juego: Path) -> None:
    ruta = _archivo(juego)
    Respaldo(juego).escribir(ruta, b"TRADUCIDO")
    sobrante = ruta.with_name(ruta.name + ".traductor.tmp")
    sobrante.write_bytes(b"TRADU")  # lo que deja un corte a mitad de una escritura
    Respaldo(juego).restaurar()
    assert not sobrante.exists() and ruta.read_bytes() == b"ORIGINAL v1"


def _union(enlace: Path, destino: Path) -> None:
    if os.name != "nt":
        pytest.skip("las uniones (junctions) solo existen en Windows")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(destino)], check=True, capture_output=True)


@pytest.mark.parametrize("cual", [CARPETA, f"{CARPETA}/respaldo"])
def test_union_que_apunta_afuera_no_recibe_copias_ni_registro(juego: Path, cual: str) -> None:
    afuera = juego.parent.parent / "afuera"
    afuera.mkdir()
    enlace = juego / cual
    enlace.parent.mkdir(parents=True, exist_ok=True)
    _union(enlace, afuera)
    ruta = _archivo(juego)
    try:
        with pytest.raises(OSError, match="fuera de la instancia"):
            Respaldo(juego).escribir(ruta, b"TRADUCIDO")
        assert list(afuera.rglob("*")) == []
        assert ruta.read_bytes() == b"ORIGINAL v1"
    finally:
        enlace.rmdir()  # quita solo la unión, no lo que hay detrás


def test_registro_vaciado_a_mano_se_recupera_con_su_copia(juego: Path) -> None:
    """Variante que encontró la verificación independiente: un `{}` válido no debe tapar la copia."""
    ruta = _archivo(juego)
    Respaldo(juego).escribir(ruta, b"TRADUCIDO 1")
    Respaldo(juego).escribir(ruta, b"TRADUCIDO 2")
    (juego / CARPETA / "registro.json").write_text("{}", encoding="utf-8")
    assert Respaldo(juego).original(ruta) == b"ORIGINAL v1"
    Respaldo(juego).restaurar()
    assert ruta.read_bytes() == b"ORIGINAL v1"

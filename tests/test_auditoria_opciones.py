"""options.txt: solo cambia lo que la app pide (pack y idioma); lo demás queda byte a byte."""

from __future__ import annotations

from pathlib import Path

import pytest

from traductor_es.salida.opciones import activar


def _opciones(tmp_path: Path, texto: str) -> Path:
    (tmp_path / "options.txt").write_bytes(texto.encode("utf-8"))
    return tmp_path


@pytest.mark.parametrize("separador", ["\u2028", "\u2029", "\x85", "\x0b", "\x0c", "\x1c"])
def test_options_no_parte_lineas_en_separadores_que_minecraft_no_usa(tmp_path: Path, separador: str) -> None:
    juego = _opciones(tmp_path, f'lastServer:mi{separador}servidor\nlang:en_us\nresourcePacks:["vanilla"]\n')
    activar(juego, "Traduccion_ES", "es_mx", con_prefijo=True)
    lineas = (juego / "options.txt").read_bytes().decode("utf-8").split("\n")
    assert lineas[0] == f"lastServer:mi{separador}servidor"
    assert lineas[1:] == ["lang:es_mx", 'resourcePacks:["vanilla","file/Traduccion_ES"]', ""]


def test_options_conserva_los_saltos_de_las_lineas_que_no_cambia(tmp_path: Path) -> None:
    juego = _opciones(tmp_path, 'version:3465\r\nfov:0.0\nlang:en_us\r\nresourcePacks:["vanilla"]\r\n')
    activar(juego, "Traduccion_ES", "es_mx", con_prefijo=True)
    assert (juego / "options.txt").read_bytes() == (
        b'version:3465\r\nfov:0.0\nlang:es_mx\r\nresourcePacks:["vanilla","file/Traduccion_ES"]\r\n'
    )


def test_options_sin_salto_final_y_con_lineas_nuevas(tmp_path: Path) -> None:
    juego = _opciones(tmp_path, "version:3465\r\nfov:0.0")
    activar(juego, "Traduccion_ES", "es_mx", con_prefijo=True)
    assert (juego / "options.txt").read_bytes() == (
        b'version:3465\r\nfov:0.0\r\nresourcePacks:["vanilla","file/Traduccion_ES"]\r\nlang:es_mx\r\n'
    )


def test_options_activar_dos_veces_es_activar_una(tmp_path: Path) -> None:
    juego = _opciones(tmp_path, 'version:3465\nlang:en_us\nresourcePacks:["vanilla","file/Otro"]\n')
    activar(juego, "Traduccion_ES", "es_mx", con_prefijo=True)
    una = (juego / "options.txt").read_bytes()
    assert activar(juego, "Traduccion_ES", "es_mx", con_prefijo=True) == []
    assert (juego / "options.txt").read_bytes() == una


def test_options_un_nombre_de_pack_no_puede_meter_lineas(tmp_path: Path) -> None:
    juego = _opciones(tmp_path, 'lang:en_us\nresourcePacks:["vanilla"]\n')
    activar(juego, "Pack\nlang:xx_yy", None, con_prefijo=True)
    texto = (juego / "options.txt").read_text(encoding="utf-8")
    assert texto.count("\n") == 2 and "lang:en_us" in texto

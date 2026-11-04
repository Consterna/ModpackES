"""Registro en archivo, errores no previstos y diagnóstico: nada de esto puede filtrar la clave."""

from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from traductor_es import __version__, configuracion, registro

#: Clave falsa con la forma de una de Google. Se arma en dos partes para que el escaneo de secretos de GitHub no
#: la confunda con una clave real filtrada.
CLAVE = "AIza" + "SyD-prueba-0123456789abcdefghijklmn"


@pytest.fixture(autouse=True)
def _registro_propio(tmp_path: Path) -> Iterator[Path]:
    ruta = registro.configurar(tmp_path / "datos")
    yield ruta
    registro.cerrar()


def _contenido(ruta: Path) -> str:
    for h in registro.LOGGER.handlers:
        h.flush()
    return ruta.read_text(encoding="utf-8")


def test_escribe_en_archivo_y_tapa_las_claves(_registro_propio: Path) -> None:
    registro.ocultar("mi-secreto-personal")
    registro.LOGGER.info("probando %s y %s y sk-abcdefghijklmnopqrstu", CLAVE, "mi-secreto-personal")
    texto = _contenido(_registro_propio)
    assert "probando" in texto
    assert CLAVE not in texto and "mi-secreto-personal" not in texto and "sk-abcdef" not in texto
    assert texto.count("[clave oculta]") == 3


def test_la_clave_leida_queda_oculta_aunque_aparezca_en_un_error(
    _registro_propio: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rara = "clave-sin-forma-conocida-123"
    monkeypatch.setenv("GEMINI_API_KEY", rara)
    assert configuracion.leer_clave() == rara
    try:
        raise ValueError(f"la API rechazó {rara}")
    except ValueError:
        registro.LOGGER.exception("fallo")
    texto = _contenido(_registro_propio)
    assert rara not in texto and "ValueError" in texto


def test_configurar_dos_veces_no_duplica_y_cambia_de_archivo(tmp_path: Path, _registro_propio: Path) -> None:
    assert registro.configurar(tmp_path / "datos") == _registro_propio
    otra = registro.configurar(tmp_path / "otra")
    registro.LOGGER.info("al nuevo")
    assert sum(1 for h in registro.LOGGER.handlers if h.__class__.__name__ == "RotatingFileHandler") == 1
    assert "al nuevo" in _contenido(otra)
    actual = registro.ruta_actual()
    assert actual is not None and actual.resolve() == otra.resolve()


def test_diagnostico_sin_carpeta_personal_ni_clave(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    casa = tmp_path / "Usuarios" / "Fulano"
    monkeypatch.setenv("USERPROFILE", str(casa))  # Path.home() en Windows
    monkeypatch.setenv("HOME", str(casa))  # y en los demás sistemas
    registro.LOGGER.info("Instancia en %s con %s", casa / "instancias" / "FC4", CLAVE)
    texto = registro.diagnostico({"Instancia": str(casa / "instancias" / "FC4")})
    assert f"ModpackES {__version__}" in texto and "Sistema:" in texto and "PySide6" in texto
    assert str(casa) not in texto and "~" in texto
    # Regresión: la misma carpeta escrita con otras mayúsculas o con «/» también se tapa
    otra = registro.diagnostico({"a": str(casa).lower(), "b": str(casa).replace("\\", "/").upper()})
    assert "fulano" not in otra.lower()
    assert CLAVE not in texto and "Instancia en" in texto


def test_diagnostico_sin_registro_dice_vacio() -> None:
    registro.cerrar()
    assert "(vacío)" in registro.diagnostico()


def test_errores_no_previstos_se_anotan_y_avisan(_registro_propio: Path) -> None:
    avisos: list[str] = []
    antes, antes_hilo = sys.excepthook, threading.excepthook
    try:
        registro.instalar_manejadores(avisos.append)
        try:
            raise RuntimeError("se rompió algo")
        except RuntimeError as e:
            sys.excepthook(type(e), e, e.__traceback__)

        def romper() -> None:
            raise KeyError("en otro hilo")

        hilo = threading.Thread(target=romper)
        hilo.start()
        hilo.join()
    finally:
        sys.excepthook, threading.excepthook = antes, antes_hilo
    texto = _contenido(_registro_propio)
    assert "se rompió algo" in texto and "en otro hilo" in texto and "Traceback" in texto
    assert len(avisos) == 2 and str(registro.ruta_actual()) in avisos[0]

"""Escrituras de datos del usuario (glosario, preferencias) que no deben quedar a medias."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from traductor_es import configuracion


class Corte(Exception):
    pass


def _cortar_a_medias(monkeypatch: pytest.MonkeyPatch) -> None:
    """La próxima escritura de texto deja la mitad del archivo y falla (corte de luz, disco lleno)."""
    original: Callable[..., Any] = Path.write_text

    def a_medias(self: Path, datos: str, *args: Any, **kwargs: Any) -> int:
        original(self, datos[: len(datos) // 2], *args, **kwargs)
        raise Corte(self.name)

    monkeypatch.setattr(Path, "write_text", a_medias)


def test_corte_al_guardar_el_glosario_no_pierde_los_terminos_anteriores(monkeypatch: pytest.MonkeyPatch) -> None:
    configuracion.guardar_glosario_usuario({"Wrench": "Llave inglesa", "Gear": "Engranaje"})
    with monkeypatch.context() as m:
        _cortar_a_medias(m)
        with pytest.raises(Corte):
            configuracion.guardar_glosario_usuario({"Wrench": "Llave", "Gear": "Engranaje", "Nuevo": "Nuevo"})
    assert configuracion.leer_glosario_usuario() == {"Wrench": "Llave inglesa", "Gear": "Engranaje"}


def test_corte_al_guardar_preferencias_no_las_borra(monkeypatch: pytest.MonkeyPatch) -> None:
    configuracion.guardar_preferencias({"motor": "gemini", "dialecto": "es_ar"})
    with monkeypatch.context() as m:
        _cortar_a_medias(m)
        with pytest.raises(Corte):
            configuracion.guardar_preferencias({"motor": "openrouter", "dialecto": "es_ar"})
    assert configuracion.leer_preferencias() == {"motor": "gemini", "dialecto": "es_ar"}


def test_las_preferencias_nunca_guardan_la_clave() -> None:
    configuracion.guardar_preferencias({"motor": "gemini", "clave": "AIza" + "x" * 35})
    assert "clave" not in configuracion.leer_preferencias()
    assert "AIza" not in (configuracion.carpeta_datos() / "preferencias.json").read_text(encoding="utf-8")


def test_la_copia_se_baja_al_disco_y_reintenta_si_un_antivirus_la_tiene_tomada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Investigación `escritura_atomica_windows.md`: sin `fsync` un corte de luz podía dejar el archivo vacío, y un
    antivirus que lo tiene abierto un instante (WinError 32) hacía fallar la escritura sin reintentar."""
    from traductor_es.salida import copias

    sincronizados: list[int] = []
    original_fsync = copias.os.fsync

    def fsync(fd: int) -> None:
        sincronizados.append(fd)
        original_fsync(fd)

    def sin_esperar(_segundos: float) -> None:
        return None

    monkeypatch.setattr(copias.os, "fsync", fsync)
    monkeypatch.setattr(copias.time, "sleep", sin_esperar)
    original_replace = Path.replace
    intentos: list[int] = []

    def ocupado(self: Path, destino: Path) -> Path:
        intentos.append(1)
        if len(intentos) <= 2:
            error = PermissionError(13, "El proceso no tiene acceso al archivo")
            error.winerror = 32  # type: ignore[attr-defined]
            raise error
        return original_replace(self, destino)

    monkeypatch.setattr(Path, "replace", ocupado)
    ruta = tmp_path / "a.snbt"
    copias._escribir_entero(ruta, b"traducido")  # pyright: ignore[reportPrivateUsage]
    assert ruta.read_bytes() == b"traducido" and len(intentos) == 3 and sincronizados
    assert not (tmp_path / "a.snbt.traductor.tmp").exists()


def test_un_error_que_no_es_pasajero_no_se_reintenta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from traductor_es.salida import copias

    intentos: list[int] = []

    def lleno(self: Path, destino: Path) -> Path:
        intentos.append(1)
        raise OSError(28, "No queda espacio en el disco")

    monkeypatch.setattr(Path, "replace", lleno)
    with pytest.raises(OSError, match="espacio"):
        copias._escribir_entero(tmp_path / "a.snbt", b"x")  # pyright: ignore[reportPrivateUsage]
    assert intentos == [1] and not (tmp_path / "a.snbt.traductor.tmp").exists()

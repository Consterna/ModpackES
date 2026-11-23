"""Las DLL que el programa carga desde System32 antes de importar Qt (H-016, «DLL planting»)."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from traductor_es import dll_sistema

solo_windows = pytest.mark.skipif(sys.platform != "win32", reason="solo en Windows")


@solo_windows
def test_precarga_dwmapi_desde_system32() -> None:
    sistema = dll_sistema.carpeta_sistema()
    assert sistema is not None and (sistema / "kernel32.dll").is_file()
    assert dll_sistema.precargar() == [sistema / "dwmapi.dll"]
    cargada = dll_sistema.ruta_cargada("dwmapi.dll")
    assert cargada is not None and cargada.parent.resolve() == sistema.resolve()


_PEDIR_DWMAPI = """
import ctypes, sys
from traductor_es import dll_sistema
ctypes.windll.kernel32.SetDllDirectoryW(sys.argv[1])  # como la carpeta del .exe: Windows mira ahí antes que System32
if sys.argv[2] == "precargar":
    dll_sistema.precargar()
ctypes.WinDLL("dwmapi.dll")
print(dll_sistema.ruta_cargada("dwmapi.dll"))
"""


def _pedir_dwmapi(carpeta: Path, modo: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_PEDIR_DWMAPI), str(carpeta), modo],
        capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip


@solo_windows
def test_una_dwmapi_falsa_en_una_carpeta_que_se_busca_antes_no_se_carga(tmp_path: Path) -> None:
    (tmp_path / "dwmapi.dll").write_bytes(b"MZ\x00\x00\xde\xad\xbe\xef")
    sin_precarga = _pedir_dwmapi(tmp_path, "no")
    assert sin_precarga.returncode != 0 and "OSError" in sin_precarga.stderr  # control: sin precarga, se usa la falsa
    con_precarga = _pedir_dwmapi(tmp_path, "precargar")
    assert con_precarga.returncode == 0, con_precarga.stderr
    sistema = dll_sistema.carpeta_sistema()
    assert sistema is not None and Path(con_precarga.stdout.strip()).parent.resolve() == sistema.resolve()


def test_fuera_de_windows_no_hace_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert dll_sistema.carpeta_sistema() is None
    assert dll_sistema.precargar() == []
    assert dll_sistema.ruta_cargada("dwmapi.dll") is None

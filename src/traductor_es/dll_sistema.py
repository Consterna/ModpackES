"""DLL de Windows que el programa carga desde System32 antes de que nadie las pida por su nombre (CWE-427).

Windows busca una DLL que no está entre las «KnownDLLs» primero en la carpeta del `.exe`. `dwmapi.dll`, que pide
Qt al crear la ventana, es una de ellas: si alguien deja una falsa junto al programa, se cargaría esa. Cargarla
antes con su ruta completa lo evita, porque Windows reutiliza el módulo que ya tiene cargado con ese nombre.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

#: Las que se cargan antes de importar Qt.
DLLS = ("dwmapi.dll",)
_MAX_RUTA = 32768


def carpeta_sistema() -> Path | None:
    """La carpeta System32 de este Windows (None en otro sistema)."""
    if sys.platform != "win32":
        return None
    buffer = ctypes.create_unicode_buffer(_MAX_RUTA)
    largo = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, _MAX_RUTA)
    return Path(buffer.value) if 0 < largo < _MAX_RUTA else None


def precargar() -> list[Path]:
    """Carga cada DLL de `DLLS` desde System32 con su ruta completa. Devuelve las que cargó.

    Si una no se puede cargar, se sigue: el programa funciona igual y Windows la buscará como siempre.
    """
    carpeta = carpeta_sistema()
    if carpeta is None or sys.platform != "win32":
        return []
    cargadas: list[Path] = []
    for nombre in DLLS:
        ruta = carpeta / nombre
        try:
            ctypes.WinDLL(str(ruta))
        except OSError:
            continue
        cargadas.append(ruta)
    return cargadas


def ruta_cargada(nombre: str) -> Path | None:
    """De qué archivo cargó Windows esa DLL en este proceso (None si no está cargada o fuera de Windows)."""
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p  # HMODULE
    kernel32.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
    kernel32.GetModuleFileNameW.restype = ctypes.c_uint32
    modulo = kernel32.GetModuleHandleW(nombre)
    if not modulo:
        return None
    buffer = ctypes.create_unicode_buffer(_MAX_RUTA)
    largo = kernel32.GetModuleFileNameW(modulo, buffer, _MAX_RUTA)
    return Path(buffer.value) if 0 < largo < _MAX_RUTA else None

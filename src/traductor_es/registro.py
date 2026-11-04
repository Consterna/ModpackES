"""Registro en archivo para diagnosticar problemas: lo que muestra la ventana, los avisos y los errores.

Nunca guarda claves: el formateador tapa las que se registren con `ocultar()` y todo lo que tenga forma de
clave de API. El diagnóstico que se copia para un issue cambia además la carpeta del usuario por «~».
"""

from __future__ import annotations

import logging
import platform
import re
import sys
import threading
import traceback
from collections.abc import Callable, Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from . import NOMBRE, __version__

try:
    from PySide6 import __version__ as _version_qt
except ImportError:  # la línea de comandos puede funcionar sin Qt
    _version_qt = "no instalado"
VERSION_QT: str = _version_qt

LOGGER = logging.getLogger("modpackes")
ARCHIVO = "registro.log"
TAMANO_MAXIMO = 1_000_000  #: bytes por archivo; se guardan además 2 anteriores
_CON_FORMA_DE_CLAVE = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|\bsk-[A-Za-z0-9_\-]{16,}")
_secretos: set[str] = set()
_cerrojo = threading.Lock()


def ocultar(valor: str | None) -> None:
    """Agrega un valor que no debe aparecer nunca en el registro (por ejemplo, la clave guardada)."""
    if valor and len(valor.strip()) >= 8:
        with _cerrojo:
            _secretos.add(valor.strip())


def tapar(texto: str) -> str:
    with _cerrojo:
        secretos = sorted(_secretos, key=len, reverse=True)
    for s in secretos:
        texto = texto.replace(s, "[clave oculta]")
    return _CON_FORMA_DE_CLAVE.sub("[clave oculta]", texto)


class _Formato(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return tapar(super().format(record))


def _manejador_actual() -> RotatingFileHandler | None:
    return next((h for h in LOGGER.handlers if isinstance(h, RotatingFileHandler)), None)


def configurar(carpeta: Path) -> Path:
    """Escribe el registro en `carpeta/registro.log`. Se puede llamar varias veces; cambia de archivo si hace falta."""
    ruta = carpeta / ARCHIVO
    actual = _manejador_actual()
    if actual is not None and Path(actual.baseFilename).resolve() == ruta.resolve():
        return ruta
    if actual is not None:
        LOGGER.removeHandler(actual)
        actual.close()
    carpeta.mkdir(parents=True, exist_ok=True)
    manejador = RotatingFileHandler(ruta, maxBytes=TAMANO_MAXIMO, backupCount=2, encoding="utf-8", delay=True)
    manejador.setFormatter(_Formato("%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
    LOGGER.addHandler(manejador)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    return ruta


def ruta_actual() -> Path | None:
    actual = _manejador_actual()
    return Path(actual.baseFilename) if actual is not None else None


def cerrar() -> None:
    actual = _manejador_actual()
    if actual is not None:
        LOGGER.removeHandler(actual)
        actual.close()


def ultimas_lineas(n: int = 150) -> list[str]:
    ruta = ruta_actual()
    if ruta is None or not ruta.is_file():
        return []
    for h in LOGGER.handlers:
        h.flush()
    return ruta.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]


def _sin_carpeta_personal(texto: str) -> str:
    """Cambia la carpeta del usuario por «~», con barras de cualquier tipo y sin distinguir mayúsculas (Windows)."""
    casa = str(Path.home()).rstrip("\\/")
    if len(casa) < 3:
        return texto
    barra = r"[\\/]+"
    cuerpo = barra.join(re.escape(p) for p in re.split(barra, casa) if p)
    patron = (barra if casa.startswith(("/", "\\")) else "") + cuerpo
    return re.sub(patron, "~", texto, flags=re.IGNORECASE)


def diagnostico(extra: Mapping[str, str] | None = None, lineas: int = 150) -> str:
    """Texto para pegar en un issue: versiones, sistema, datos del caso y el final del registro."""
    partes = [
        f"{NOMBRE} {__version__}{' (ejecutable)' if getattr(sys, 'frozen', False) else ''}",
        f"Sistema: {platform.platform()}",
        f"Python {platform.python_version()} · PySide6 {VERSION_QT}",
        *(f"{k}: {v}" for k, v in (extra or {}).items()),
        "",
        f"Últimas líneas del registro ({ARCHIVO}):",
        *(ultimas_lineas(lineas) or ["(vacío)"]),
    ]
    return tapar(_sin_carpeta_personal("\n".join(partes)))


def instalar_manejadores(mostrar: Callable[[str], None] | None = None) -> None:
    """Los errores no previstos quedan en el registro y, si se puede, se avisan en vez de cerrar la app en silencio."""

    def avisar(tipo: type[BaseException], valor: BaseException, rastro: TracebackType | None) -> None:
        LOGGER.critical("Error no previsto:\n%s", "".join(traceback.format_exception(tipo, valor, rastro)))
        if mostrar is not None:
            donde = ruta_actual()
            mostrar(
                f"Ocurrió un error no previsto: {valor}\n\n"
                + (f"Quedó anotado en {donde}. Usa «Más ▸ Copiar diagnóstico» para reportarlo." if donde else "")
            )

    def en_hilo(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is not None:
            avisar(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = avisar
    threading.excepthook = en_hilo

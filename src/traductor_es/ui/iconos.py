"""Íconos de Lucide (licencia ISC, ver iconos/LICENSE.txt) teñidos con los colores del tema.

Los SVG traen `stroke="currentColor"`: se cambia por el color pedido y se dibuja en dos tamaños para que se
vean nítidos con la pantalla al 100 % y al 200 %.
"""

from __future__ import annotations

from functools import cache, lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import tema

CARPETA = Path(__file__).with_name("iconos")


@cache
def _svg(nombre: str) -> bytes:
    ruta = CARPETA / f"{nombre}.svg"
    if not ruta.is_file():
        raise ValueError(f"No existe el ícono «{nombre}» en {CARPETA}")
    return ruta.read_bytes()


def disponibles() -> list[str]:
    return sorted(p.stem for p in CARPETA.glob("*.svg"))


def pixmap(nombre: str, color: str, tam: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg(nombre).replace(b"currentColor", color.encode("ascii"))))
    imagen = QPixmap(tam, tam)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(pintor, QRectF(0, 0, tam, tam))
    pintor.end()
    return imagen


def icono(nombre: str, color: str | None = None, tam: int = 18) -> QIcon:
    """Ícono teñido; sin color usa el del texto del tema en curso."""
    return _icono(nombre, color or tema.actual().texto, tam)


@lru_cache(maxsize=512)
def _icono(nombre: str, tinta: str, tam: int) -> QIcon:
    """Los pasos y las tarjetas se repintan a cada cambio de opción: el mismo ícono no se vuelve a dibujar."""
    resultado = QIcon()
    for escala in (1, 2):
        resultado.addPixmap(pixmap(nombre, tinta, tam * escala))
    return resultado

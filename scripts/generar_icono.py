"""Dibuja el ícono de la app (un bloque de pasto de 16x16 con «ES») en src/traductor_es/ui/icono.png.

Uso:  uv run python scripts/generar_icono.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "src" / "traductor_es" / "ui" / "icono.png"

PASTO = ["#5da130", "#4a8a24", "#6bbf3a"]
TIERRA = ["#8b5a2b", "#7a4e24", "#9c6b3c", "#6b4220"]
LETRAS = {
    "E": ["XXXX", "X...", "XXX.", "X...", "XXXX"],
    "S": [".XXX", "X...", ".XX.", "...X", "XXX."],
}


def dibujar() -> QImage:
    azar = random.Random(26)  # siempre el mismo dibujo
    pixeles = QImage(16, 16, QImage.Format.Format_ARGB32)
    for y in range(16):
        for x in range(16):
            # el pasto cubre las 3 primeras filas y gotea en la cuarta y quinta
            es_pasto = y < 3 or (y == 3 and x % 3 != 1) or (y == 4 and x % 5 == 0)
            pixeles.setPixelColor(x, y, QColor(azar.choice(PASTO if es_pasto else TIERRA)))
    for i, letra in enumerate("ES"):
        for fila, patron in enumerate(LETRAS[letra]):
            for col, marca in enumerate(patron):
                if marca == "X":
                    x, y = 3 + i * 6 + col, 7 + fila
                    pixeles.setPixelColor(x + 1, y + 1, QColor("#3b2412"))  # sombra como el texto del juego
    for i, letra in enumerate("ES"):
        for fila, patron in enumerate(LETRAS[letra]):
            for col, marca in enumerate(patron):
                if marca == "X":
                    pixeles.setPixelColor(3 + i * 6 + col, 7 + fila, QColor("#ffffff"))
    return pixeles.scaled(256, 256, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)


def main() -> int:
    if not dibujar().save(str(DESTINO)):
        raise SystemExit(f"No pude guardar {DESTINO}")
    print(DESTINO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""La bienvenida de la primera vez: los tres pasos en una tarjeta, sin cuadros que interrumpan."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .componentes import Tarjeta, etiqueta, icono_en, icono_en_boton

PASOS = [
    ("sparkles", "Elige el motor", "Gemini (con una clave gratuita) o un modelo en tu PC, gratis."),
    ("search", "Analiza gratis", "Cuenta qué hay para traducir y cuánto costaría, sin cambiar nada."),
    ("languages", "Traduce", "Lo traducido se guarda en una memoria: no se paga dos veces por lo mismo."),
]


class TarjetaBienvenida(Tarjeta):
    configurar = Signal()
    cerrada = Signal()

    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(padre=padre)
        self.fijar_activa(True)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(18, 14, 18, 14)
        capa.setSpacing(10)
        capa.addWidget(etiqueta("Te damos la bienvenida a ModpackES", "subtitulo"))
        capa.addWidget(etiqueta("Traduce tu modpack al español en tres pasos:", "tenue"))
        fila = QHBoxLayout()
        fila.setSpacing(18)
        for nombre_icono, titulo, texto in PASOS:
            columna = QVBoxLayout()
            columna.setSpacing(4)
            cabeza = QHBoxLayout()
            icono_ = QLabel()
            icono_en(icono_, nombre_icono, lambda p: p.acento, 18)
            cabeza.addWidget(icono_)
            cabeza.addWidget(etiqueta(titulo, "subtitulo"), 1)
            columna.addLayout(cabeza)
            columna.addWidget(etiqueta(texto, "tenue", ajustar=True))
            columna.addStretch(1)
            fila.addLayout(columna, 1)
        capa.addLayout(fila)
        botones = QHBoxLayout()
        self.b_configurar = QPushButton("Configurar el motor")
        self.b_configurar.setProperty("tipo", "primario")
        icono_en_boton(self.b_configurar, "sparkles", lambda p: p.sobre_acento)
        self.b_configurar.clicked.connect(self.configurar.emit)
        self.b_entendido = QPushButton("Entendido")
        self.b_entendido.setProperty("tipo", "plano")
        self.b_entendido.clicked.connect(self._cerrar)
        botones.addWidget(self.b_configurar)
        botones.addWidget(self.b_entendido)
        botones.addStretch(1)
        capa.addLayout(botones)
        self.setAccessibleName("Bienvenida: elige el motor, analiza gratis y traduce")

    def _cerrar(self) -> None:
        self.setVisible(False)
        self.cerrada.emit()

"""El cuadro «Qué queda en inglés»: el informe por categorías, con un botón para guardarlo."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from .componentes import etiqueta


class DialogoInforme(QDialog):
    """Solo muestra el texto del informe; qué hace «Guardar…» lo decide la ventana."""

    def __init__(self, texto: str, guardar: Callable[[], None], padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setWindowTitle("Qué queda en inglés")
        self.setMinimumSize(720, 460)
        capa = QVBoxLayout(self)
        capa.setSpacing(12)
        capa.addWidget(etiqueta("Qué queda en inglés", "titulo"))
        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setPlainText(texto)
        capa.addWidget(self.texto, 1)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.b_guardar = QPushButton("Guardar…")
        self.b_guardar.clicked.connect(guardar)
        botones.addButton(self.b_guardar, QDialogButtonBox.ButtonRole.ActionRole)
        botones.rejected.connect(self.close)
        capa.addWidget(botones)

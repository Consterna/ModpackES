"""Ventana para buscar en la memoria de traducciones y corregir a mano lo que quedó mal."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import configuracion
from ..nucleo.memoria import Coincidencia, Memoria

_AMBITOS = {"ui": "Mods", "mision": "Misión", "libro": "Libro", "script": "Script", "*": "—"}


class DialogoCorrecciones(QDialog):
    def __init__(self, dialecto: str, memoria: Memoria | None = None, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setWindowTitle(f"Correcciones ({dialecto})")
        self.resize(980, 620)
        self.dialecto = dialecto
        self._propia = memoria is None
        self.memoria = memoria or Memoria(configuracion.ruta_memoria())
        self.resultados: list[Coincidencia] = []
        self._construir()
        self.buscar()

    def _construir(self) -> None:
        capa = QVBoxLayout(self)
        ayuda = QLabel(
            "Busca un texto en inglés o en español. Lo que corrijas manda sobre la memoria y el motor, en todas las "
            "misiones, libros y mods, y se aplica la próxima vez que pulses «Traducir» (sin costo). Con la búsqueda "
            "vacía se listan tus correcciones."
        )
        ayuda.setWordWrap(True)
        capa.addWidget(ayuda)
        fila = QHBoxLayout()
        self.e_buscar = QLineEdit()
        self.e_buscar.setPlaceholderText("Ej.: Iron Ingot, lingote…")
        self.e_buscar.returnPressed.connect(self.buscar)
        self.b_buscar = QPushButton("Buscar")
        self.b_buscar.clicked.connect(self.buscar)
        fila.addWidget(self.e_buscar, 1)
        fila.addWidget(self.b_buscar)
        capa.addLayout(fila)
        self.tabla = QTableWidget(0, 3)
        self.tabla.setHorizontalHeaderLabels(["Original", "Traducción", "Dónde"])
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        cabecera.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.currentCellChanged.connect(self._al_cambiar_fila)
        capa.addWidget(self.tabla, 3)
        capa.addWidget(QLabel("Original:"))
        self.t_original = QPlainTextEdit()
        self.t_original.setReadOnly(True)
        self.t_original.setMaximumHeight(80)
        capa.addWidget(self.t_original)
        capa.addWidget(QLabel("Traducción corregida (conserva los códigos como %s, §a o $(l)):"))
        self.t_correccion = QPlainTextEdit()
        self.t_correccion.setMaximumHeight(100)
        capa.addWidget(self.t_correccion)
        botones = QHBoxLayout()
        self.estado = QLabel()
        self.estado.setWordWrap(True)
        self.b_guardar = QPushButton("Guardar corrección")
        self.b_guardar.clicked.connect(self.guardar)
        self.b_quitar = QPushButton("Quitar corrección")
        self.b_quitar.clicked.connect(self.quitar)
        b_cerrar = QPushButton("Cerrar")
        b_cerrar.clicked.connect(self.accept)
        botones.addWidget(self.estado, 1)
        for b in (self.b_guardar, self.b_quitar, b_cerrar):
            botones.addWidget(b)
        capa.addLayout(botones)
        self._habilitar(None)

    # ------------------------------------------------------------------ acciones
    def buscar(self) -> None:
        self.resultados = self.memoria.buscar(self.e_buscar.text(), self.dialecto)
        self.tabla.setRowCount(len(self.resultados))
        for fila, c in enumerate(self.resultados):
            valores = [c.origen, ("★ " if c.corregida else "") + c.traduccion, _AMBITOS.get(c.ambito, c.ambito)]
            for col, v in enumerate(valores):
                item = QTableWidgetItem(v.replace("\n", " ⏎ "))
                item.setToolTip(v)
                self.tabla.setItem(fila, col, item)
        self.estado.setText(f"{len(self.resultados)} resultados." if self.resultados else "Sin resultados.")
        self.t_original.clear()
        self.t_correccion.clear()
        self._habilitar(None)

    def _al_cambiar_fila(self, fila: int, _columna: int, _fila_anterior: int, _columna_anterior: int) -> None:
        self.elegir(fila)

    def elegir(self, fila: int) -> None:
        c = self.resultados[fila] if 0 <= fila < len(self.resultados) else None
        self.t_original.setPlainText(c.origen if c else "")
        self.t_correccion.setPlainText(c.traduccion if c else "")
        self._habilitar(c)

    def _actual(self) -> Coincidencia | None:
        fila = self.tabla.currentRow()
        return self.resultados[fila] if 0 <= fila < len(self.resultados) else None

    def guardar(self) -> None:
        c = self._actual()
        if c is None:
            return
        try:
            self.memoria.corregir(c.origen, self.dialecto, self.t_correccion.toPlainText())
        except ValueError as e:
            self.estado.setText(f"✖ {e}")
            return
        self._refrescar(c, "Corrección guardada. Se aplica la próxima vez que pulses «Traducir».")

    def quitar(self) -> None:
        c = self._actual()
        if c is None:
            return
        self.memoria.quitar_correccion(c.origen, self.dialecto)
        self._refrescar(c, "Corrección quitada: vuelve la traducción de la memoria.")

    def _refrescar(self, c: Coincidencia, mensaje: str) -> None:
        fila = self.tabla.currentRow()
        self.buscar()
        nueva = next((i for i, r in enumerate(self.resultados) if (r.origen, r.ambito) == (c.origen, c.ambito)), -1)
        if nueva < 0 and 0 <= fila < len(self.resultados):
            nueva = fila
        if nueva >= 0:
            self.tabla.setCurrentCell(nueva, 0)
            self.elegir(nueva)  # Qt no avisa el cambio si la fila elegida es la misma de antes
        self.estado.setText(mensaje)

    def _habilitar(self, c: Coincidencia | None) -> None:
        self.b_guardar.setEnabled(c is not None)
        self.b_quitar.setEnabled(c is not None and c.corregida)
        self.t_correccion.setReadOnly(c is None)

    def done(self, resultado: int) -> None:
        if self._propia:
            self.memoria.cerrar()
        super().done(resultado)


def mostrar(padre: QWidget, dialecto: str) -> None:
    dialogo = DialogoCorrecciones(dialecto, padre=padre)
    dialogo.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialogo.open()

"""El diálogo «Motor de traducción»: motor, dirección, modelo y clave, con una guía corta para cada uno.

Solo arma los controles; qué hace cada uno lo decide la ventana (que es la que los usa al traducir).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..motores import fabrica
from .componentes import etiqueta, icono_en_boton

GUIAS = {
    fabrica.GEMINI: "Google Gemini traduce rápido y bien. Necesita una clave gratuita de aistudio.google.com/apikey; "
    "el análisis te dice cuánto costaría antes de gastar.",
    "openrouter": "Un solo servicio con modelos de muchas empresas. Pide una clave de openrouter.ai; el precio "
    "depende del modelo que elijas.",
    "deepseek": "Modelos de DeepSeek, baratos y buenos para traducir. Pide una clave en platform.deepseek.com.",
    "lmstudio": "Traduce gratis con un modelo en tu PC. Abre LM Studio, carga un modelo y activa su servidor local.",
    "ollama": "Traduce gratis con un modelo en tu PC. Instala Ollama y descarga un modelo "
    "(p. ej. «ollama pull qwen3:8b»).",
    "personalizado": "Cualquier servidor compatible con la API de OpenAI: escribe su dirección y, si la pide, "
    "la clave.",
}


class DialogoMotor(QDialog):
    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setWindowTitle("Motor de traducción")
        self.setMinimumWidth(560)
        capa = QVBoxLayout(self)
        capa.setSpacing(12)
        capa.addWidget(etiqueta("Motor de traducción", "titulo"))
        self.guia: QLabel = etiqueta("", "tenue", ajustar=True)
        capa.addWidget(self.guia)
        self.formulario = QFormLayout()
        self.formulario.setVerticalSpacing(10)
        self.c_motor = QComboBox()
        for motor_id, nombre in fabrica.MOTORES.items():
            self.c_motor.addItem(nombre, motor_id)
        self.formulario.addRow("Motor:", self.c_motor)
        self.e_direccion = QLineEdit()
        self.e_direccion.setPlaceholderText("http://localhost:8080/v1")
        self.formulario.addRow("Dirección:", self.e_direccion)
        self.c_modelo = QComboBox()
        self.c_modelo.setEditable(True)
        self.formulario.addRow("Modelo:", self.c_modelo)
        clave = QHBoxLayout()
        self.etiqueta_clave = QLabel()
        self.b_clave = QPushButton("Guardar clave…")
        icono_en_boton(self.b_clave, "key-round")
        clave.addWidget(self.etiqueta_clave, 1)
        clave.addWidget(self.b_clave)
        self.formulario.addRow("Clave:", clave)
        capa.addLayout(self.formulario)
        self.b_probar = QPushButton("Probar conexión")
        self.b_probar.setToolTip("Comprueba la clave y la conexión, y carga la lista de modelos")
        icono_en_boton(self.b_probar, "plug")
        self.resultado: QLabel = etiqueta("", "tenue", ajustar=True)
        fila = QHBoxLayout()
        fila.addWidget(self.b_probar)
        fila.addWidget(self.resultado, 1)
        capa.addLayout(fila)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botones.rejected.connect(self.reject)
        listo = botones.button(QDialogButtonBox.StandardButton.Close)
        listo.setText("Listo")
        listo.setProperty("tipo", "primario")
        capa.addWidget(botones)

    def mostrar_guia(self, motor: str) -> None:
        self.guia.setText(GUIAS.get(motor, ""))

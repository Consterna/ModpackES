"""Ventana principal: elegir instancia, analizar gratis, traducir, restaurar y exportar."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import AUTOR, NOMBRE, REPOSITORIO, __version__, actualizaciones, configuracion, registro
from ..actualizaciones import Novedad
from ..fuentes.instancia import resolver_carpeta_juego
from ..fuentes.lanzadores import InstanciaEncontrada, buscar
from ..motores import fabrica
from ..motores.base import Cancelado, ErrorFatal, Motor
from ..motores.compatible import Compatible
from ..motores.gemini import MODELO_POR_DEFECTO, PRECIOS
from ..motores.simulador import Simulador
from ..nucleo.traductor import LARGO_CONTEXTO
from ..proceso import GRUPOS, Informe, Proceso
from ..salida import exportar
from . import correcciones

#: (motor, clave, modelo, dirección) → motor listo para traducir
FabricaMotor = Callable[[str, str | None, str, str], Motor]
NOMBRES_GRUPOS = {
    "mods": "Mods (objetos, bloques, menús)",
    "libros": "Libros guía",
    "misiones": "Misiones",
    "scripts": "Scripts de KubeJS",
}


def _diccionario(valor: object) -> dict[str, str]:
    """Un diccionario de texto leído de las preferencias (vacío si el archivo tenía otra cosa)."""
    if not isinstance(valor, dict):
        return {}
    return {str(k): str(v) for k, v in cast(dict[object, object], valor).items()}


class Consulta(QObject):
    """Una consulta corta a Google (p. ej. listar modelos) sin congelar la ventana."""

    listo = Signal(list)
    fallo = Signal(str)

    def __init__(self, funcion: Callable[[], list[str]]) -> None:
        super().__init__()
        self.funcion = funcion

    @Slot()
    def ejecutar(self) -> None:
        try:
            self.listo.emit(self.funcion())
        except (ErrorFatal, OSError) as e:
            self.fallo.emit(str(e))
        except Exception as e:  # un error no previsto no puede dejar el botón bloqueado
            registro.LOGGER.exception("Error no previsto al consultar a Google")
            self.fallo.emit(_no_previsto(e))


class Trabajador(QObject):
    """Corre una acción del proceso fuera del hilo de la ventana."""

    registro = Signal(str)
    progreso = Signal(int, int)
    terminado = Signal(object)
    fallo = Signal(str)

    def __init__(self, accion: str, carpeta: str, opciones: dict[str, Any], motor: Motor, cancelar: threading.Event):
        super().__init__()
        self.accion, self.carpeta, self.opciones, self.motor, self.cancelar = accion, carpeta, opciones, motor, cancelar

    @Slot()
    def ejecutar(self) -> None:
        try:
            with Proceso(
                self.carpeta,
                self.motor,
                self.opciones["dialecto"],
                self.opciones["grupos"],
                registro=self.registro.emit,
                progreso=self.progreso.emit,
                cancelar=self.cancelar,
                hilos=self.opciones["hilos"],
                usar_lotes=self.opciones["lotes"],
                contexto=self.opciones["contexto"],
                revisar=self.opciones["revisar"],
            ) as p:
                self.registro.emit(f"Minecraft {p.instancia.version} · {p.instancia.loader or '¿loader?'}")
                if self.accion == "analizar":
                    resultado: object = p.analizar()
                elif self.accion == "traducir":
                    resultado = p.ejecutar(activar=self.opciones["activar"], poner_idioma=self.opciones["idioma"])
                else:
                    resultado = p.restaurar()
            self.terminado.emit(resultado)
        except Cancelado:
            self.fallo.emit("Cancelado. Lo traducido hasta ahora quedó guardado en la memoria.")
        except (ErrorFatal, ValueError, OSError) as e:
            self.fallo.emit(str(e))
        except Exception as e:  # sin esto la ventana quedaría en «Trabajando…» con los botones bloqueados
            registro.LOGGER.exception("Error no previsto en «%s»", self.accion)
            self.fallo.emit(_no_previsto(e))


def _no_previsto(e: Exception) -> str:
    donde = registro.ruta_actual()
    nota = f"\n\nQuedó anotado en {donde}. Pulsa «Copiar diagnóstico» para reportarlo." if donde else ""
    return f"Error no previsto: {type(e).__name__}: {e}{nota}"


class Ventana(QMainWindow):
    def __init__(
        self,
        buscar_instancias: Callable[[], list[InstanciaEncontrada]] = buscar,
        fabrica_motor: FabricaMotor | None = None,
        buscar_novedad: Callable[[], Novedad | None] | None = None,
        avisar_version: bool = True,
    ) -> None:
        """`buscar_novedad` reemplaza la consulta a GitHub (pruebas); `avisar_version=False` no consulta nada."""
        super().__init__()
        self.setWindowTitle(f"{NOMBRE} {__version__} · Traductor de modpacks al español")
        self.resize(1100, 800)
        self._buscar_instancias = buscar_instancias
        self._fabrica_motor: FabricaMotor = fabrica_motor or fabrica.crear
        self._hilo: QThread | None = None
        self._accion = ""
        self._sondeo: QThread | None = None
        self._consulta: Consulta | None = None
        self._trabajador: Trabajador | None = None
        self._cancelar = threading.Event()
        self.ultimo_informe: Informe | None = None
        self._preferencias: dict[str, Any] = configuracion.leer_preferencias()
        self._motor_anterior: str | None = None
        self._construir()
        self.actualizar_instancias()
        self._actualizar_estado_clave()
        self._hilo_novedad: QThread | None = None
        self._consulta_novedad: Consulta | None = None
        por_defecto = actualizaciones.buscar if avisar_version and not self._es_prueba() else None
        funcion = buscar_novedad or por_defecto
        if funcion is not None and self.c_avisar.isChecked():
            self._buscar_novedad(funcion)

    # ------------------------------------------------------------------ construcción
    def _construir(self) -> None:
        izquierda = QWidget()
        capa_izq = QVBoxLayout(izquierda)
        capa_izq.addWidget(QLabel("<b>Instancias encontradas</b>"))
        self.lista = QListWidget()
        self.lista.currentItemChanged.connect(self._al_elegir)
        capa_izq.addWidget(self.lista)
        botones_izq = QHBoxLayout()
        self.b_carpeta = QPushButton("Elegir carpeta…")
        self.b_carpeta.clicked.connect(self._elegir_carpeta)
        self.b_actualizar = QPushButton("Actualizar")
        self.b_actualizar.clicked.connect(self.actualizar_instancias)
        botones_izq.addWidget(self.b_carpeta)
        botones_izq.addWidget(self.b_actualizar)
        capa_izq.addLayout(botones_izq)

        derecha = QWidget()
        capa = QVBoxLayout(derecha)
        self.etiqueta_carpeta = QLabel("Elige una instancia de la lista.")
        self.etiqueta_carpeta.setWordWrap(True)
        self.etiqueta_carpeta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        capa.addWidget(self.etiqueta_carpeta)

        opciones = QGroupBox("Opciones")
        formulario = QFormLayout(opciones)
        self.c_dialecto = QComboBox()
        self.c_dialecto.addItem("Español latinoamericano (es_mx)", "es_mx")
        self.c_dialecto.addItem("Español de España (es_es)", "es_es")
        self.c_dialecto.setCurrentIndex(max(0, self.c_dialecto.findData(self._preferencias.get("dialecto", "es_mx"))))
        formulario.addRow("Base de la traducción:", self.c_dialecto)
        grupos = QHBoxLayout()
        self.casillas: dict[str, QCheckBox] = {}
        elegidos = set(self._preferencias.get("grupos", GRUPOS))
        for g in GRUPOS:
            casilla = QCheckBox(NOMBRES_GRUPOS[g])
            casilla.setChecked(g in elegidos)
            self.casillas[g] = casilla
            grupos.addWidget(casilla)
        formulario.addRow("Qué traducir:", grupos)
        self.c_motor = QComboBox()
        for motor_id, nombre in fabrica.MOTORES.items():
            self.c_motor.addItem(nombre, motor_id)
        self.c_motor.setToolTip("Gemini necesita clave; LM Studio y Ollama traducen gratis con un modelo en tu PC")
        formulario.addRow("Motor:", self.c_motor)
        self.e_direccion = QLineEdit()
        self.e_direccion.setPlaceholderText("http://localhost:8080/v1")
        formulario.addRow("Dirección:", self.e_direccion)
        self.c_modelo = QComboBox()
        self.c_modelo.setEditable(True)
        formulario.addRow("Modelo:", self.c_modelo)
        self.c_lotes = QCheckBox("Por lotes: mitad de precio, pero puede tardar desde minutos hasta horas")
        self.c_lotes.setChecked(bool(self._preferencias.get("lotes", False)))
        formulario.addRow("", self.c_lotes)
        self.c_revisar = QCheckBox("Revisión automática de misiones y libros: rehace lo que tenga errores graves")
        self.c_revisar.setToolTip(
            "Otro pedido al motor juzga cada traducción nueva de misiones y libros; las que tengan errores graves se "
            "vuelven a traducir. El análisis muestra el costo con la revisión incluida."
        )
        self.c_revisar.setChecked(bool(self._preferencias.get("revisar", False)))
        formulario.addRow("", self.c_revisar)
        self.c_hilos = QSpinBox()
        self.c_hilos.setRange(1, 16)
        self.c_hilos.setValue(int(self._preferencias.get("hilos", 4)))
        formulario.addRow("Peticiones a la vez:", self.c_hilos)
        self.e_contexto = QLineEdit()
        self.e_contexto.setMaxLength(LARGO_CONTEXTO)
        self.e_contexto.setPlaceholderText("Opcional. Ej.: granja acogedora, tono amable; «Bells» es la moneda")
        self.e_contexto.setToolTip("Se le da al motor para el tono y los términos propios. Se guarda por instancia.")
        formulario.addRow("Ambientación:", self.e_contexto)
        self.c_activar = QCheckBox("Activar el pack y poner el juego en español (con Minecraft cerrado)")
        self.c_activar.setChecked(True)
        formulario.addRow("", self.c_activar)
        self.c_avisar = QCheckBox("Avisar al abrir si hay una versión nueva (consulta GitHub; no descarga nada)")
        self.c_avisar.setChecked(bool(self._preferencias.get("avisar_version", True)))
        self.c_avisar.toggled.connect(self._guardar_aviso)
        formulario.addRow("", self.c_avisar)
        clave = QHBoxLayout()
        self.etiqueta_clave = QLabel()
        self.b_clave = QPushButton("Guardar clave…")
        self.b_clave.clicked.connect(self._guardar_clave)
        self.b_probar = QPushButton("Probar conexión")
        self.b_probar.setToolTip("Comprueba la clave y la conexión, y carga la lista de modelos")
        self.b_probar.clicked.connect(self._probar_clave)
        clave.addWidget(self.etiqueta_clave, 1)
        clave.addWidget(self.b_clave)
        clave.addWidget(self.b_probar)
        formulario.addRow("Clave:", clave)
        capa.addWidget(opciones)
        self._formulario = formulario
        self.c_motor.setCurrentIndex(max(0, self.c_motor.findData(self._preferencias.get("motor", fabrica.GEMINI))))
        self.c_motor.currentIndexChanged.connect(self._al_cambiar_motor)
        self._al_cambiar_motor()

        acciones = QHBoxLayout()
        self.b_analizar = QPushButton("1. Analizar (gratis)")
        self.b_traducir = QPushButton("2. Traducir")
        self.b_cancelar = QPushButton("Cancelar")
        self.b_restaurar = QPushButton("Restaurar original")
        self.b_exportar = QPushButton("Exportar pack…")
        self.b_kit = QPushButton("Kit de servidor…")
        self.b_abrir = QPushButton("Abrir carpeta")
        self.b_correcciones = QPushButton("Correcciones…")
        self.b_correcciones.setToolTip("Buscar y corregir a mano traducciones de la memoria")
        self.b_cancelar.setEnabled(False)
        self.b_analizar.clicked.connect(lambda: self.lanzar("analizar"))
        self.b_traducir.clicked.connect(self._confirmar_traducir)
        self.b_cancelar.clicked.connect(self._cancelar.set)
        self.b_restaurar.clicked.connect(self._confirmar_restaurar)
        self.b_exportar.clicked.connect(lambda: self._exportar(kit=False))
        self.b_kit.clicked.connect(lambda: self._exportar(kit=True))
        self.b_abrir.clicked.connect(self._abrir_carpeta)
        self.b_correcciones.clicked.connect(self.abrir_correcciones)
        for b in (self.b_analizar, self.b_traducir, self.b_cancelar):
            acciones.addWidget(b)
        acciones.addStretch(1)
        for b in (self.b_correcciones, self.b_restaurar, self.b_exportar, self.b_kit, self.b_abrir):
            acciones.addWidget(b)
        capa.addLayout(acciones)

        self.barra = QProgressBar()
        self.estado = QLabel("Listo.")
        capa.addWidget(self.barra)
        capa.addWidget(self.estado)
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["Qué", "Detalle", "Textos", "Para el motor", "Resultado"])
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        capa.addWidget(self.tabla, 3)
        self.costo = QLabel()
        capa.addWidget(self.costo)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        capa.addWidget(self.log, 2)
        self.creditos = QLabel(
            f'{NOMBRE} {__version__} · © 2026 {AUTOR} · Licencia GPL-3.0 · <a href="{REPOSITORIO}">{REPOSITORIO}</a>'
        )
        self.creditos.setOpenExternalLinks(True)
        self.creditos.setAlignment(Qt.AlignmentFlag.AlignRight)
        pie = QHBoxLayout()
        self.b_diagnostico = QPushButton("Copiar diagnóstico")
        self.b_diagnostico.setToolTip("Copia versiones y el final del registro, para pegarlos al reportar un problema")
        self.b_diagnostico.clicked.connect(self.copiar_diagnostico)
        self.b_registro = QPushButton("Abrir registro")
        self.b_registro.clicked.connect(self._abrir_registro)
        self.novedad = QLabel()
        self.novedad.setOpenExternalLinks(True)
        self.novedad.setVisible(False)
        pie.addWidget(self.b_diagnostico)
        pie.addWidget(self.b_registro)
        pie.addWidget(self.novedad)
        pie.addWidget(self.creditos, 1)
        capa.addLayout(pie)

        divisor = QSplitter()
        divisor.addWidget(izquierda)
        divisor.addWidget(derecha)
        divisor.setStretchFactor(1, 3)
        divisor.setSizes([340, 840])  # que se lean los nombres de las instancias
        self.setCentralWidget(divisor)

    # ------------------------------------------------------------------ instancias
    def actualizar_instancias(self) -> None:
        self.lista.clear()
        for e in self._buscar_instancias():
            item = QListWidgetItem(f"{e.lanzador}: {e.nombre}")
            item.setData(Qt.ItemDataRole.UserRole, str(e.juego))
            item.setToolTip(str(e.juego))
            self.lista.addItem(item)
        ultima = self._preferencias.get("carpeta")
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == ultima:
                self.lista.setCurrentRow(i)

    def carpeta(self) -> str | None:
        item = self.lista.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _al_elegir(self, actual: QListWidgetItem | None, _anterior: QListWidgetItem | None) -> None:
        # Lo analizado era de otra instancia: no se muestra ni se usa para estimar el costo
        self.ultimo_informe = None
        self.tabla.setRowCount(0)
        self.costo.setText("")
        if actual is not None:
            self.etiqueta_carpeta.setText(f"<b>{actual.text()}</b><br>{actual.data(Qt.ItemDataRole.UserRole)}")
            self.e_contexto.setText(self._contexto_de(str(actual.data(Qt.ItemDataRole.UserRole))))

    def _contexto_de(self, carpeta: str) -> str:
        return _diccionario(self._preferencias.get("contextos")).get(carpeta, "")

    def _elegir_carpeta(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(self, "Carpeta de la instancia")
        if carpeta:
            item = QListWidgetItem(f"Carpeta: {Path(carpeta).name}")
            item.setData(Qt.ItemDataRole.UserRole, carpeta)
            self.lista.addItem(item)
            self.lista.setCurrentItem(item)

    # ------------------------------------------------------------------ motor y clave
    def motor_elegido(self) -> str:
        return str(self.c_motor.currentData())

    def _al_cambiar_motor(self) -> None:
        anterior = self._motor_anterior
        if anterior is not None:  # lo escrito para el motor anterior se recuerda aunque todavía no se haya usado
            self._preferencias["modelos"] = _diccionario(self._preferencias.get("modelos")) | {
                anterior: self.c_modelo.currentText().strip()
            }
            if anterior == "personalizado":
                self._preferencias["direcciones"] = _diccionario(self._preferencias.get("direcciones")) | {
                    anterior: self.e_direccion.text().strip()
                }
        motor = self.motor_elegido()
        self._motor_anterior = motor
        es_gemini = motor == fabrica.GEMINI
        guardada = _diccionario(self._preferencias.get("direcciones")).get(motor, "")
        self.e_direccion.setText(guardada or fabrica.direccion_por_defecto(motor))
        self.e_direccion.setReadOnly(motor != "personalizado")
        self._formulario.setRowVisible(self.e_direccion, not es_gemini)
        modelo = _diccionario(self._preferencias.get("modelos")).get(motor, "")
        if es_gemini and not modelo:
            modelo = str(self._preferencias.get("modelo", MODELO_POR_DEFECTO))  # preferencia de la v2.0
        self.c_modelo.clear()
        if es_gemini:
            self.c_modelo.addItems(list(PRECIOS))
        self.c_modelo.setCurrentText(modelo)
        editor = self.c_modelo.lineEdit()
        if editor is not None:
            editor.setPlaceholderText("" if es_gemini else "Pulsa «Probar conexión» para ver la lista")
        self.c_lotes.setEnabled(es_gemini)
        if not es_gemini:
            self.c_lotes.setChecked(False)
        self.b_clave.setEnabled(not fabrica.es_local(motor))
        self._actualizar_estado_clave()

    def _actualizar_estado_clave(self) -> None:
        motor = self.motor_elegido()
        if fabrica.es_local(motor):
            self.etiqueta_clave.setText("No hace falta: el modelo corre en tu PC")
        elif configuracion.leer_clave(motor):
            self.etiqueta_clave.setText("Guardada ✓")
        else:
            self.etiqueta_clave.setText("No guardada" if fabrica.necesita_clave(motor) else "Opcional")

    def _guardar_clave(self) -> None:
        motor = self.motor_elegido()
        nombre = fabrica.MOTORES[motor]
        donde = " de aistudio.google.com/apikey" if motor == fabrica.GEMINI else ""
        clave, ok = QInputDialog.getText(
            self, f"Clave de {nombre}", f"Pega tu clave{donde}:", QLineEdit.EchoMode.Password
        )
        if ok and clave.strip():
            configuracion.guardar_clave(clave.strip(), motor)
            self._actualizar_estado_clave()
            self.escribir(f"Clave de {nombre} guardada en el almacén de credenciales del sistema.")

    def _probar_clave(self) -> None:
        if self._sondeo is not None:
            return
        o = self.opciones()
        clave = configuracion.leer_clave(o["motor"])
        try:
            motor = self._fabrica_motor(o["motor"], clave, o["modelo"] or "listar", o["direccion"])
        except ErrorFatal as e:
            self.avisar(str(e))
            return
        listar = getattr(motor, "listar_modelos", None)
        if not callable(listar):
            return
        self.b_probar.setEnabled(False)
        self.escribir(f"Comprobando la conexión con {fabrica.MOTORES[o['motor']]}…")
        self._sondeo = QThread(self)  # con padre: Qt lo libera junto con la ventana
        self._consulta = Consulta(cast(Callable[[], list[str]], listar))
        if isinstance(motor, Compatible):
            self._sondeo.finished.connect(motor.cerrar)
        self._consulta.moveToThread(self._sondeo)
        self._sondeo.finished.connect(self._consulta.deleteLater)
        self._sondeo.started.connect(self._consulta.ejecutar)
        self._consulta.listo.connect(self._modelos_listos)
        self._consulta.fallo.connect(self._modelos_fallo)
        self._sondeo.start()

    def _fin_sondeo(self) -> None:
        if self._sondeo is not None:
            self._sondeo.quit()
            self._sondeo.wait()
            self._sondeo.deleteLater()
        self._sondeo = None
        self._consulta = None
        self.b_probar.setEnabled(True)

    def _modelos_fallo(self, mensaje: str) -> None:
        self._fin_sondeo()
        self.avisar(mensaje)

    def _modelos_listos(self, modelos: list[str]) -> None:
        self._fin_sondeo()
        if modelos:
            actual = self.c_modelo.currentText()
            self.c_modelo.clear()
            self.c_modelo.addItems([m for m in modelos if "tts" not in m and "image" not in m])
            por_defecto = MODELO_POR_DEFECTO if self.motor_elegido() == fabrica.GEMINI else modelos[0]
            self.c_modelo.setCurrentText(actual if actual in modelos else por_defecto)
            self.escribir(f"Conexión correcta. {len(modelos)} modelos disponibles.")
        else:
            self.escribir("Conexión correcta, pero el servidor no informó modelos: escribe el nombre a mano.")

    # ------------------------------------------------------------------ acciones
    def opciones(self) -> dict[str, Any]:
        return {
            "dialecto": self.c_dialecto.currentData(),
            "grupos": [g for g, c in self.casillas.items() if c.isChecked()],
            "motor": self.motor_elegido(),
            "direccion": self.e_direccion.text().strip(),
            "modelo": self.c_modelo.currentText().strip()
            or (MODELO_POR_DEFECTO if self.motor_elegido() == fabrica.GEMINI else ""),
            "lotes": self.c_lotes.isChecked(),
            "hilos": self.c_hilos.value(),
            "activar": self.c_activar.isChecked(),
            "idioma": self.c_activar.isChecked(),
            "contexto": self.e_contexto.text().strip(),
            "revisar": self.c_revisar.isChecked(),
        }

    def _confirmar_traducir(self) -> None:
        motor = self.motor_elegido()
        if fabrica.necesita_clave(motor) and not configuracion.leer_clave(motor) and not self._es_prueba():
            self.avisar(f"Falta la clave de {fabrica.MOTORES[motor]}: pulsa «Guardar clave…».")
            return
        texto = (
            "Cierra Minecraft antes de seguir.\n\nLas misiones y scripts se guardan en una copia y puedes "
            "volver al original con «Restaurar original»."
        )
        if self.ultimo_informe is not None:
            o = self.opciones()
            costo = self.ultimo_informe.costo(o["modelo"], o["lotes"], o["motor"], o["revisar"])
            if costo is not None:
                texto = f"Costo estimado: US$ {costo:.2f}.\n\n" + texto
        if self._preguntar("Traducir", texto):
            self.lanzar("traducir")

    def _confirmar_restaurar(self) -> None:
        if self._preguntar("Restaurar", "Las misiones, scripts y libros propios vuelven al texto original. ¿Seguir?"):
            self.lanzar("restaurar")

    def _es_prueba(self) -> bool:
        return os.environ.get("TRADUCTOR_ES_PRUEBA_UI") == "1"

    def lanzar(self, accion: str) -> None:
        carpeta = self.carpeta()
        if not carpeta:
            self.avisar("Elige primero una instancia.")
            return
        if self._hilo is not None:
            return
        opciones = self.opciones()
        if accion == "traducir":
            try:
                motor = self._fabrica_motor(
                    opciones["motor"], configuracion.leer_clave(opciones["motor"]), opciones["modelo"],
                    opciones["direccion"],
                )  # fmt: skip
            except ErrorFatal as e:
                self.avisar(str(e))
                return
        else:
            motor = Simulador()  # analizar y restaurar no llaman al motor
        self._guardar_preferencias(carpeta)
        self._cancelar.clear()
        self.log.clear()
        self.barra.setValue(0)
        self.estado.setText("Trabajando…")
        self._ocupado(True)
        self._hilo = QThread(self)  # con padre: Qt lo libera junto con la ventana
        self._trabajador = Trabajador(accion, carpeta, opciones, motor, self._cancelar)
        self._trabajador.moveToThread(self._hilo)
        self._hilo.finished.connect(self._trabajador.deleteLater)
        self._hilo.started.connect(self._trabajador.ejecutar)
        self._trabajador.registro.connect(self.escribir)
        self._trabajador.progreso.connect(self._progreso)
        self._accion = accion
        self._trabajador.terminado.connect(self._terminar)
        self._trabajador.fallo.connect(self._fallar)
        self._hilo.start()

    def _ocupado(self, si: bool) -> None:
        for b in (self.b_analizar, self.b_traducir, self.b_restaurar, self.b_exportar, self.b_kit, self.lista,
                  self.b_correcciones):  # fmt: skip
            b.setEnabled(not si)
        self.b_cancelar.setEnabled(si)

    def _progreso(self, hechos: int, total: int) -> None:
        self.barra.setMaximum(max(total, 1))
        self.barra.setValue(hechos)
        self.estado.setText(f"Traduciendo… {hechos} de {total}")

    def _limpiar_hilo(self) -> None:
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait()
            self._hilo.deleteLater()
        self._hilo = None
        self._trabajador = None
        self._ocupado(False)

    def _terminar(self, resultado: object) -> None:
        accion = self._accion
        self._limpiar_hilo()
        if isinstance(resultado, Informe):
            self.ultimo_informe = resultado
            self._mostrar(resultado)
            self.estado.setText(
                "Análisis listo. Si te parece bien, pulsa «Traducir»."
                if accion == "analizar"
                else "¡Listo! Abre el juego."
            )
        else:
            n = len(resultado) if isinstance(resultado, list) else 0  # pyright: ignore[reportUnknownArgumentType]
            self.estado.setText(f"Restaurados {n} archivos.")
        self.escribir(self.estado.text())

    def _fallar(self, mensaje: str) -> None:
        registro.LOGGER.warning("Se detuvo: %s", mensaje)
        self._limpiar_hilo()
        self.estado.setText("Se detuvo.")
        self.escribir(f"✖ {mensaje}")
        self.avisar(mensaje)

    def _mostrar(self, informe: Informe) -> None:
        self.tabla.setRowCount(len(informe.modulos))
        for fila, m in enumerate(informe.modulos):
            valores = [m.nombre, m.descripcion, str(m.textos), str(m.a_traducir), str(m.resumen) if m.resumen else ""]
            for col, v in enumerate(valores):
                self.tabla.setItem(fila, col, QTableWidgetItem(v))
        o = self.opciones()
        costo = informe.costo(o["modelo"], o["lotes"], o["motor"], o["revisar"])
        texto = f"Para el motor: {informe.a_traducir} textos, {informe.caracteres} caracteres."
        if fabrica.es_local(o["motor"]):
            texto += " Sin costo: el modelo corre en tu PC."
        elif costo is not None:
            texto += f" Costo estimado con {o['modelo']}{' por lotes' if o['lotes'] else ''}: US$ {costo:.2f}."
        elif o["motor"] != fabrica.GEMINI:
            texto += " El costo depende del proveedor y del modelo: revisa sus precios."
        self.costo.setText(texto)
        for aviso in informe.avisos:
            self.escribir(f"⚠ {aviso}")
        if informe.revision_automatica is not None:
            self.escribir(str(informe.revision_automatica))
        if informe.pack_activado:
            self.escribir("Juego: " + ", ".join(informe.pack_activado))

    def _exportar(self, kit: bool) -> None:
        carpeta = self.carpeta()
        if not carpeta:
            self.avisar("Elige primero una instancia.")
            return
        sugerido = str(Path.home() / ("Kit_servidor_traduccion.zip" if kit else "Traduccion_ES.zip"))
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar como", sugerido, "Zip (*.zip)")
        if not destino:
            return
        juego = resolver_carpeta_juego(Path(carpeta)) or Path(carpeta)
        try:
            n = (exportar.exportar_kit_servidor if kit else exportar.exportar_pack)(juego, Path(destino))
        except (ValueError, OSError) as e:
            self.avisar(str(e))
            return
        self.escribir(f"Exportado: {destino} ({n} archivos)")

    def abrir_correcciones(self) -> None:
        correcciones.mostrar(self, str(self.c_dialecto.currentData()))

    def _abrir_carpeta(self) -> None:
        carpeta = self.carpeta()
        if carpeta:
            QDesktopServices.openUrl(QUrl.fromLocalFile(carpeta))

    # ------------------------------------------------------------------ utilidades
    def escribir(self, texto: str) -> None:
        self.log.appendPlainText(texto)
        registro.LOGGER.info(texto)

    def copiar_diagnostico(self) -> str:
        extra = {"Instancia": self.carpeta() or "(ninguna)", "Acción en curso": self._accion or "(ninguna)"}
        if self.ultimo_informe is not None:
            modulos = self.ultimo_informe.modulos
            extra["Último análisis"] = ", ".join(f"{m.grupo} {m.textos}/{m.a_traducir}" for m in modulos)
        texto = registro.diagnostico(extra)
        QApplication.clipboard().setText(texto)
        self.estado.setText("Diagnóstico copiado: pégalo en el reporte del problema.")
        return texto

    def _abrir_registro(self) -> None:
        ruta = registro.ruta_actual()
        if ruta is None or not ruta.is_file():
            self.avisar("Todavía no hay nada en el registro.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))

    def avisar(self, texto: str) -> None:
        if self._es_prueba():
            self.escribir(f"[aviso] {texto}")
            return
        QMessageBox.information(self, NOMBRE, texto)

    def _preguntar(self, titulo: str, texto: str) -> bool:
        if self._es_prueba():
            return True
        return QMessageBox.question(self, titulo, texto) == QMessageBox.StandardButton.Yes

    def _guardar_preferencias(self, carpeta: str) -> None:
        o = self.opciones()
        contextos = _diccionario(self._preferencias.get("contextos"))
        if o["contexto"]:
            contextos[carpeta] = o["contexto"]
        else:
            contextos.pop(carpeta, None)
        modelos = _diccionario(self._preferencias.get("modelos")) | {o["motor"]: o["modelo"]}
        direcciones = _diccionario(self._preferencias.get("direcciones"))
        if o["motor"] == "personalizado":
            direcciones["personalizado"] = o["direccion"]
        self._preferencias = {
            "carpeta": carpeta, "dialecto": o["dialecto"], "grupos": o["grupos"], "motor": o["motor"],
            "modelo": modelos.get(fabrica.GEMINI, MODELO_POR_DEFECTO), "modelos": modelos,
            "direcciones": direcciones, "lotes": o["lotes"], "hilos": o["hilos"], "contextos": contextos,
            "revisar": o["revisar"], "avisar_version": self.c_avisar.isChecked(),
        }  # fmt: skip
        configuracion.guardar_preferencias(dict(self._preferencias))

    # ------------------------------------------------------------------ versión nueva
    def _guardar_aviso(self, activo: bool) -> None:
        self._preferencias["avisar_version"] = activo
        configuracion.guardar_preferencias(dict(self._preferencias))

    def _buscar_novedad(self, funcion: Callable[[], Novedad | None]) -> None:
        def como_lista() -> list[str]:
            n = funcion()
            return [n.version, n.enlace] if n else []

        self._hilo_novedad = QThread(self)  # con padre: Qt lo libera junto con la ventana
        self._consulta_novedad = Consulta(como_lista)
        self._consulta_novedad.moveToThread(self._hilo_novedad)
        self._hilo_novedad.finished.connect(self._consulta_novedad.deleteLater)
        self._hilo_novedad.started.connect(self._consulta_novedad.ejecutar)
        self._consulta_novedad.listo.connect(self._mostrar_novedad)
        self._consulta_novedad.fallo.connect(self._novedad_fallo)
        self._hilo_novedad.start()

    def _novedad_fallo(self, _mensaje: str) -> None:
        self._fin_novedad()  # sin aviso: se vuelve a intentar en el próximo arranque

    def _fin_novedad(self) -> None:
        if self._hilo_novedad is not None:
            self._hilo_novedad.quit()
            self._hilo_novedad.wait()
        self._hilo_novedad = None
        self._consulta_novedad = None

    def _mostrar_novedad(self, datos: list[str]) -> None:
        self._fin_novedad()
        if len(datos) == 2:
            version, enlace = datos
            self.novedad.setText(f'<a href="{enlace}"><b>Versión nueva: {version}</b></a>')
            self.novedad.setToolTip("Abre la página de descarga en GitHub")
            self.novedad.setVisible(True)
            self.escribir(f"Hay una versión nueva de {NOMBRE}: {version} ({enlace})")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._fin_novedad()
        self._cancelar.set()
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait(5000)
        event.accept()

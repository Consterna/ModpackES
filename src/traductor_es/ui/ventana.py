"""Ventana principal: elegir instancia, analizar gratis, traducir, restaurar y exportar."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

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

from .. import AUTOR, NOMBRE, REPOSITORIO, __version__, configuracion, registro
from ..fuentes.instancia import resolver_carpeta_juego
from ..fuentes.lanzadores import InstanciaEncontrada, buscar
from ..motores.base import Cancelado, ErrorFatal, Motor
from ..motores.gemini import MODELO_POR_DEFECTO, PRECIOS, Gemini
from ..motores.simulador import Simulador
from ..proceso import GRUPOS, Informe, Proceso
from ..salida import exportar
from . import correcciones

FabricaMotor = Callable[[str, str], Motor]
NOMBRES_GRUPOS = {
    "mods": "Mods (objetos, bloques, menús)",
    "libros": "Libros guía",
    "misiones": "Misiones",
    "scripts": "Scripts de KubeJS",
}


def _gemini(clave: str, modelo: str) -> Motor:
    return Gemini(clave, modelo)


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
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"{NOMBRE} {__version__} · Traductor de modpacks al español")
        self.resize(1100, 800)
        self._buscar_instancias = buscar_instancias
        self._fabrica_motor: FabricaMotor = fabrica_motor or _gemini
        self._hilo: QThread | None = None
        self._accion = ""
        self._sondeo: QThread | None = None
        self._consulta: Consulta | None = None
        self._trabajador: Trabajador | None = None
        self._cancelar = threading.Event()
        self.ultimo_informe: Informe | None = None
        self._preferencias = configuracion.leer_preferencias()
        self._construir()
        self.actualizar_instancias()
        self._actualizar_estado_clave()

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
        self.c_modelo = QComboBox()
        self.c_modelo.setEditable(True)
        self.c_modelo.addItems(list(PRECIOS))
        self.c_modelo.setCurrentText(self._preferencias.get("modelo", MODELO_POR_DEFECTO))
        formulario.addRow("Modelo de Gemini:", self.c_modelo)
        self.c_lotes = QCheckBox("Por lotes: mitad de precio, pero puede tardar desde minutos hasta horas")
        self.c_lotes.setChecked(bool(self._preferencias.get("lotes", False)))
        formulario.addRow("", self.c_lotes)
        self.c_hilos = QSpinBox()
        self.c_hilos.setRange(1, 16)
        self.c_hilos.setValue(int(self._preferencias.get("hilos", 4)))
        formulario.addRow("Peticiones a la vez:", self.c_hilos)
        self.c_activar = QCheckBox("Activar el pack y poner el juego en español (con Minecraft cerrado)")
        self.c_activar.setChecked(True)
        formulario.addRow("", self.c_activar)
        clave = QHBoxLayout()
        self.etiqueta_clave = QLabel()
        self.b_clave = QPushButton("Guardar clave…")
        self.b_clave.clicked.connect(self._guardar_clave)
        self.b_probar = QPushButton("Probar clave")
        self.b_probar.clicked.connect(self._probar_clave)
        clave.addWidget(self.etiqueta_clave, 1)
        clave.addWidget(self.b_clave)
        clave.addWidget(self.b_probar)
        formulario.addRow("Clave de Gemini:", clave)
        capa.addWidget(opciones)

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
        pie.addWidget(self.b_diagnostico)
        pie.addWidget(self.b_registro)
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

    def _elegir_carpeta(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(self, "Carpeta de la instancia")
        if carpeta:
            item = QListWidgetItem(f"Carpeta: {Path(carpeta).name}")
            item.setData(Qt.ItemDataRole.UserRole, carpeta)
            self.lista.addItem(item)
            self.lista.setCurrentItem(item)

    # ------------------------------------------------------------------ clave
    def _actualizar_estado_clave(self) -> None:
        self.etiqueta_clave.setText("Guardada ✓" if configuracion.leer_clave() else "No guardada")

    def _guardar_clave(self) -> None:
        clave, ok = QInputDialog.getText(
            self, "Clave de Gemini", "Pega tu clave de aistudio.google.com/apikey:", QLineEdit.EchoMode.Password
        )
        if ok and clave.strip():
            configuracion.guardar_clave(clave.strip())
            self._actualizar_estado_clave()
            self.escribir("Clave guardada en el almacén de credenciales del sistema.")

    def _probar_clave(self) -> None:
        clave = configuracion.leer_clave()
        if not clave:
            self.avisar("Primero guarda la clave de Gemini.")
            return
        motor = self._fabrica_motor(clave, self.c_modelo.currentText())
        if not isinstance(motor, Gemini) or self._sondeo is not None:
            return
        self.b_probar.setEnabled(False)
        self.escribir("Comprobando la clave con Google…")
        self._sondeo = QThread(self)  # con padre: Qt lo libera junto con la ventana
        self._consulta = Consulta(motor.listar_modelos)
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
            self.c_modelo.setCurrentText(actual if actual in modelos else MODELO_POR_DEFECTO)
            self.escribir(f"Clave correcta. {len(modelos)} modelos disponibles.")

    # ------------------------------------------------------------------ acciones
    def opciones(self) -> dict[str, Any]:
        return {
            "dialecto": self.c_dialecto.currentData(),
            "grupos": [g for g, c in self.casillas.items() if c.isChecked()],
            "modelo": self.c_modelo.currentText().strip() or MODELO_POR_DEFECTO,
            "lotes": self.c_lotes.isChecked(),
            "hilos": self.c_hilos.value(),
            "activar": self.c_activar.isChecked(),
            "idioma": self.c_activar.isChecked(),
        }

    def _confirmar_traducir(self) -> None:
        if not configuracion.leer_clave() and not self._es_prueba():
            self.avisar("Falta la clave de Gemini: pulsa «Guardar clave…».")
            return
        texto = (
            "Cierra Minecraft antes de seguir.\n\nLas misiones y scripts se guardan en una copia y puedes "
            "volver al original con «Restaurar original»."
        )
        if self.ultimo_informe is not None:
            o = self.opciones()
            costo = self.ultimo_informe.costo(o["modelo"], o["lotes"])
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
            clave = configuracion.leer_clave() or ""
            motor = self._fabrica_motor(clave, opciones["modelo"])
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
        costo = informe.costo(o["modelo"], o["lotes"])
        texto = f"Para el motor: {informe.a_traducir} textos, {informe.caracteres} caracteres."
        if costo is not None:
            texto += f" Costo estimado con {o['modelo']}{' por lotes' if o['lotes'] else ''}: US$ {costo:.2f}."
        self.costo.setText(texto)
        for aviso in informe.avisos:
            self.escribir(f"⚠ {aviso}")
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
        configuracion.guardar_preferencias(
            {"carpeta": carpeta, "dialecto": o["dialecto"], "grupos": o["grupos"], "modelo": o["modelo"],
             "lotes": o["lotes"], "hilos": o["hilos"]}
        )  # fmt: skip

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cancelar.set()
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait(5000)
        event.accept()

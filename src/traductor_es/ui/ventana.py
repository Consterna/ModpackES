"""Ventana principal: elegir instancia, analizar gratis, traducir, restaurar y exportar."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QMimeData, QObject, QSize, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import AUTOR, NOMBRE, REPOSITORIO, __version__, actualizaciones, configuracion, registro
from ..actualizaciones import Novedad
from ..fuentes.instancia import Instancia, resolver_carpeta_juego
from ..fuentes.lanzadores import InstanciaEncontrada, buscar
from ..modulos.cobertura import Hallazgo, texto_del_informe
from ..motores import fabrica
from ..motores.base import Cancelado, ErrorFatal, Motor
from ..motores.compatible import Compatible
from ..motores.gemini import MODELO_POR_DEFECTO, PRECIOS
from ..motores.simulador import Simulador
from ..nucleo.traductor import LARGO_CONTEXTO
from ..proceso import GRUPOS, Informe, Proceso
from ..salida import exportar, mod_apoyo
from . import correcciones, iconos, tema
from .bienvenida import TarjetaBienvenida
from .componentes import (
    Aviso,
    BotonPrincipal,
    EtiquetaRuta,
    Pasos,
    Plegable,
    TarjetaGrupo,
    etiqueta,
    icono_en_boton,
    seguir_tema,
)
from .informe import DialogoInforme
from .instancias import Lector, ListaInstancias, traducida
from .motor import DialogoMotor

#: (motor, clave, modelo, dirección) → motor listo para traducir
FabricaMotor = Callable[[str, str | None, str, str], Motor]
#: grupo → (título, ícono, qué abarca)
GRUPOS_VISIBLES = {
    "mods": ("Mods", "box", "Objetos, bloques y menús"),
    "libros": ("Libros guía", "book-open", "Patchouli y otros"),
    "misiones": ("Misiones", "flag", "FTB Quests, Heracles…"),
    "scripts": ("Scripts", "code-xml", "Textos de KubeJS"),
}
PASOS = ["Motor", "Analizar", "Traducir", "Listo"]
LOGO = Path(__file__).with_name("icono.png")
SIN_INSTANCIA = "Están a la izquierda; si no aparece la tuya, pulsa «Elegir carpeta…»."
TEMAS = {"sistema": "Como Windows", "oscuro": "Oscuro", "claro": "Claro"}


def _diccionario(valor: object) -> dict[str, str]:
    """Un diccionario de texto leído de las preferencias (vacío si el archivo tenía otra cosa)."""
    if not isinstance(valor, dict):
        return {}
    return {str(k): str(v) for k, v in cast(dict[object, object], valor).items()}


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _dinero(costo: float) -> str:
    return f"US$ {costo:.2f}".replace(".", ",")


def _restante(segundos: float) -> str:
    if segundos < 60:
        return "menos de un minuto"
    if segundos < 90 * 60:
        return f"unos {round(segundos / 60)} min"
    return f"unas {round(segundos / 3600)} h"


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
                texto_java=self.opciones["texto_java"],
                scripts_exhaustivo=self.opciones["exhaustivo"],
            ) as p:
                self.registro.emit(f"Minecraft {p.instancia.version} · {p.instancia.loader or '¿loader?'}")
                if self.accion == "analizar":
                    resultado: object = p.analizar()
                elif self.accion == "traducir":
                    resultado = p.ejecutar(activar=self.opciones["activar"], poner_idioma=self.opciones["idioma"])
                elif self.accion == "cobertura":
                    resultado = p.que_queda(java=True, progreso=self.progreso.emit)
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
    nota = f"\n\nQuedó anotado en {donde}. Usa «Más ▸ Copiar diagnóstico» para reportarlo." if donde else ""
    return f"Error no previsto: {type(e).__name__}: {e}{nota}"


class Ventana(QMainWindow):
    """La ventana guía un camino de cuatro pasos (motor, analizar, traducir, listo) con un solo botón principal.

    `_estado` dice qué hace ese botón: «analizar», «traducir», «trabajando» o «listo».
    """

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
        self.resize(1180, 860)
        self.setMinimumSize(900, 600)
        self._buscar_instancias = buscar_instancias
        self._fabrica_motor: FabricaMotor = fabrica_motor or fabrica.crear
        self._hilo: QThread | None = None
        self._accion = ""
        self._estado = "analizar"
        self._antes = "analizar"
        self._sondeo: QThread | None = None
        self._consulta: Consulta | None = None
        self._trabajador: Trabajador | None = None
        self._lectores: list[Lector] = []
        self._cancelar = threading.Event()
        self._inicio: tuple[float, int] | None = None
        self._fase = ""
        self._clave_lista = False
        self.ultimo_informe: Informe | None = None
        self.ultima_cobertura: list[Hallazgo] = []
        self._dialogo_informe: DialogoInforme | None = None
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
        self.dialogo_motor = DialogoMotor(self)
        self.c_motor, self.e_direccion = self.dialogo_motor.c_motor, self.dialogo_motor.e_direccion
        self.c_modelo, self.etiqueta_clave = self.dialogo_motor.c_modelo, self.dialogo_motor.etiqueta_clave
        self.b_clave, self.b_probar = self.dialogo_motor.b_clave, self.dialogo_motor.b_probar
        self.b_clave.clicked.connect(self._guardar_clave)
        self.b_probar.clicked.connect(self._probar_clave)
        self.dialogo_motor.finished.connect(self._al_cerrar_motor)
        central = QWidget()
        capa = QVBoxLayout(central)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        capa.addWidget(self._barra_superior())
        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self._barra_lateral())
        cuerpo.addWidget(self._contenido(), 1)
        capa.addLayout(cuerpo, 1)
        self.setCentralWidget(central)
        atajos = [("Ctrl+F", self.lista.e_buscar.setFocus), ("F5", self.actualizar_instancias),
                  ("Ctrl+Return", self.b_principal.click), ("Ctrl+Enter", self.b_principal.click)]  # fmt: skip
        self.atajos: list[QShortcut] = []
        for tecla, funcion in atajos:
            atajo = QShortcut(QKeySequence(tecla), self)
            atajo.activated.connect(funcion)
            self.atajos.append(atajo)
        self.setAcceptDrops(True)  # soltar la carpeta de un modpack en cualquier parte de la ventana
        self.c_motor.setCurrentIndex(max(0, self.c_motor.findData(self._preferencias.get("motor", fabrica.GEMINI))))
        self.c_motor.currentIndexChanged.connect(self._al_cambiar_motor)
        self._al_cambiar_motor()
        for senal in (
            self.c_lotes.toggled,
            self.c_revisar.toggled,
            self.c_activar.toggled,
            self.c_java.toggled,
            self.c_exhaustivo.toggled,
        ):
            senal.connect(self._al_cambiar_opciones)
        self.c_hilos.valueChanged.connect(self._al_cambiar_opciones)
        self.c_dialecto.currentIndexChanged.connect(self._al_cambiar_opciones)
        self.c_modelo.currentTextChanged.connect(self._al_cambiar_opciones)
        self._al_cambiar_opciones()

    def _barra_superior(self) -> QFrame:
        barra = QFrame()
        barra.setProperty("tipo", "barra")
        capa = QHBoxLayout(barra)
        capa.setContentsMargins(16, 10, 16, 10)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(LOGO)).scaled(QSize(28, 28), Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))  # fmt: skip
        capa.addWidget(logo)
        capa.addWidget(etiqueta(NOMBRE, "titulo"))
        capa.addWidget(etiqueta(__version__, "tenue"))
        capa.addStretch(1)
        self.novedad = QLabel()
        self.novedad.setOpenExternalLinks(True)
        self.novedad.setVisible(False)
        capa.addWidget(self.novedad)
        self.b_motor = QPushButton()
        self.b_motor.setProperty("tipo", "ficha")
        self.b_motor.setToolTip("Elegir el motor de traducción y guardar su clave")
        self.b_motor.clicked.connect(self.abrir_motor)
        seguir_tema(self.b_motor, self._pintar_motor)
        capa.addWidget(self.b_motor)
        self.b_ajustes = QPushButton()
        self.b_ajustes.setProperty("tipo", "plano")
        self.b_ajustes.setAccessibleName("Ajustes")
        self.b_ajustes.setToolTip("Ajustes")
        icono_en_boton(self.b_ajustes, "settings", tam=18)
        self.b_ajustes.setMenu(self._menu_ajustes())
        capa.addWidget(self.b_ajustes)
        return barra

    def _menu_ajustes(self) -> QMenu:
        menu = QMenu(self)
        self.a_motor = menu.addAction("Motor de traducción…")
        self.a_motor.triggered.connect(self.abrir_motor)
        temas = menu.addMenu("Tema")
        grupo = QActionGroup(self)
        actual = str(self._preferencias.get("tema", "sistema"))
        self.a_temas: dict[str, QAction] = {}
        for clave, texto in TEMAS.items():
            accion = temas.addAction(texto)
            accion.setCheckable(True)
            accion.setChecked(clave == actual)
            accion.triggered.connect(lambda _c=False, k=clave: self.elegir_tema(k))
            grupo.addAction(accion)
            self.a_temas[clave] = accion
        menu.addSeparator()
        self.c_avisar = menu.addAction("Avisar al abrir si hay una versión nueva")
        self.c_avisar.setCheckable(True)
        self.c_avisar.setToolTip("Consulta GitHub al abrir; no descarga nada")
        self.c_avisar.setChecked(bool(self._preferencias.get("avisar_version", True)))
        self.c_avisar.toggled.connect(self._guardar_aviso)

        def pintar() -> None:
            p = tema.actual()
            self.a_motor.setIcon(iconos.icono("sparkles", p.texto))
            temas.setIcon(iconos.icono("moon" if p.nombre == "oscuro" else "sun", p.texto))

        seguir_tema(menu, pintar)
        return menu

    def _barra_lateral(self) -> QFrame:
        lateral = QFrame()
        lateral.setProperty("tipo", "lateral")
        lateral.setFixedWidth(310)
        capa = QVBoxLayout(lateral)
        capa.setContentsMargins(14, 16, 14, 14)
        capa.setSpacing(10)
        capa.addWidget(etiqueta("Instancias", "subtitulo"))
        self.lista = ListaInstancias()
        self.lista.elegida.connect(self._al_elegir)
        capa.addWidget(self.lista, 1)
        botones = QHBoxLayout()
        self.b_carpeta = QPushButton("Elegir carpeta…")
        icono_en_boton(self.b_carpeta, "folder-plus")
        self.b_carpeta.clicked.connect(self._elegir_carpeta)
        self.b_actualizar = QPushButton()
        self.b_actualizar.setProperty("tipo", "plano")
        self.b_actualizar.setToolTip("Volver a buscar instancias (F5)")
        self.b_actualizar.setAccessibleName("Volver a buscar instancias")
        icono_en_boton(self.b_actualizar, "refresh-cw")
        self.b_actualizar.clicked.connect(self.actualizar_instancias)
        botones.addWidget(self.b_carpeta, 1)
        botones.addWidget(self.b_actualizar)
        capa.addLayout(botones)
        return lateral

    def _contenido(self) -> QScrollArea:
        hoja = QWidget()
        capa = QVBoxLayout(hoja)
        capa.setContentsMargins(28, 22, 28, 18)
        capa.setSpacing(14)
        self.aviso = Aviso()
        capa.addWidget(self.aviso)
        self.bienvenida = TarjetaBienvenida()
        self.bienvenida.configurar.connect(self.abrir_motor)
        self.bienvenida.cerrada.connect(self._bienvenida_vista)
        self.bienvenida.setVisible(not self._preferencias.get("bienvenida_vista", False))
        capa.addWidget(self.bienvenida)
        self.e_titulo = etiqueta("Elige una instancia", "titulo")
        self.e_ruta = EtiquetaRuta(SIN_INSTANCIA)
        capa.addWidget(self.e_titulo)
        capa.addWidget(self.e_ruta)
        self.pasos = Pasos(PASOS)
        capa.addWidget(self.pasos)
        capa.addLayout(self._tarjetas_grupos())
        self.costo = etiqueta("", "tenue", True)
        capa.addWidget(self.costo)
        capa.addWidget(etiqueta("Ambientación (opcional)", "subtitulo"))
        self.e_contexto = QLineEdit()
        self.e_contexto.setMaxLength(LARGO_CONTEXTO)
        self.e_contexto.setPlaceholderText("Ej.: granja acogedora, tono amable; «Bells» es la moneda")
        self.e_contexto.setToolTip("Se le da al motor para el tono y los términos propios. Se guarda por instancia.")
        self.e_contexto.setAccessibleName("Ambientación del modpack")
        capa.addWidget(self.e_contexto)
        self.avanzadas = Plegable("Opciones avanzadas", self._opciones_avanzadas())
        capa.addWidget(self.avanzadas)
        capa.addLayout(self._acciones())
        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(8)
        self.barra.setVisible(False)  # solo mientras trabaja
        self.estado = etiqueta("Listo para empezar.", "tenue", True)
        capa.addWidget(self.barra)
        capa.addWidget(self.estado)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setProperty("tipo", "registro")
        self.log.setMinimumHeight(160)
        self.log.setAccessibleName("Registro de lo que va pasando")
        self.detalles = Plegable("Detalles", self.log)
        capa.addWidget(self.detalles)
        capa.addStretch(1)
        self.creditos = etiqueta(
            f'{NOMBRE} {__version__} · © 2026 {AUTOR} · Licencia GPL-3.0 · <a href="{REPOSITORIO}">{REPOSITORIO}</a>',
            "tenue",
        )
        self.creditos.setOpenExternalLinks(True)
        self.creditos.setAlignment(Qt.AlignmentFlag.AlignRight)
        capa.addWidget(self.creditos)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setWidget(hoja)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # el contenido se ajusta
        return desplazable

    def _tarjetas_grupos(self) -> QGridLayout:
        rejilla = QGridLayout()
        rejilla.setSpacing(12)
        elegidos = set(self._preferencias.get("grupos", GRUPOS))
        self.grupos: dict[str, TarjetaGrupo] = {}
        for i, g in enumerate(GRUPOS):
            titulo, nombre_icono, abarca = GRUPOS_VISIBLES[g]
            tarjeta = TarjetaGrupo(g, titulo, nombre_icono)
            tarjeta.fijar_cantidad(None, abarca)
            tarjeta.fijar_incluido(g in elegidos)
            tarjeta.cambiado.connect(self._al_cambiar_opciones)
            self.grupos[g] = tarjeta
            rejilla.addWidget(tarjeta, 0, i)
        return rejilla

    def _opciones_avanzadas(self) -> QWidget:
        caja = QWidget()
        formulario = QFormLayout(caja)
        formulario.setContentsMargins(4, 4, 4, 4)
        formulario.setVerticalSpacing(10)
        self.c_dialecto = QComboBox()
        self.c_dialecto.addItem("Latinoamérica (es_mx)", "es_mx")
        self.c_dialecto.addItem("España (es_es)", "es_es")
        self.c_dialecto.setToolTip("La variante de la que parte la traducción; las demás variantes se copian de ella")
        self.c_dialecto.setCurrentIndex(max(0, self.c_dialecto.findData(self._preferencias.get("dialecto", "es_mx"))))
        formulario.addRow("Español de:", self.c_dialecto)
        self.c_lotes = QCheckBox("Más barato, pero tarda más (la mitad de precio; de minutos a horas)")
        self.c_lotes.setToolTip("Usa la Batch API de Google: solo con Gemini")
        self.c_lotes.setChecked(bool(self._preferencias.get("lotes", False)))
        formulario.addRow("", self.c_lotes)
        self.c_revisar = QCheckBox("Revisar misiones y libros, y rehacer lo que tenga errores graves")
        self.c_revisar.setToolTip(
            "Otro pedido al motor juzga cada traducción nueva de misiones y libros; las que tengan errores graves se "
            "vuelven a traducir. El análisis muestra el costo con la revisión incluida."
        )
        self.c_revisar.setChecked(bool(self._preferencias.get("revisar", False)))
        formulario.addRow("", self.c_revisar)
        self.c_java = QCheckBox("Incluir texto escrito en el código de los mods (necesita el mod de apoyo)")
        self.c_java.setToolTip(
            "Algunos mods tienen mensajes escritos en su código y un resource pack no los alcanza. Esto los "
            "traduce a una tabla que lee el mod de apoyo «ModpackES Runtime» (Más ▸ Instalar el mod de apoyo). "
            "Por ahora existe para Forge 1.19.2 y 1.20.1, NeoForge 1.21.1 y Fabric 1.19.4, 1.20.1, 1.21.1 y 1.21.4."
        )
        self.c_java.setChecked(bool(self._preferencias.get("texto_java", False)))
        formulario.addRow("", self.c_java)
        self.c_exhaustivo = QCheckBox("Scripts: traducir toda frase, aunque no se sepa dónde se muestra")
        self.c_exhaustivo.setToolTip(
            "Puede tocar lógica de los scripts de KubeJS (una frase que se compara o se guarda). Todo queda con copia "
            "de seguridad y se puede restaurar. Mira antes «Más ▸ Qué queda en inglés»."
        )
        self.c_exhaustivo.setChecked(bool(self._preferencias.get("exhaustivo", False)))
        formulario.addRow("", self.c_exhaustivo)
        self.c_hilos = QSpinBox()
        self.c_hilos.setRange(1, 16)
        self.c_hilos.setSuffix(" pedidos a la vez")
        self.c_hilos.setToolTip("Más es más rápido, pero los planes gratuitos y los modelos en tu PC aguantan pocos")
        self.c_hilos.setValue(int(self._preferencias.get("hilos", 4)))
        formulario.addRow("Velocidad:", self.c_hilos)
        self.c_activar = QCheckBox("Activar el pack y poner el juego en español (con Minecraft cerrado)")
        self.c_activar.setChecked(True)
        formulario.addRow("", self.c_activar)
        return caja

    def _acciones(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(10)
        self.b_principal = BotonPrincipal()
        self.b_principal.setToolTip("La acción del paso en el que estás (Ctrl+Enter)")
        self.b_principal.clicked.connect(self._accion_principal)
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.setProperty("tipo", "peligro")
        icono_en_boton(self.b_cancelar, "square", lambda p: p.peligro)
        self.b_cancelar.clicked.connect(self._cancelar.set)
        self.b_cancelar.setVisible(False)
        self.b_secundario = QPushButton("Analizar de nuevo")
        self.b_secundario.setProperty("tipo", "plano")
        icono_en_boton(self.b_secundario, "refresh-cw")
        self.b_secundario.clicked.connect(lambda: self.lanzar("analizar"))
        self.b_mas = QPushButton("Más")
        self.b_mas.setMenu(self._menu_mas())
        fila.addWidget(self.b_principal)
        fila.addWidget(self.b_cancelar)
        fila.addWidget(self.b_secundario)
        fila.addStretch(1)
        fila.addWidget(self.b_mas)
        return fila

    def _menu_mas(self) -> QMenu:
        menu = QMenu(self)
        con_icono: list[tuple[QAction, str]] = []

        def agregar(texto: str, nombre_icono: str, funcion: Callable[[], object]) -> QAction:
            accion = menu.addAction(texto)
            accion.triggered.connect(funcion)
            con_icono.append((accion, nombre_icono))
            return accion

        self.a_correcciones = agregar("Correcciones…", "pencil", self.abrir_correcciones)
        self.a_correcciones.setToolTip("Buscar y corregir a mano traducciones de la memoria")
        self.a_cobertura = agregar("Qué queda en inglés", "circle-alert", lambda: self.lanzar("cobertura"))
        self.a_cobertura.setToolTip("Lista el texto que no se puede traducir y por qué (solo lee, no cambia nada)")
        self.a_guardar_informe = agregar("Guardar el informe de lo que queda…", "file-text", self._guardar_informe)
        self.a_comprobar_apoyo = agregar("Comprobar el mod de apoyo", "circle-check", self._comprobar_apoyo)
        self.a_apoyo = agregar("Instalar el mod de apoyo", "package", self._instalar_apoyo)
        self.a_apoyo.setToolTip(
            "Pone ModpackES Runtime en la carpeta mods: muestra en español el texto del código de los mods"
        )
        self.a_quitar_apoyo = agregar("Quitar el mod de apoyo", "undo-2", self._quitar_apoyo)
        self.a_restaurar = agregar("Restaurar el original…", "undo-2", self._confirmar_restaurar)
        self.a_exportar = agregar("Exportar pack…", "package", lambda: self._exportar(kit=False))
        self.a_kit = agregar("Kit de servidor…", "server", lambda: self._exportar(kit=True))
        self.a_abrir = agregar("Abrir la carpeta", "folder-open", self._abrir_carpeta)
        menu.addSeparator()
        self.a_diagnostico = agregar("Copiar diagnóstico", "copy", self.copiar_diagnostico)
        self.a_diagnostico.setToolTip("Copia versiones y el final del registro, para pegarlos al reportar un problema")
        self.a_registro = agregar("Abrir el registro", "file-text", self._abrir_registro)

        def pintar() -> None:
            for accion, nombre_icono in con_icono:
                accion.setIcon(iconos.icono(nombre_icono, tema.actual().texto))

        seguir_tema(menu, pintar)
        return menu

    # ------------------------------------------------------------------ instancias
    def actualizar_instancias(self) -> None:
        if self._hilo is not None:  # el atajo F5 sigue activo mientras trabaja: la lista no se toca
            return
        for lector in self._lectores:
            lector.parar.set()
        self._lectores = [lector for lector in self._lectores if not lector.terminado.is_set()]
        self.lista.limpiar()
        for e in self._buscar_instancias():
            self.lista.agregar(e.nombre, e.lanzador, str(e.juego))
        self._leer_datos([t.ruta for t in self.lista.tarjetas])
        ultima = self._preferencias.get("carpeta")
        tarjeta = self.lista.tarjeta_de(str(ultima)) if ultima else None
        self.lista.elegir(tarjeta)

    def _leer_datos(self, carpetas: list[str]) -> None:
        if not carpetas:
            return
        lector = Lector(carpetas)  # se guarda: lo que todavía no llegó a la ventana necesita al emisor vivo
        lector.leido.connect(self.lista.al_leer)
        self._lectores.append(lector)
        lector.iniciar()

    def carpeta(self) -> str | None:
        return self.lista.carpeta()

    def _al_elegir(self, carpeta: str) -> None:
        self._olvidar_analisis()  # lo analizado era de otra instancia: no se muestra ni se usa para el costo
        self.aviso.ocultar()
        actual = self.lista.actual()
        if actual is None:
            self.e_titulo.setText("Elige una instancia")
            self.e_ruta.fijar(SIN_INSTANCIA)
        else:
            self.e_titulo.setText(actual.nombre)
            self.e_ruta.fijar(f"{actual.lanzador} · {carpeta}")
            self.e_contexto.setText(self._contexto_de(carpeta))
        self._al_cambiar_opciones()

    def _olvidar_analisis(self) -> None:
        self.ultimo_informe = None
        self._estado = "analizar"
        for g, tarjeta in self.grupos.items():
            tarjeta.fijar_cantidad(None, GRUPOS_VISIBLES[g][2])
        self.costo.setText("")

    def _contexto_de(self, carpeta: str) -> str:
        return _diccionario(self._preferencias.get("contextos")).get(carpeta, "")

    def _elegir_carpeta(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(self, "Carpeta de la instancia")
        if carpeta:
            self.agregar_carpeta(carpeta)

    def agregar_carpeta(self, carpeta: str) -> bool:
        ruta = Path(carpeta)
        juego = resolver_carpeta_juego(ruta)
        if juego is None:
            self.avisar(f"«{ruta.name}» no parece una instancia de Minecraft: no tiene las carpetas mods ni config.")
            return False
        # La del juego, con «\»: la misma ruta que da el lanzador, para no repetir la instancia ni perder lo guardado
        carpeta = str(juego)
        nombre = juego.parent.name if juego.name.lower() in ("minecraft", ".minecraft") else juego.name
        tarjeta = self.lista.tarjeta_de(carpeta) or self.lista.agregar(nombre or carpeta, "Carpeta", carpeta)
        self._leer_datos([carpeta])
        self.lista.elegir(tarjeta)
        return True

    @staticmethod
    def carpetas_soltadas(datos: QMimeData) -> list[str]:
        rutas = [Path(u.toLocalFile()) for u in datos.urls() if u.isLocalFile()]
        return [str(r) for r in rutas if r.is_dir()]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._hilo is None and self.carpetas_soltadas(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        carpetas = self.carpetas_soltadas(event.mimeData())
        if self._hilo is not None or not carpetas:
            return
        event.acceptProposedAction()
        for carpeta in carpetas:
            self.agregar_carpeta(carpeta)

    # ------------------------------------------------------------------ motor y clave
    def motor_elegido(self) -> str:
        return str(self.c_motor.currentData())

    def abrir_motor(self) -> None:
        self.dialogo_motor.resultado.setText("")
        self.dialogo_motor.open()

    def _al_cerrar_motor(self, _resultado: int) -> None:
        self._actualizar_estado_clave()
        self._al_cambiar_opciones()

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
        self.dialogo_motor.formulario.setRowVisible(self.e_direccion, not es_gemini)
        self.dialogo_motor.mostrar_guia(motor)
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
        guardada = not fabrica.es_local(motor) and bool(configuracion.leer_clave(motor))
        if fabrica.es_local(motor):
            self.etiqueta_clave.setText("No hace falta: el modelo corre en tu PC")
        elif guardada:
            self.etiqueta_clave.setText("Guardada ✓")
        else:
            self.etiqueta_clave.setText("No guardada" if fabrica.necesita_clave(motor) else "Opcional")
        self._clave_lista = guardada or not fabrica.necesita_clave(motor)
        nombre = fabrica.MOTORES[motor].split(" (")[0]
        self.b_motor.setText(f"{nombre} · {'listo' if self._clave_lista else 'falta la clave'}")
        self.b_motor.setAccessibleName(f"Motor de traducción: {self.b_motor.text()}")
        self._pintar_motor()
        self._actualizar_pasos()

    def _pintar_motor(self) -> None:
        p = tema.actual()
        nombre, color = ("circle-check", p.acento) if self._clave_lista else ("triangle-alert", p.aviso)
        self.b_motor.setIcon(iconos.icono(nombre, color, 16))

    def _guardar_clave(self) -> None:
        motor = self.motor_elegido()
        nombre = fabrica.MOTORES[motor]
        donde = " de aistudio.google.com/apikey" if motor == fabrica.GEMINI else ""
        clave, ok = QInputDialog.getText(
            self.dialogo_motor, f"Clave de {nombre}", f"Pega tu clave{donde}:", QLineEdit.EchoMode.Password
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
            self._resultado_prueba(f"✖ {e}")
            return
        listar = getattr(motor, "listar_modelos", None)
        if not callable(listar):
            return
        self.b_probar.setEnabled(False)
        self._resultado_prueba(f"Comprobando la conexión con {fabrica.MOTORES[o['motor']]}…")
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

    def _resultado_prueba(self, texto: str) -> None:
        self.dialogo_motor.resultado.setText(texto)
        self.escribir(texto)

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
        self._resultado_prueba(f"✖ {mensaje}")

    def _modelos_listos(self, modelos: list[str]) -> None:
        self._fin_sondeo()
        if modelos:
            actual = self.c_modelo.currentText()
            self.c_modelo.clear()
            self.c_modelo.addItems([m for m in modelos if "tts" not in m and "image" not in m])
            por_defecto = MODELO_POR_DEFECTO if self.motor_elegido() == fabrica.GEMINI else modelos[0]
            self.c_modelo.setCurrentText(actual if actual in modelos else por_defecto)
            self._resultado_prueba(f"✓ Conexión correcta. {len(modelos)} modelos disponibles.")
        else:
            self._resultado_prueba("✓ Conexión correcta, pero el servidor no dio la lista: escribe el nombre a mano.")

    # ------------------------------------------------------------------ estado de la ventana
    def _grupos_elegidos(self) -> list[str]:
        return [g for g, t in self.grupos.items() if t.incluido]

    def informe_elegido(self) -> Informe | None:
        """El último análisis, solo con los grupos que siguen marcados (para el costo y el botón)."""
        if self.ultimo_informe is None:
            return None
        elegidos = set(self._grupos_elegidos())
        return Informe(modulos=[m for m in self.ultimo_informe.modulos if m.grupo in elegidos])

    def _al_cambiar_opciones(self, *_args: object) -> None:
        o = self.opciones()
        partes = [f"Español de {'España' if o['dialecto'] == 'es_es' else 'Latinoamérica'}",
                  f"velocidad {o['hilos']}"]  # fmt: skip
        if o["lotes"]:
            partes.append("más barato")
        if o["revisar"]:
            partes.append("con revisión")
        if not o["activar"]:
            partes.append("sin activar el pack")
        self.avanzadas.fijar_resumen(" · ".join(partes))
        if self._estado == "traducir":
            self.costo.setText(self._texto_costo())
        self._actualizar_principal()

    def _texto_costo(self) -> str:
        informe = self.informe_elegido()
        if informe is None:
            return ""
        o = self.opciones()
        texto = f"Para el motor: {_miles(informe.a_traducir)} textos, {_miles(informe.caracteres)} caracteres."
        costo = informe.costo(o["modelo"], o["lotes"], o["motor"], o["revisar"])
        if fabrica.es_local(o["motor"]):
            texto += " Sin costo: el modelo corre en tu PC."
        elif costo is not None:
            texto += f" Costo estimado con {o['modelo']}{' por lotes' if o['lotes'] else ''}: {_dinero(costo)}."
        elif o["motor"] != fabrica.GEMINI:
            texto += " El costo depende del proveedor y del modelo: revisa sus precios."
        return texto

    def _texto_traducir(self) -> str:
        informe = self.informe_elegido()
        if informe is None or not informe.a_traducir:
            return "Aplicar la traducción (ya está en la memoria)"
        o = self.opciones()
        costo = informe.costo(o["modelo"], o["lotes"], o["motor"], o["revisar"])
        precio = "" if costo is None else " · gratis" if costo == 0 else f" · {_dinero(costo)}"
        return f"Traducir {_miles(informe.a_traducir)} textos{precio}"

    def _actualizar_principal(self) -> None:
        trabajando = self._estado == "trabajando"
        self.barra.setVisible(trabajando)
        self.b_principal.setVisible(not trabajando)
        self.b_cancelar.setVisible(trabajando)
        self.b_secundario.setVisible(self._estado in ("traducir", "listo"))
        habilitado = True
        if self._estado == "listo":
            self.b_principal.fijar("Listo: abrir la carpeta", "folder-open")
        elif self._estado == "traducir":
            self.b_principal.fijar(self._texto_traducir(), "languages")
            informe = self.informe_elegido()
            habilitado = informe is not None and bool(informe.modulos)  # un grupo marcado pero vacío no cuenta
            if not habilitado:
                self.b_principal.fijar("Marca al menos un grupo para traducir", "languages")
        else:
            self.b_principal.fijar("Analizar (gratis)", "search")
        self.b_principal.setEnabled(habilitado and not trabajando)
        self._actualizar_pasos()

    def _actualizar_pasos(self) -> None:
        estado = self._antes if self._estado == "trabajando" else self._estado
        if not self._clave_lista:
            self.pasos.fijar(0)
        else:
            self.pasos.fijar({"analizar": 1, "traducir": 2, "listo": len(PASOS)}.get(estado, 1))

    def _accion_principal(self) -> None:
        if self._estado == "listo":
            self._abrir_carpeta()
        elif self._estado == "traducir":
            self._confirmar_traducir()
        elif self._estado == "analizar":
            self.lanzar("analizar")

    # ------------------------------------------------------------------ acciones
    def opciones(self) -> dict[str, Any]:
        return {
            "dialecto": self.c_dialecto.currentData(),
            "grupos": self._grupos_elegidos(),
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
            "texto_java": self.c_java.isChecked(),
            "exhaustivo": self.c_exhaustivo.isChecked(),
        }

    def _confirmar_traducir(self) -> None:
        motor = self.motor_elegido()
        if fabrica.necesita_clave(motor) and not configuracion.leer_clave(motor) and not self._es_prueba():
            self.avisar(f"Falta la clave de {fabrica.MOTORES[motor]}.", "aviso",
                        ("Configurar el motor", self.abrir_motor))  # fmt: skip
            return
        texto = (
            "Cierra Minecraft antes de seguir.\n\nLas misiones y scripts se guardan en una copia y puedes "
            "volver al original con «Más ▸ Restaurar el original»."
        )
        informe = self.informe_elegido()
        if informe is not None:
            o = self.opciones()
            costo = informe.costo(o["modelo"], o["lotes"], o["motor"], o["revisar"])
            if costo is not None:
                texto = f"Costo estimado: {_dinero(costo)}.\n\n" + texto
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
                self.avisar(str(e), "error", ("Configurar el motor", self.abrir_motor))
                return
        else:
            motor = Simulador()  # analizar y restaurar no llaman al motor
            if accion == "analizar":  # el análisis es gratis: se cuentan todos los grupos y luego se eligen
                opciones["grupos"] = list(GRUPOS)
        self._guardar_preferencias(carpeta)
        self._cancelar.clear()
        self.log.clear()
        self.aviso.ocultar()
        self.barra.setMaximum(0)  # sin total todavía: barra en movimiento
        self._inicio = None
        self._fase = ""
        self.estado.setText(
            {"analizar": "Analizando…", "traducir": "Preparando…", "cobertura": "Buscando texto en inglés…"}.get(
                accion, "Restaurando…"
            )
        )
        self._accion = accion
        self._antes = self._estado
        self._estado = "trabajando"
        self._ocupado(True)
        self._hilo = QThread(self)  # con padre: Qt lo libera junto con la ventana
        self._trabajador = Trabajador(accion, carpeta, opciones, motor, self._cancelar)
        self._trabajador.moveToThread(self._hilo)
        self._hilo.finished.connect(self._trabajador.deleteLater)
        self._hilo.started.connect(self._trabajador.ejecutar)
        self._trabajador.registro.connect(self._al_registro)
        self._trabajador.progreso.connect(self._progreso)
        self._trabajador.terminado.connect(self._terminar)
        self._trabajador.fallo.connect(self._fallar)
        self._hilo.start()

    def _ocupado(self, si: bool) -> None:
        for w in (self.lista, self.b_carpeta, self.b_actualizar, self.b_mas, self.b_motor, self.b_secundario,
                  self.e_contexto, self.avanzadas.contenido, self.bienvenida.b_configurar, self.a_motor,
                  *(t.casilla for t in self.grupos.values())):  # fmt: skip
            w.setEnabled(not si)
        self._actualizar_principal()

    def _al_registro(self, texto: str) -> None:
        if texto.startswith("▶ "):
            self._fase = texto[2:].split(":", maxsplit=1)[0]
        self.escribir(texto)

    def _progreso(self, hechos: int, total: int) -> None:
        ahora = time.monotonic()
        if self._inicio is None or self._inicio[1] != total or hechos == 0:
            self._inicio = (ahora, total)  # cada módulo cuenta desde cero
        self.barra.setMaximum(max(total, 1))
        self.barra.setValue(hechos)
        if self._accion == "cobertura":
            texto = f"Leyendo los mods… {_miles(hechos)} de {_miles(total)}"
        else:
            texto = f"Traduciendo{f' {self._fase}' if self._fase else ''}… {_miles(hechos)} de {_miles(total)}"
        pasado = ahora - self._inicio[0]
        if 0 < hechos < total and pasado > 3:
            texto += f" · quedan {_restante(pasado / hechos * (total - hechos))}"
        self.estado.setText(texto)

    def _limpiar_hilo(self) -> None:
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait()
            self._hilo.deleteLater()
        self._hilo = None
        self._trabajador = None
        self.barra.setMaximum(1)
        self.barra.setValue(0)

    def _terminar(self, resultado: object) -> None:
        accion = self._accion
        self._limpiar_hilo()
        if isinstance(resultado, Informe):
            self.ultimo_informe = resultado
            self._mostrar(resultado, hecho=accion == "traducir")
            if accion == "analizar":
                self._estado = "traducir"
                if not self.bienvenida.isHidden():
                    self.bienvenida.setVisible(False)
                    self._bienvenida_vista()
                self.estado.setText("Análisis listo. Elige qué traducir y pulsa el botón de abajo.")
            else:
                self._estado = "listo"
                self.estado.setText("¡Listo! Abre el juego: ya está en español.")
                self.aviso.mostrar("Traducción terminada. Abre Minecraft para verla.", "exito")
                self._marcar_traducida()
        elif accion == "cobertura":
            self._estado = self._antes  # no cambia nada en la instancia: el botón principal sigue como estaba
            self._mostrar_cobertura(cast("list[Hallazgo]", resultado))
        else:
            self._olvidar_analisis()  # el texto volvió al original: lo contado antes ya no vale
            n = len(resultado) if isinstance(resultado, list) else 0  # pyright: ignore[reportUnknownArgumentType]
            self.estado.setText(f"Restaurados {n} archivos.")
        self._ocupado(False)
        self._al_cambiar_opciones()
        self.escribir(self.estado.text())

    def _con_instancia(self, accion: Callable[[Instancia], str]) -> None:
        carpeta = self.carpeta()
        if not carpeta:
            self.avisar("Elige primero una instancia.")
            return
        try:
            with Instancia(carpeta) as inst:
                mensaje = accion(inst)
        except (ValueError, OSError) as e:
            self.avisar(str(e), "aviso", anotar=False)
            return
        self.escribir(mensaje)
        self.aviso.mostrar(mensaje, "exito")

    def _instalar_apoyo(self) -> None:
        self._con_instancia(
            lambda inst: (
                f"Mod de apoyo instalado: {mod_apoyo.instalar(inst).name}. Abre el juego para que empiece a actuar."
            )
        )

    def _quitar_apoyo(self) -> None:
        def quitar(inst: Instancia) -> str:
            quitados = mod_apoyo.quitar(inst)
            return "Quité: " + ", ".join(p.name for p in quitados) if quitados else "No había mod de apoyo instalado."

        self._con_instancia(quitar)

    def _comprobar_apoyo(self) -> None:
        self._con_instancia(lambda inst: "\n".join(mod_apoyo.estado(inst)))

    def _guardar_informe(self, destino: str | None = None) -> None:
        if not self.ultima_cobertura:
            self.avisar("Primero usa «Más ▸ Qué queda en inglés».")
            return
        if destino is None:
            destino, _ = QFileDialog.getSaveFileName(
                self, "Guardar el informe", str(Path.home() / "Que_queda_en_ingles.txt"), "Texto (*.txt)"
            )
        if not destino:
            return
        try:
            Path(destino).write_text(texto_del_informe(self.ultima_cobertura), encoding="utf-8")
        except OSError as e:
            self.avisar(f"No pude guardar el informe: {e}", "error")
            return
        self.aviso.mostrar(f"Informe guardado: {destino}", "exito")

    def _mostrar_cobertura(self, hallazgos: list[Hallazgo]) -> None:
        self.ultima_cobertura = hallazgos
        if not hallazgos:
            self.estado.setText("No encontré texto que se quede en inglés.")
            return
        self._dialogo_informe = DialogoInforme(texto_del_informe(hallazgos), self._guardar_informe, self)
        self._dialogo_informe.show()
        self.estado.setText(f"Quedan {len(hallazgos)} lugares con texto en inglés: el detalle está en Detalles.")
        self.escribir("Texto que se queda en inglés aunque traduzcas todo:")
        for h in hallazgos:
            self.escribir(f"· [{h.categoria}] {h}")
        self.escribir(
            "Lo de «java» está escrito en el código del mod: un resource pack no lo alcanza. "
            "Lo de «script» puede ser lógica y no un mensaje."
        )
        self.detalles.fijar_abierta(True)

    def _marcar_traducida(self) -> None:
        carpeta = self.carpeta()
        tarjeta = self.lista.actual()
        juego = resolver_carpeta_juego(Path(carpeta)) if carpeta else None
        if tarjeta is not None and juego is not None:
            tarjeta.fijar_traducida(traducida(juego))

    def _fallar(self, mensaje: str) -> None:
        registro.LOGGER.warning("Se detuvo: %s", mensaje)
        self._limpiar_hilo()
        self._estado = self._antes
        self._ocupado(False)
        self.estado.setText("Se detuvo.")
        self.escribir(f"✖ {mensaje}")
        cancelado = self._cancelar.is_set()  # lo pidió el jugador: no es un error
        if not cancelado:
            self.detalles.fijar_abierta(True)
        self.avisar(mensaje, "info" if cancelado else "error", anotar=False)

    def _mostrar(self, informe: Informe, hecho: bool) -> None:
        for g, tarjeta in self.grupos.items():
            modulos = [m for m in informe.modulos if m.grupo == g]
            if g in informe.fallidos:
                tarjeta.fijar_incluido(False)
                tarjeta.fijar_cantidad(None, "No se pudo leer: el motivo está en Detalles")
                continue
            if not modulos:
                tarjeta.fijar_cantidad(0, "No hay en esta instancia")
                continue
            if hecho:
                resumenes = "; ".join(str(m.resumen) for m in modulos if m.resumen)
                tarjeta.fijar_cantidad(sum(m.a_traducir for m in modulos), f"nuevos · {resumenes}")
            else:
                textos = sum(m.textos for m in modulos)
                que = " · ".join(m.descripcion for m in modulos if m.descripcion)
                tarjeta.fijar_cantidad(sum(m.a_traducir for m in modulos),
                                       f"por traducir, de {_miles(textos)}{f' · {que}' if que else ''}")  # fmt: skip
        self.costo.setText("" if hecho else self._texto_costo())
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
            self.avisar(str(e), "error")
            return
        self.escribir(f"Exportado: {destino} ({n} archivos)")
        self.aviso.mostrar(f"Exportado: {destino} ({n} archivos).", "exito")

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
            self.avisar("Todavía no hay nada en el registro.", "info")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))

    def avisar(
        self, texto: str, tipo: str = "aviso", accion: tuple[str, Callable[[], None]] | None = None, anotar: bool = True
    ) -> None:
        """Una franja de aviso arriba del contenido (no interrumpe con un cuadro); también queda en Detalles."""
        if anotar:
            self.escribir(f"[aviso] {texto}")
        self.aviso.mostrar(texto, tipo, accion)

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
            "revisar": o["revisar"], "texto_java": o["texto_java"], "exhaustivo": o["exhaustivo"],
            "avisar_version": self.c_avisar.isChecked(),
            "tema": self._preferencias.get("tema", "sistema"),
            "bienvenida_vista": bool(self._preferencias.get("bienvenida_vista", False)),
        }  # fmt: skip
        configuracion.guardar_preferencias(dict(self._preferencias))

    # ------------------------------------------------------------------ ajustes
    def elegir_tema(self, preferencia: str) -> None:
        instalado = tema.tema()
        if instalado is not None:
            instalado.elegir(preferencia)
        self._preferencias["tema"] = preferencia
        configuracion.guardar_preferencias(dict(self._preferencias))

    def _bienvenida_vista(self) -> None:
        self._preferencias["bienvenida_vista"] = True
        configuracion.guardar_preferencias(dict(self._preferencias))

    def _guardar_aviso(self, activo: bool) -> None:
        self._preferencias["avisar_version"] = activo
        configuracion.guardar_preferencias(dict(self._preferencias))

    # ------------------------------------------------------------------ versión nueva
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
        for lector in self._lectores:
            lector.parar.set()
        for lector in self._lectores:
            lector.esperar(2)  # que no quede avisando mientras Qt se cierra
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait(5000)
        event.accept()

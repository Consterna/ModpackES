"""Piezas reutilizables de la interfaz: tarjetas, pasos, avisos, secciones plegables y el botón principal.

Cada pieza marca su papel con la propiedad «tipo» y la hoja del tema la pinta; los íconos se vuelven a teñir
cuando cambia el tema (`seguir_tema`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import iconos, tema

Color = Callable[[tema.Paleta], str]
LOADERS = {"forge": "Forge", "neoforge": "NeoForge", "fabric": "Fabric", "quilt": "Quilt"}


class _Receptor(QObject):
    """Hijo del widget que recibe el cambio de tema: si el widget se destruye, Qt corta la conexión sola."""

    def __init__(self, dueno: QObject, callback: Callable[[], None]) -> None:
        super().__init__(dueno)
        self._callback = callback

    @Slot(object)
    def al_cambiar(self, _paleta: object) -> None:
        self._callback()


def seguir_tema(dueno: QObject, callback: Callable[[], None]) -> None:
    """Llama a `callback` ahora y cada vez que cambie el tema, mientras `dueno` exista."""
    callback()
    instalado = tema.tema()
    if instalado is not None:
        instalado.cambiado.connect(_Receptor(dueno, callback).al_cambiar)


def repintar(widget: QWidget) -> None:
    """Aplica de nuevo la hoja después de cambiar una propiedad que la hoja usa (p. ej. «activa»)."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def etiqueta(texto: str = "", tipo: str = "", ajustar: bool = False) -> QLabel:
    e = QLabel(texto)
    if tipo:
        e.setProperty("tipo", tipo)
    e.setWordWrap(ajustar)
    return e


def icono_en(destino: QLabel, nombre: str, color: Color, tam: int = 18) -> None:
    """Un ícono dentro de una etiqueta, teñido con un color del tema que se actualiza solo."""

    def pintar() -> None:
        destino.setPixmap(iconos.icono(nombre, color(tema.actual()), tam).pixmap(QSize(tam, tam)))

    destino.setProperty("icono", nombre)
    seguir_tema(destino, pintar)


def icono_en_boton(boton: QPushButton, nombre: str, color: Color | None = None, tam: int = 16) -> None:
    def pintar() -> None:
        p = tema.actual()
        boton.setIcon(iconos.icono(nombre, color(p) if color else p.texto, tam))
        boton.setIconSize(QSize(tam, tam))

    boton.setProperty("icono", nombre)
    seguir_tema(boton, pintar)


class Tarjeta(QFrame):
    """Un recuadro con borde redondeado; si es «elegible», responde al clic o al teclado y puede quedar activa."""

    pulsada = Signal()

    def __init__(self, elegible: bool = False, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setProperty("tipo", "tarjeta")
        self.setProperty("activa", False)
        self._elegible = elegible
        if elegible:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @property
    def activa(self) -> bool:
        return bool(self.property("activa"))

    def fijar_activa(self, activa: bool) -> None:
        if self.activa != activa:
            self.setProperty("activa", activa)
            repintar(self)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._elegible and event.button() == Qt.MouseButton.LeftButton:
            self.pulsada.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._elegible and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.pulsada.emit()
            return
        super().keyPressEvent(event)


class TarjetaInstancia(Tarjeta):
    """Una instancia en la barra lateral: nombre, versión, loader, lanzador y si ya está traducida."""

    def __init__(self, nombre: str, lanzador: str, ruta: str, padre: QWidget | None = None) -> None:
        super().__init__(elegible=True, padre=padre)
        self.nombre, self.lanzador, self.ruta = nombre, lanzador, ruta
        capa = QVBoxLayout(self)
        capa.setContentsMargins(10, 8, 10, 8)
        capa.setSpacing(2)
        self.e_nombre = etiqueta(nombre, "subtitulo")
        self.e_detalle = etiqueta(f"{lanzador} · leyendo…", "tenue", ajustar=True)
        self.e_estado = etiqueta("", "tenue")
        for e in (self.e_nombre, self.e_detalle, self.e_estado):
            capa.addWidget(e)
        self.e_estado.setVisible(False)  # hasta saber si está traducida
        self.setToolTip(ruta)
        self.setAccessibleName(f"Instancia {nombre}")
        self.version: str | None = None
        self.loader: str | None = None
        self.traducida: bool | None = None

    def fijar_datos(self, version: str | None, loader: str | None, traducida: bool | None) -> None:
        self.version, self.loader = version, loader
        partes = [p for p in (version or "versión desconocida", LOADERS.get(loader or "", loader), self.lanzador) if p]
        self.e_detalle.setText(" · ".join(partes))
        self.traducida = traducida
        self.e_estado.setVisible(traducida is not None)
        if traducida is None:
            self.e_estado.setText("")
        else:
            self.e_estado.setText("✓ Traducido" if traducida else "Sin traducir")
            self.e_estado.setProperty("tipo", "acento" if traducida else "tenue")
            repintar(self.e_estado)
        self.setAccessibleDescription(f"{self.e_detalle.text()}. {self.e_estado.text()}")

    def fijar_traducida(self, traducida: bool) -> None:
        self.fijar_datos(self.version, self.loader, traducida)

    def coincide(self, filtro: str) -> bool:
        f = filtro.strip().casefold()
        return not f or f in self.nombre.casefold() or f in self.lanzador.casefold()


class EtiquetaRuta(QLabel):
    """Una ruta que se acorta por el medio para caber en el ancho que haya; completa en el texto de ayuda."""

    def __init__(self, texto: str = "", tipo: str = "tenue", padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setProperty("tipo", tipo)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._completo = ""
        self.fijar(texto)

    def fijar(self, texto: str) -> None:
        self._completo = texto
        self.setToolTip(texto)
        self.setAccessibleName(texto)
        self._acortar()

    def texto_completo(self) -> str:
        return self._completo

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._acortar()

    def _acortar(self) -> None:
        ancho = max(self.width(), 40)
        self.setText(self.fontMetrics().elidedText(self._completo, Qt.TextElideMode.ElideMiddle, ancho))


class Pasos(QWidget):
    """La guía de pasos: los hechos con ✓ en agua marina, el actual resaltado y los que faltan en tenue."""

    def __init__(self, nombres: Sequence[str], padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.nombres = list(nombres)
        self.actual = 0
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(8)
        self._iconos: list[QLabel] = []
        self._textos: list[QLabel] = []
        for i, nombre in enumerate(self.nombres):
            if i:
                linea = QFrame()
                linea.setFrameShape(QFrame.Shape.HLine)
                linea.setProperty("tipo", "separador")
                linea.setFixedWidth(28)
                capa.addWidget(linea)
            icono_ = QLabel()
            texto = etiqueta(nombre)
            self._iconos.append(icono_)
            self._textos.append(texto)
            capa.addWidget(icono_)
            capa.addWidget(texto)
        capa.addStretch(1)
        seguir_tema(self, self._pintar)

    def fijar(self, actual: int) -> None:
        self.actual = max(0, min(actual, len(self.nombres)))
        self._pintar()

    def estado(self, i: int) -> str:
        """«hecho», «actual» o «pendiente»."""
        return "hecho" if i < self.actual else "actual" if i == self.actual else "pendiente"

    def _pintar(self) -> None:
        p = tema.actual()
        for i, (icono_, texto) in enumerate(zip(self._iconos, self._textos, strict=True)):
            estado = self.estado(i)
            nombre, color = {"hecho": ("circle-check", p.acento), "actual": ("circle-dot", p.morado),
                             "pendiente": ("circle", p.tenue)}[estado]  # fmt: skip
            icono_.setPixmap(iconos.icono(nombre, color, 16).pixmap(QSize(16, 16)))
            texto.setProperty("tipo", {"hecho": "acento", "actual": "subtitulo", "pendiente": "tenue"}[estado])
            repintar(texto)
        hecho = self.nombres[self.actual] if self.actual < len(self.nombres) else "terminado"
        self.setAccessibleName(f"Paso {min(self.actual + 1, len(self.nombres))} de {len(self.nombres)}: {hecho}")


class TarjetaGrupo(Tarjeta):
    """Un grupo de contenido (mods, libros, misiones, scripts) con su cantidad y un interruptor para incluirlo."""

    cambiado = Signal(str, bool)

    def __init__(self, grupo: str, titulo: str, nombre_icono: str, padre: QWidget | None = None) -> None:
        super().__init__(padre=padre)
        self.grupo = grupo
        capa = QVBoxLayout(self)
        capa.setContentsMargins(12, 10, 12, 10)
        capa.setSpacing(2)
        arriba = QHBoxLayout()
        self.e_icono = QLabel()
        icono_en(self.e_icono, nombre_icono, lambda p: p.acento, 20)
        self.casilla = QCheckBox()
        self.casilla.setChecked(True)
        self.casilla.setToolTip(f"Incluir {titulo.lower()} al traducir")
        self.casilla.setAccessibleName(f"Incluir {titulo.lower()}")
        self.casilla.toggled.connect(self._al_cambiar)
        arriba.addWidget(self.e_icono)
        arriba.addStretch(1)
        arriba.addWidget(self.casilla)
        capa.addLayout(arriba)
        self.e_numero = etiqueta("—", "numero")
        self.e_titulo = etiqueta(titulo)
        self.e_detalle = etiqueta("", "tenue", ajustar=True)
        for e in (self.e_numero, self.e_titulo, self.e_detalle):
            capa.addWidget(e)
        capa.addStretch(1)  # las tarjetas de una fila miden lo mismo: el texto queda arriba en todas
        self.fijar_activa(True)

    @property
    def incluido(self) -> bool:
        return self.casilla.isChecked()

    def fijar_incluido(self, si: bool) -> None:
        self.casilla.setChecked(si)

    def fijar_cantidad(self, por_traducir: int | None, detalle: str = "") -> None:
        """Cuántos textos faltan; None antes de analizar."""
        self.e_numero.setText("—" if por_traducir is None else f"{por_traducir:,}".replace(",", "."))
        self.e_detalle.setText(detalle)

    def _al_cambiar(self, si: bool) -> None:
        self.fijar_activa(si)
        self.cambiado.emit(self.grupo, si)


#: Tipo de aviso → (ícono, color de la paleta).
TIPOS_AVISO: dict[str, tuple[str, str]] = {
    "info": ("info", "morado"),
    "exito": ("circle-check", "acento"),
    "aviso": ("triangle-alert", "aviso"),
    "error": ("circle-alert", "peligro"),
}


class Aviso(QFrame):
    """Una franja de aviso dentro de la ventana (información, éxito, aviso o error), con una acción opcional."""

    cerrado = Signal()

    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.tipo = "info"
        capa = QHBoxLayout(self)
        capa.setContentsMargins(12, 8, 8, 8)
        self.e_icono = QLabel()
        self.e_texto = etiqueta("", ajustar=True)
        self.e_texto.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.b_accion = QPushButton()
        self.b_accion.setVisible(False)
        self.b_cerrar = QPushButton()
        self.b_cerrar.setProperty("tipo", "plano")
        self.b_cerrar.setAccessibleName("Cerrar aviso")
        self.b_cerrar.clicked.connect(self.ocultar)
        icono_en_boton(self.b_cerrar, "x", tam=14)
        capa.addWidget(self.e_icono)
        capa.addWidget(self.e_texto, 1)
        capa.addWidget(self.b_accion)
        capa.addWidget(self.b_cerrar)
        self._accion: Callable[[], None] | None = None
        self.b_accion.clicked.connect(self._hacer_accion)
        seguir_tema(self, self._pintar)
        self.setVisible(False)

    def mostrar(self, texto: str, tipo: str = "info", accion: tuple[str, Callable[[], None]] | None = None) -> None:
        self.tipo = tipo if tipo in TIPOS_AVISO else "info"
        self.e_texto.setText(texto)
        self._accion = accion[1] if accion else None
        self.b_accion.setText(accion[0] if accion else "")
        self.b_accion.setVisible(accion is not None)
        self.setProperty("tipo", f"aviso-{self.tipo}")
        self.setAccessibleName(f"Aviso: {texto}")
        self._pintar()
        repintar(self)
        self.setVisible(True)

    def ocultar(self) -> None:
        self.setVisible(False)
        self.cerrado.emit()

    def _hacer_accion(self) -> None:
        if self._accion is not None:
            self._accion()

    def _pintar(self) -> None:
        nombre, clave = TIPOS_AVISO[self.tipo]
        color = str(getattr(tema.actual(), clave))
        self.e_icono.setPixmap(iconos.icono(nombre, color, 18).pixmap(QSize(18, 18)))


class Plegable(QWidget):
    """Una sección que se abre y se cierra, con un resumen visible cuando está cerrada."""

    alternada = Signal(bool)

    def __init__(self, titulo: str, contenido: QWidget, abierta: bool = False, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.titulo = titulo
        self.contenido = contenido
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(6)
        self.cabecera = QPushButton()
        self.cabecera.setProperty("tipo", "plano")
        self.cabecera.setCheckable(True)
        self.cabecera.setChecked(abierta)
        self.cabecera.setStyleSheet("text-align: left;")
        self.cabecera.toggled.connect(self._al_alternar)
        capa.addWidget(self.cabecera)
        capa.addWidget(contenido)
        self._resumen = ""
        seguir_tema(self, self._pintar)
        self._al_alternar(abierta)

    @property
    def abierta(self) -> bool:
        return self.cabecera.isChecked()

    def fijar_abierta(self, si: bool) -> None:
        self.cabecera.setChecked(si)

    def fijar_resumen(self, texto: str) -> None:
        self._resumen = texto
        self._pintar()

    def _al_alternar(self, abierta: bool) -> None:
        self.contenido.setVisible(abierta)
        self._pintar()
        self.alternada.emit(abierta)

    def _pintar(self) -> None:
        abierta = self.cabecera.isChecked()
        extra = "" if abierta or not self._resumen else f"   ·   {self._resumen}"
        self.cabecera.setText(f"{self.titulo}{extra}")
        self.cabecera.setAccessibleName(f"{self.titulo}, {'abierta' if abierta else 'cerrada'}")
        nombre = "chevron-down" if abierta else "chevron-right"
        self.cabecera.setIcon(iconos.icono(nombre, tema.actual().tenue, 14))
        self.cabecera.setIconSize(QSize(14, 14))


class BotonPrincipal(QPushButton):
    """El botón de la acción principal del momento, en agua marina. Cambia de texto e ícono según el paso."""

    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setProperty("tipo", "primario")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.nombre_icono = ""
        seguir_tema(self, self._pintar)

    def fijar(self, texto: str, nombre_icono: str) -> None:
        self.setText(texto)
        self.setAccessibleName(texto)
        self.nombre_icono = nombre_icono
        self._pintar()

    def _pintar(self) -> None:
        if self.nombre_icono:
            self.setIcon(iconos.icono(self.nombre_icono, tema.actual().sobre_acento, 18))
            self.setIconSize(QSize(18, 18))

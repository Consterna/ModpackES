"""Piezas reutilizables de la interfaz: tarjetas, pasos, avisos, secciones plegables y el botón principal.

Cada pieza marca su papel con la propiedad «tipo» y la hoja del tema la pinta; los íconos se vuelven a teñir
cuando cambia el tema (`seguir_tema`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
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


def solo_texto(raiz: QWidget, excepto: Iterable[QLabel] = ()) -> None:
    """Las etiquetas de `raiz` muestran su texto tal cual, sin interpretarlo como HTML.

    QLabel dibuja como HTML lo que «parece» HTML: un modpack llamado `<img src=…>` o un mensaje de un servidor con
    etiquetas alterarían la ventana. Solo las de `excepto` (créditos y aviso de versión nueva) llevan enlaces.
    """
    dejar = {id(e) for e in excepto}
    for e in raiz.findChildren(QLabel):
        if id(e) not in dejar:
            e.setTextFormat(Qt.TextFormat.PlainText)


def etiqueta(texto: str = "", tipo: str = "", ajustar: bool = False, enriquecida: bool = False) -> QLabel:
    """`enriquecida`: solo para textos propios con enlaces; lo demás (que puede venir del modpack) va tal cual."""
    e = QLabel(texto)
    e.setTextFormat(Qt.TextFormat.RichText if enriquecida else Qt.TextFormat.PlainText)
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
        self.e_nombre = EtiquetaRuta(nombre, "subtitulo", modo=Qt.TextElideMode.ElideRight)
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
    """Un texto de una línea que se acorta («…») para caber en el ancho que haya; completo en el texto de ayuda.

    Una ruta se acorta por el medio (se ven la unidad y la carpeta final); un nombre, por el final. Nunca pide más
    ancho que el que hay: un nombre largo no puede ensanchar la barra ni el panel.
    """

    def __init__(
        self,
        texto: str = "",
        tipo: str = "tenue",
        padre: QWidget | None = None,
        modo: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle,
    ) -> None:
        super().__init__(padre)
        self.setTextFormat(Qt.TextFormat.PlainText)  # una ruta o un nombre del modpack nunca es HTML
        self.setProperty("tipo", tipo)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._modo = modo
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
        self.setText(self.fontMetrics().elidedText(self._completo, self._modo, ancho))

    def minimumSizeHint(self) -> QSize:
        return QSize(40, super().minimumSizeHint().height())


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
                linea.setMinimumWidth(8)  # en una ventana angosta las rayas se achican; el texto no
                linea.setMaximumWidth(28)
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
        # El resumen se acorta con «…» al ancho que haya: con muchas opciones ensanchaba el panel y lo cortaba
        self.cabecera.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
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

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._pintar()

    def texto_completo(self) -> str:
        abierta = self.cabecera.isChecked()
        extra = "" if abierta or not self._resumen else f"   ·   {self._resumen}"
        return f"{self.titulo}{extra}"

    def _pintar(self) -> None:
        abierta = self.cabecera.isChecked()
        completo = self.texto_completo()
        disponible = self.cabecera.width() - 14 - 28  # el ícono y los márgenes del botón
        texto = completo
        if self.cabecera.width() > 0:
            texto = self.cabecera.fontMetrics().elidedText(completo, Qt.TextElideMode.ElideRight, max(disponible, 80))
        self.cabecera.setText(texto)
        self.cabecera.setToolTip(completo if texto != completo else "")
        self.cabecera.setAccessibleName(f"{self.titulo}, {'abierta' if abierta else 'cerrada'}")
        nombre = "chevron-down" if abierta else "chevron-right"
        self.cabecera.setIcon(iconos.icono(nombre, tema.actual().tenue, 14))
        self.cabecera.setIconSize(QSize(14, 14))


class FilaAcciones(QWidget):
    """La acción principal y, a su lado, las secundarias. Si no caben en una línea, las secundarias bajan a otra fila.

    El panel no tiene barra horizontal: una fila más ancha que la ventana dejaba botones cortados (H-047).
    """

    def __init__(
        self, principales: Sequence[QWidget], secundarias: Sequence[QWidget], padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self._principales = list(principales)
        self._secundarias = list(secundarias)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(10)
        capa.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)  # el mínimo lo da `minimumSizeHint`
        self._arriba = QHBoxLayout()
        self._abajo = QHBoxLayout()
        for fila in (self._arriba, self._abajo):
            fila.setSpacing(10)
            capa.addLayout(fila)
        self.dos_filas: bool | None = None
        self._acomodar(False)

    def _visibles(self, lista: Sequence[QWidget]) -> list[QWidget]:
        return [w for w in lista if not w.isHidden()]

    def _ancho_en_una_fila(self) -> int:
        visibles = self._visibles([*self._principales, *self._secundarias])
        return sum(w.sizeHint().width() for w in visibles) + 10 * max(len(visibles) - 1, 0)

    def _acomodar(self, dos_filas: bool) -> None:
        if dos_filas == self.dos_filas:
            return
        self.dos_filas = dos_filas
        for fila in (self._arriba, self._abajo):
            while fila.count():
                fila.takeAt(0)
        for w in self._principales:
            self._arriba.addWidget(w)
        destino = self._abajo if dos_filas else self._arriba
        *izquierda, derecha = self._secundarias
        for w in izquierda:
            destino.addWidget(w)
        destino.addStretch(1)
        destino.addWidget(derecha)
        if not dos_filas:
            self._abajo.addStretch(1)
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        visibles = self._visibles([*self._principales, *self._secundarias])
        ancho = max((w.minimumSizeHint().width() for w in visibles), default=0)
        return QSize(ancho, super().minimumSizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._acomodar(self._ancho_en_una_fila() > event.size().width())
        super().resizeEvent(event)

    def event(self, evento: QEvent) -> bool:
        if evento.type() == QEvent.Type.LayoutRequest:  # un botón cambió de texto o se mostró: puede que ya no quepa
            self._acomodar(self._ancho_en_una_fila() > self.width())
        return super().event(evento)


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

    def minimumSizeHint(self) -> QSize:
        """Puede ser más angosto que su texto: se dibuja acortado con «…» (el texto y el nombre accesible quedan
        enteros). Si no, en una ventana angosta o con una escala grande, el botón ensanchaba el panel y se cortaba."""
        base = super().minimumSizeHint()
        return QSize(min(base.width(), 160), base.height())

    def paintEvent(self, event: QPaintEvent) -> None:
        opcion = QStyleOptionButton()
        self.initStyleOption(opcion)
        pide = self.sizeHint().width()
        if pide > self.width():
            resto = pide - self.fontMetrics().horizontalAdvance(self.text())  # ícono, márgenes y relleno
            opcion.text = self.fontMetrics().elidedText(
                self.text(), Qt.TextElideMode.ElideRight, max(self.width() - resto, 20)
            )
        pintor = QStylePainter(self)
        pintor.drawControl(QStyle.ControlElement.CE_PushButton, opcion)

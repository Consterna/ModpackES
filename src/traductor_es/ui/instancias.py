"""La barra lateral de instancias: tarjetas con buscador, y la lectura de versión y loader en segundo plano."""

from __future__ import annotations

import threading
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from ..fuentes.deteccion import detectar
from ..fuentes.instancia import resolver_carpeta_juego
from ..salida.resource_pack import NOMBRE as NOMBRE_PACK
from .componentes import TarjetaInstancia, etiqueta

#: (versión de Minecraft, loader, ya traducida); None donde no se pudo saber
Datos = tuple[str | None, str | None, bool | None]


def traducida(juego: Path) -> bool:
    return (juego / "resourcepacks" / NOMBRE_PACK / "pack.mcmeta").is_file()


def leer_datos(carpeta: str) -> Datos:
    """Lo que muestra la tarjeta. Solo lee metadatos y nombres de archivo: no abre la instancia entera."""
    juego = resolver_carpeta_juego(Path(carpeta))
    if juego is None:
        return None, None, None
    try:
        mods = juego / "mods"
        jars = sorted(p for p in mods.iterdir() if p.is_file() and p.suffix.lower() in (".jar", ".zip")) \
            if mods.is_dir() else []  # fmt: skip
        d = detectar(juego, jars)
        return (d.version.texto if d.version else None), d.loader, traducida(juego)
    except OSError:
        return None, None, None


class Lector(QObject):
    """Lee los datos de cada instancia en un hilo y los avisa de a uno (la ventana no espera)."""

    leido = Signal(str, object)

    def __init__(self, carpetas: Iterable[str]) -> None:
        super().__init__()
        self.carpetas = list(carpetas)
        self.parar = threading.Event()
        self.terminado = threading.Event()
        self._hilo: threading.Thread | None = None

    def ejecutar(self) -> None:
        try:
            for carpeta in self.carpetas:
                if self.parar.is_set():
                    return
                try:
                    datos = leer_datos(carpeta)
                except Exception:  # una instancia rara no puede cortar la lectura de las demás
                    datos = (None, None, None)
                self.leido.emit(carpeta, datos)
        finally:
            self.terminado.set()

    def iniciar(self) -> threading.Thread:
        """Un hilo de Python, sin padre: si la ventana se cierra antes, Qt corta la conexión y el aviso se pierde."""
        hilo = threading.Thread(target=self.ejecutar, name="leer-instancias", daemon=True)
        hilo.start()
        self._hilo = hilo
        return hilo

    def esperar(self, segundos: float) -> None:
        if self._hilo is not None:
            self._hilo.join(segundos)


class ListaInstancias(QWidget):
    """Buscador y tarjetas. `elegida` avisa la carpeta de la tarjeta elegida (o "" si no queda ninguna)."""

    elegida = Signal(str)

    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(8)
        self.e_buscar = QLineEdit()
        self.e_buscar.setPlaceholderText("Buscar instancia…  (Ctrl+F)")
        self.e_buscar.setAccessibleName("Buscar instancia")
        self.e_buscar.setClearButtonEnabled(True)
        self.e_buscar.textChanged.connect(self.filtrar)
        self.e_buscar.installEventFilter(self)  # flecha abajo desde el buscador: a la primera instancia
        capa.addWidget(self.e_buscar)
        self._contenido = QWidget()
        self._capa = QVBoxLayout(self._contenido)
        self._capa.setContentsMargins(0, 0, 4, 0)
        self._capa.setSpacing(6)
        self._capa.addStretch(1)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setWidget(self._contenido)
        self._desplazable = desplazable
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        capa.addWidget(desplazable, 1)
        self.vacio: QLabel = etiqueta(
            "No encontré instancias. Arrastra aquí la carpeta de tu modpack o pulsa «Elegir carpeta…».", "tenue", True
        )
        self._capa.insertWidget(0, self.vacio)
        self.tarjetas: list[TarjetaInstancia] = []
        self._actual: TarjetaInstancia | None = None

    # ------------------------------------------------------------------ contenido
    def limpiar(self) -> None:
        self.elegir(None)
        for t in self.tarjetas:
            t.setParent(None)
            t.deleteLater()
        self.tarjetas = []
        self._actual = None
        self.vacio.setVisible(True)

    def agregar(self, nombre: str, lanzador: str, carpeta: str) -> TarjetaInstancia:
        t = TarjetaInstancia(nombre, lanzador, carpeta)
        t.pulsada.connect(lambda: self.elegir(t))
        t.installEventFilter(self)
        self._capa.insertWidget(self._capa.count() - 1, t)
        self.tarjetas.append(t)
        self.vacio.setVisible(False)
        t.setVisible(t.coincide(self.e_buscar.text()))
        return t

    def fijar_datos(self, carpeta: str, datos: Datos) -> None:
        for t in self.tarjetas:
            if t.ruta == carpeta:
                t.fijar_datos(*datos)

    def tarjeta_de(self, carpeta: str) -> TarjetaInstancia | None:
        return next((t for t in self.tarjetas if t.ruta == carpeta), None)

    # ------------------------------------------------------------------ elección
    def count(self) -> int:
        return len(self.tarjetas)

    def actual(self) -> TarjetaInstancia | None:
        return self._actual

    def carpeta(self) -> str | None:
        return self._actual.ruta if self._actual else None

    def setCurrentRow(self, fila: int) -> None:  # el mismo nombre que en QListWidget
        self.elegir(self.tarjetas[fila] if 0 <= fila < len(self.tarjetas) else None)

    def elegir(self, tarjeta: TarjetaInstancia | None) -> None:
        if tarjeta is self._actual:
            return
        for t in self.tarjetas:
            t.fijar_activa(t is tarjeta)
        self._actual = tarjeta
        self.elegida.emit(tarjeta.ruta if tarjeta else "")

    def mover(self, paso: int) -> None:
        """Elige la instancia visible anterior (-1) o siguiente (+1) y le pasa el foco."""
        visibles = [t for t in self.tarjetas if not t.isHidden()]
        if not visibles:
            return
        i = visibles.index(self._actual) if self._actual in visibles else -1
        destino = visibles[max(0, min(len(visibles) - 1, i + paso))]
        self.elegir(destino)
        destino.setFocus()
        self._desplazable.ensureWidgetVisible(destino)

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:
        """El área desplazable se queda con las flechas: se atienden antes, en las tarjetas y el buscador."""
        if evento.type() == QEvent.Type.KeyPress and isinstance(evento, QKeyEvent):
            tecla = evento.key()
            if tecla == Qt.Key.Key_Down:
                self.mover(1)
                return True
            if tecla == Qt.Key.Key_Up and objeto is not self.e_buscar:
                self.mover(-1)
                return True
        return super().eventFilter(objeto, evento)

    def filtrar(self, texto: str) -> None:
        for t in self.tarjetas:  # la elegida se sigue viendo: si no, el botón actuaría sobre una que no está
            t.setVisible(t.coincide(texto) or t is self._actual)
        visibles = [t for t in self.tarjetas if t.isVisibleTo(self._contenido)]
        self.vacio.setText(
            "Ninguna instancia coincide con la búsqueda." if self.tarjetas
            else "No encontré instancias. Arrastra aquí la carpeta de tu modpack o pulsa «Elegir carpeta…»."
        )  # fmt: skip
        self.vacio.setVisible(not visibles)

    @Slot(str, object)
    def al_leer(self, carpeta: str, datos: object) -> None:
        if isinstance(datos, tuple):
            self.fijar_datos(carpeta, datos)  # pyright: ignore[reportUnknownArgumentType]

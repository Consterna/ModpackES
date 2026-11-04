"""Tema visual: paleta agua marina y morado, en oscuro y en claro, aplicada con Fusion, QPalette y una hoja QSS.

El estilo nativo de Windows no usa la paleta para dibujar los controles, así que la app usa Fusion y le da
una paleta completa; la hoja QSS sale de los mismos colores. Con la preferencia «sistema» sigue el modo de
Windows mientras la app está abierta.

Los widgets marcan su papel con la propiedad dinámica «tipo» (por ejemplo `primario`, `tarjeta`, `tenue`) y
la hoja los pinta según ese papel, para que el aspecto viva en un solo lugar.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

MODOS = ("sistema", "oscuro", "claro")
FUENTE = '"Segoe UI Variable Text", "Segoe UI", sans-serif'


@dataclass(frozen=True, slots=True)
class Paleta:
    nombre: str
    fondo: str  #: ventana
    lateral: str  #: barra de instancias
    tarjeta: str  #: tarjetas, campos y menús
    tarjeta_activa: str  #: tarjeta con el puntero encima o elegida
    borde: str  #: líneas finas decorativas
    borde_control: str  #: borde de campos y casillas (tiene que distinguirse: 3:1)
    texto: str
    tenue: str  #: texto secundario
    acento: str  #: agua marina: acción principal, progreso, «listo»
    acento_activo: str
    sobre_acento: str  #: texto encima del acento
    morado: str  #: selección, foco e insignias
    morado_suave: str  #: fondo de lo elegido
    peligro: str
    aviso: str
    fondo_peligro: str
    fondo_aviso: str
    fondo_exito: str
    fondo_info: str


OSCURO = Paleta(
    nombre="oscuro",
    fondo="#100F1A",
    lateral="#141325",
    tarjeta="#1A1830",
    tarjeta_activa="#232041",
    borde="#2A2842",
    borde_control="#6E6A9C",
    texto="#ECEAF6",
    tenue="#A29EC2",
    acento="#2EF5C9",
    acento_activo="#7CFBDD",
    sobre_acento="#04211A",
    morado="#A78BFA",
    morado_suave="#2B2350",
    peligro="#FF6B7F",
    aviso="#FFC857",
    fondo_peligro="#3A1622",
    fondo_aviso="#3A2D10",
    fondo_exito="#0E3A31",
    fondo_info="#24204A",
)

CLARO = Paleta(
    nombre="claro",
    fondo="#F6F5FB",
    lateral="#EEECF7",
    tarjeta="#FFFFFF",
    tarjeta_activa="#ECE8FB",
    borde="#DCD9EA",
    borde_control="#8682A8",
    texto="#1B1930",
    tenue="#55516F",
    acento="#087A63",
    acento_activo="#06644F",
    sobre_acento="#FFFFFF",
    morado="#6246D0",
    morado_suave="#E6E0FB",
    peligro="#B8263D",
    aviso="#7A4F00",
    fondo_peligro="#FBE7EA",
    fondo_aviso="#FCF0D9",
    fondo_exito="#DDF5EE",
    fondo_info="#ECE8FB",
)


# ---------------------------------------------------------------------- contraste (WCAG 2.2)
def _canal(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def luminancia(hexa: str) -> float:
    color = QColor(hexa)
    r, g, b = _canal(color.red()), _canal(color.green()), _canal(color.blue())
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    """Relación de contraste WCAG entre dos colores: de 1 (igual) a 21 (negro sobre blanco)."""
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


#: Pares que la app pone uno sobre otro y el mínimo que piden las WCAG: 4,5 para texto y 3 para controles.
PARES: tuple[tuple[str, str, float], ...] = (
    ("texto", "fondo", 4.5), ("texto", "lateral", 4.5), ("texto", "tarjeta", 4.5), ("texto", "tarjeta_activa", 4.5),
    ("tenue", "fondo", 4.5), ("tenue", "lateral", 4.5), ("tenue", "tarjeta", 4.5),
    ("sobre_acento", "acento", 4.5), ("sobre_acento", "acento_activo", 4.5),
    ("acento", "fondo", 4.5), ("acento", "tarjeta", 4.5), ("morado", "fondo", 4.5), ("morado", "tarjeta", 4.5),
    ("texto", "morado_suave", 4.5), ("peligro", "fondo", 4.5), ("aviso", "fondo", 4.5),
    ("texto", "fondo_peligro", 4.5), ("texto", "fondo_aviso", 4.5), ("texto", "fondo_exito", 4.5),
    ("texto", "fondo_info", 4.5),
    ("borde_control", "fondo", 3.0), ("borde_control", "tarjeta", 3.0), ("acento", "lateral", 3.0),
)  # fmt: skip


def pares_insuficientes(p: Paleta) -> list[str]:
    valores = {f.name: getattr(p, f.name) for f in fields(p)}
    return [
        f"{a} sobre {b}: {contraste(valores[a], valores[b]):.2f} (mínimo {m})"
        for a, b, m in PARES
        if contraste(valores[a], valores[b]) < m
    ]


# ---------------------------------------------------------------------- aplicar
def paleta_qt(p: Paleta) -> QPalette:
    pal = QPalette()
    grupos = (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive)
    papeles = {
        QPalette.ColorRole.Window: p.fondo,
        QPalette.ColorRole.WindowText: p.texto,
        QPalette.ColorRole.Base: p.tarjeta,
        QPalette.ColorRole.AlternateBase: p.lateral,
        QPalette.ColorRole.Text: p.texto,
        QPalette.ColorRole.Button: p.tarjeta,
        QPalette.ColorRole.ButtonText: p.texto,
        QPalette.ColorRole.Highlight: p.morado,
        QPalette.ColorRole.HighlightedText: p.fondo,
        QPalette.ColorRole.ToolTipBase: p.tarjeta_activa,
        QPalette.ColorRole.ToolTipText: p.texto,
        QPalette.ColorRole.PlaceholderText: p.tenue,
        QPalette.ColorRole.Link: p.acento,
        QPalette.ColorRole.LinkVisited: p.morado,
        QPalette.ColorRole.BrightText: p.peligro,
        QPalette.ColorRole.Accent: p.acento,
    }
    for grupo in grupos:
        for papel, color in papeles.items():
            pal.setColor(grupo, papel, QColor(color))
    for papel in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, papel, QColor(p.tenue))
    return pal


def recursos(p: Paleta) -> dict[str, str]:
    """Íconos teñidos que usa la hoja (marca de las casillas, flechas), en una carpeta temporal.

    La QSS solo admite imágenes desde archivos: se escriben una vez por paleta y solo si cambiaron.
    """
    carpeta = Path(tempfile.gettempdir()) / "modpackes-tema" / p.nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    origen = Path(__file__).with_name("iconos")
    pedidos = {"marca": ("check", p.sobre_acento, "3"), "abajo": ("chevron-down", p.tenue, "2"),
               "arriba": ("chevron-up", p.tenue, "2")}  # fmt: skip
    salida: dict[str, str] = {}
    for clave, (nombre, color, grosor) in pedidos.items():
        datos = (origen / f"{nombre}.svg").read_bytes()
        datos = datos.replace(b"currentColor", color.encode()).replace(
            b'stroke-width="2"', f'stroke-width="{grosor}"'.encode()
        )
        destino = carpeta / f"{clave}.svg"
        if not destino.is_file() or destino.read_bytes() != datos:
            destino.write_bytes(datos)
        salida[clave] = destino.as_posix()
    return salida


def hoja(p: Paleta, imagenes: Mapping[str, str] | None = None) -> str:
    """La hoja QSS de toda la app, con los colores de la paleta."""
    r = imagenes if imagenes is not None else recursos(p)
    return f"""
* {{ font-family: {FUENTE}; font-size: 10pt; }}
QWidget {{ color: {p.texto}; }}
QMainWindow, QDialog {{ background: {p.fondo}; }}
QToolTip {{ background: {p.tarjeta_activa}; color: {p.texto}; border: 1px solid {p.borde}; padding: 4px 6px; }}
QLabel[tipo="titulo"] {{ font-size: 14pt; font-weight: 600; }}
QLabel[tipo="subtitulo"] {{ font-size: 11pt; font-weight: 600; }}
QLabel[tipo="tenue"] {{ color: {p.tenue}; }}
QLabel[tipo="numero"] {{ font-size: 16pt; font-weight: 600; }}
QLabel[tipo="acento"] {{ color: {p.acento}; }}
QLabel a {{ color: {p.acento}; }}
QFrame[tipo="lateral"] {{ background: {p.lateral}; border-right: 1px solid {p.borde}; }}
QFrame[tipo="barra"] {{ background: {p.fondo}; border-bottom: 1px solid {p.borde}; }}
QFrame[tipo="tarjeta"] {{ background: {p.tarjeta}; border: 1px solid {p.borde}; border-radius: 10px; }}
QFrame[tipo="tarjeta"][activa="true"] {{ background: {p.tarjeta_activa}; border: 1px solid {p.morado}; }}
QFrame[tipo="aviso-info"] {{ background: {p.fondo_info}; border: 1px solid {p.morado}; border-radius: 8px; }}
QFrame[tipo="aviso-exito"] {{ background: {p.fondo_exito}; border: 1px solid {p.acento}; border-radius: 8px; }}
QFrame[tipo="aviso-aviso"] {{ background: {p.fondo_aviso}; border: 1px solid {p.aviso}; border-radius: 8px; }}
QFrame[tipo="aviso-error"] {{ background: {p.fondo_peligro}; border: 1px solid {p.peligro}; border-radius: 8px; }}
QPushButton {{ background: {p.tarjeta}; border: 1px solid {p.borde_control}; border-radius: 8px; padding: 6px 12px; }}
QPushButton:hover {{ background: {p.tarjeta_activa}; }}
QPushButton:pressed {{ background: {p.morado_suave}; }}
QPushButton:focus {{ border: 1px solid {p.morado}; }}
QPushButton:disabled {{ color: {p.tenue}; border-color: {p.borde}; }}
QPushButton[tipo="primario"] {{ background: {p.acento}; color: {p.sobre_acento}; border: 1px solid {p.acento};
    font-weight: 600; padding: 9px 18px; font-size: 11pt; }}
QPushButton[tipo="primario"]:hover {{ background: {p.acento_activo}; border-color: {p.acento_activo}; }}
QPushButton[tipo="primario"]:focus {{ border: 2px solid {p.morado}; }}
QPushButton[tipo="primario"]:disabled {{ background: {p.borde}; color: {p.tenue}; border-color: {p.borde}; }}
QPushButton[tipo="peligro"] {{ color: {p.peligro}; border-color: {p.peligro}; }}
QPushButton[tipo="plano"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[tipo="plano"]:hover {{ background: {p.tarjeta_activa}; }}
QPushButton[tipo="ficha"] {{ background: {p.tarjeta}; border: 1px solid {p.borde}; border-radius: 14px; padding: 4px 12px; }}
QPushButton::menu-indicator {{ subcontrol-position: right center; right: 6px; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{ background: {p.tarjeta}; border: 1px solid {p.borde_control};
    border-radius: 8px; padding: 5px 8px; selection-background-color: {p.morado}; selection-color: {p.fondo}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {p.morado}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none; }}
QComboBox::down-arrow {{ image: url({r["abajo"]}); width: 14px; height: 14px; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 22px; border: none; background: transparent; }}
QSpinBox::up-arrow {{ image: url({r["arriba"]}); width: 12px; height: 12px; }}
QSpinBox::down-arrow {{ image: url({r["abajo"]}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {p.tarjeta}; border: 1px solid {p.borde}; selection-background-color: {p.morado_suave};
    selection-color: {p.texto}; outline: 0; }}
QPlainTextEdit[tipo="registro"] {{ font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p.borde_control}; border-radius: 4px; background: {p.tarjeta}; }}
QCheckBox::indicator:checked {{ background: {p.acento}; border-color: {p.acento}; image: url({r["marca"]}); }}
QCheckBox::indicator:focus {{ border-color: {p.morado}; }}
QProgressBar {{ background: {p.borde}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {p.acento}; border-radius: 4px; }}
QListWidget, QTableWidget, QTreeView {{ background: {p.tarjeta}; border: 1px solid {p.borde}; border-radius: 8px;
    alternate-background-color: {p.lateral}; outline: 0; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {p.morado_suave}; color: {p.texto}; }}
QHeaderView::section {{ background: {p.lateral}; color: {p.tenue}; border: none; border-bottom: 1px solid {p.borde}; padding: 6px; }}
QMenu {{ background: {p.tarjeta}; border: 1px solid {p.borde}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 10px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.morado_suave}; }}
QMenu::separator {{ height: 1px; background: {p.borde}; margin: 4px 8px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.borde_control}; border-radius: 4px; min-height: 24px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.borde_control}; border-radius: 4px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; }}
QSplitter::handle {{ background: {p.borde}; }}
QGroupBox {{ border: 1px solid {p.borde}; border-radius: 10px; margin-top: 12px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {p.tenue}; }}
"""


class Tema(QObject):
    """Mantiene el tema de la app al día con la preferencia y, si es «sistema», con el modo de Windows."""

    cambiado = Signal(object)  #: la Paleta nueva

    def __init__(self, app: QApplication, preferencia: str = "sistema") -> None:
        super().__init__(app)
        self._app = app
        self.preferencia = preferencia if preferencia in MODOS else "sistema"
        self.paleta = OSCURO
        self.estilo = app.setStyle("Fusion")
        app.styleHints().colorSchemeChanged.connect(self._al_cambiar_sistema)
        self.aplicar()

    def esquema_sistema(self) -> Qt.ColorScheme:
        """El modo de Windows (claro u oscuro); «Unknown» si la plataforma no lo informa."""
        return QGuiApplication.styleHints().colorScheme()

    def efectiva(self) -> Paleta:
        if self.preferencia == "oscuro":
            return OSCURO
        if self.preferencia == "claro":
            return CLARO
        return CLARO if self.esquema_sistema() == Qt.ColorScheme.Light else OSCURO  # sin dato del sistema: oscuro

    def elegir(self, preferencia: str) -> None:
        self.preferencia = preferencia if preferencia in MODOS else "sistema"
        self.aplicar()

    def aplicar(self) -> None:
        self.paleta = self.efectiva()
        self._app.setPalette(paleta_qt(self.paleta))
        self._app.setStyleSheet(hoja(self.paleta))
        self.cambiado.emit(self.paleta)

    def _al_cambiar_sistema(self, _esquema: Qt.ColorScheme) -> None:
        if self.preferencia == "sistema":
            self.aplicar()


class _Instalado:
    """El tema de la app en curso (uno por QApplication)."""

    tema: Tema | None = None


def instalar(app: QApplication, preferencia: str = "sistema") -> Tema:
    """Aplica el tema a la app (una vez) y lo deja disponible para los widgets que pintan íconos."""
    instalado = _Instalado.tema
    if instalado is None or instalado.parent() is not app:
        instalado = Tema(app, preferencia)
        _Instalado.tema = instalado
    else:
        instalado.elegir(preferencia)
    return instalado


def actual() -> Paleta:
    return _Instalado.tema.paleta if _Instalado.tema is not None else OSCURO


def tema() -> Tema | None:
    return _Instalado.tema

"""Punto de entrada de la ventana. Con `--autoprueba CARPETA SALIDA.json` comprueba sin pantalla que
la app (también empaquetada como .exe) arranca y analiza una instancia, y escribe el resultado.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import NOMBRE, __version__, configuracion, registro
from ..motores.simulador import Simulador
from ..proceso import Proceso
from .ventana import Ventana

ICONO = Path(__file__).with_name("icono.png")


class Avisador(QObject):
    """Muestra los errores no previstos en el hilo de la ventana, vengan del hilo que vengan."""

    aviso = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.aviso.connect(self._mostrar)

    def _mostrar(self, texto: str) -> None:
        QMessageBox.critical(None, NOMBRE, texto)


def _autoprueba(carpeta: str, salida: str) -> int:
    ventana = Ventana(buscar_instancias=list)
    ventana.close()
    ventana.deleteLater()  # que Qt la destruya ahora y no Python al salir, cuando Qt ya se cerró
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    registro.LOGGER.info("Autoprueba de %s", carpeta)
    with Proceso(carpeta, Simulador()) as p:
        informe = p.analizar()
        datos = {
            "version_app": __version__,
            "icono": ICONO.is_file(),
            "registro": bool(registro.ultimas_lineas(5)),
            "minecraft": str(p.instancia.version),
            "loader": p.instancia.loader,
            "modulos": [{"grupo": m.grupo, "textos": m.textos, "a_traducir": m.a_traducir} for m in informe.modulos],
        }
    Path(salida).write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    app = QApplication.instance() or QApplication([sys.argv[0], *argumentos])
    QApplication.setApplicationName(NOMBRE)
    QApplication.setApplicationVersion(__version__)
    QApplication.setWindowIcon(QIcon(str(ICONO)))
    registro.configurar(configuracion.carpeta_datos())
    registro.LOGGER.info("Inicio de %s %s", NOMBRE, __version__)
    if argumentos[:1] == ["--autoprueba"] and len(argumentos) == 3:
        return _autoprueba(argumentos[1], argumentos[2])
    avisador = Avisador()
    registro.instalar_manejadores(avisador.aviso.emit)
    ventana = Ventana()
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

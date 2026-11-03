"""Punto de entrada que usa PyInstaller para construir el .exe de la ventana."""

from traductor_es.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())

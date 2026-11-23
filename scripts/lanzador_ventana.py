"""Punto de entrada que usa PyInstaller para construir el .exe de la ventana."""

from traductor_es import dll_sistema

# Antes de importar Qt: que una DLL falsa junto al .exe no reemplace a la del sistema (ver `dll_sistema`)
dll_sistema.precargar()

from traductor_es.ui.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

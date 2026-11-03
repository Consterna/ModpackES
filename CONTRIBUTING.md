# Cómo contribuir

Gracias por querer mejorar ModpackES. Se aceptan reportes de errores, modpacks que no se traducen bien,
ideas y cambios en el código.

## Reportar un problema

Abre un [issue](https://github.com/Consterna/ModpackES/issues/new/choose) con la plantilla que corresponda.
Lo más útil es:

- el nombre y la versión del modpack (y de dónde se descarga);
- la versión de Minecraft, el loader y el lanzador;
- lo que aparece en el registro de la ventana (el cuadro de texto de abajo);
- si es un texto mal traducido, el texto original y dónde aparece en el juego.

**Nunca pegues tu clave de Gemini** en un issue, aunque sea parcial.

## Preparar el entorno

Necesitas [uv](https://docs.astral.sh/uv/) y, para las pruebas con los parsers del juego, un JDK 17 o superior
(sirve el que trae Prism Launcher).

```
git clone https://github.com/Consterna/ModpackES.git
cd ModpackES
uv sync
uv run python scripts/verificar.py --rapido
```

## Antes de mandar un pull request

1. Abre la rama desde `main` y haz un cambio por pull request.
2. Agrega o actualiza las pruebas en `tests/`. Si es un formato nuevo, incluye una prueba de ida y vuelta
   (leer → escribir sin cambios → mismo archivo byte a byte).
3. Corre la puerta de calidad completa y deja todo en verde:
   ```
   uv run python scripts/verificar.py
   ```
   Incluye `ruff check`, `ruff format --check`, `pyright` en modo estricto, `compileall` y `pytest`.
4. Si el cambio se nota para el usuario, anótalo en `CHANGELOG.md`, en la sección «Sin publicar».

## Convenciones

- El código, los nombres, los comentarios y los mensajes de commit van **en español**, como el resto del
  proyecto.
- Tipado completo: `pyright` en modo estricto no debe dar errores.
- Nada se escribe fuera de las rutas permitidas: la instancia (con copia en `traductor_es/respaldo`) y la
  carpeta de datos de la app.
- Los jars de los mods no se modifican nunca.
- Las pruebas no tocan los datos reales del usuario: `tests/conftest.py` lleva la memoria a una carpeta
  temporal y desactiva el almacén de credenciales.

## Cómo está organizado

| Carpeta | Qué hay |
|---|---|
| `src/traductor_es/nucleo` | Marcadores de códigos, memoria, glosario, variantes de español y el orquestador de traducción |
| `src/traductor_es/formatos` | Lectura y escritura sin pérdidas: SNBT, JSON, NBT, `.lang`, JavaScript y markdown |
| `src/traductor_es/fuentes` | Lanzadores, versión, loader, jars y prioridad de los resource packs |
| `src/traductor_es/modulos` | Misiones, libros, scripts y mods: qué se traduce y dónde se escribe |
| `src/traductor_es/motores` | Gemini y el simulador para pruebas |
| `src/traductor_es/salida` | Resource pack, `options.txt`, copias de seguridad y exportación |
| `src/traductor_es/validacion` | Reglas de calidad y el validador con los parsers del juego (Java) |
| `src/traductor_es/ui` | La ventana (PySide6) |

## Licencia de las contribuciones

ModpackES usa la licencia [GPL-3.0-or-later](LICENSE). Al mandar un cambio aceptas que se publique bajo esa
misma licencia.

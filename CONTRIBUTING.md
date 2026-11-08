# Cómo contribuir

Gracias por querer mejorar ModpackES. Se aceptan reportes de errores, modpacks que no se traducen bien,
ideas y cambios en el código. Al participar aceptas el [código de conducta](CODE_OF_CONDUCT.md).

## Reportar un problema

Abre un [issue](https://github.com/Consterna/ModpackES/issues/new/choose) con la plantilla que corresponda.
Lo más útil es:

- el nombre y la versión del modpack (y de dónde se descarga);
- la versión de Minecraft, el loader y el lanzador;
- el texto de «Copiar diagnóstico» (versiones y final del registro, sin tu carpeta personal ni claves);
- si es un texto mal traducido, el texto original y dónde aparece en el juego.

**Nunca pegues tu clave** de Gemini ni de otro motor en un issue, aunque sea parcial.

## Preparar el entorno

Necesitas [uv](https://docs.astral.sh/uv/) y, para las pruebas con los parsers del juego, un JDK 17 o superior
(sirve el que trae Prism Launcher).

```
git clone https://github.com/Consterna/ModpackES.git
cd ModpackES
uv sync
uv run python scripts/verificar.py --rapido
uv run --with pre-commit pre-commit install   # ruff y comprobaciones básicas antes de cada commit
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

## Medir la calidad de la traducción

Si cambias las instrucciones del motor, las reglas de calidad o agregas un motor, compara antes y después con el
banco de referencia (`tests/datos/referencia_es.json`: 148 textos escritos para el proyecto, con su traducción
de referencia y un glosario):

```
uv run python scripts/medir_calidad.py --simular            # sin gastar: comprueba que todo funcione
uv run python scripts/medir_calidad.py --revisar            # con Gemini y tu clave (cuesta unos centavos)
uv run python scripts/medir_calidad.py --motor ollama --modelo qwen3:8b
```

Muestra los textos aceptados por las reglas, el chrF contra la referencia, los términos del glosario respetados
y el costo estimado. Un chrF más bajo no siempre es peor: una traducción correcta pero distinta de la
referencia también baja el puntaje, así que revisa los ejemplos que lista el script.

## Convenciones

- Mensajes de commit con [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/)
  (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `build:`, `ci:`, `chore:`…), un cambio lógico por commit y
  explicando el porqué. El CI lo comprueba en cada pull request.
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
| `src/traductor_es` | `proceso.py` (une todo), `configuracion.py` (claves y preferencias), `registro.py` (registro y diagnóstico), `actualizaciones.py` (aviso de versión nueva) |
| `src/traductor_es/nucleo` | Marcadores de códigos, memoria y correcciones, glosario, variantes de español y el orquestador de traducción |
| `src/traductor_es/formatos` | Lectura y escritura sin pérdidas: SNBT, JSON, NBT, `.lang`, JavaScript y markdown |
| `src/traductor_es/fuentes` | Lanzadores, versión, loader, jars y prioridad de los resource packs |
| `src/traductor_es/modulos` | Misiones, libros, scripts, datos (funciones, logros, tips) y mods: qué se traduce y dónde se escribe; `cobertura.py` dice qué queda en inglés |
| `src/traductor_es/motores` | Gemini, el motor compatible con OpenAI, las instrucciones comunes a todos, la fábrica de motores y el simulador para pruebas |
| `src/traductor_es/salida` | Resource pack, `options.txt`, copias de seguridad y exportación |
| `src/traductor_es/validacion` | Reglas de calidad, revisión automática, medición con el banco de referencia y el validador con los parsers del juego (Java) |
| `src/traductor_es/ui` | La ventana y el editor de correcciones (PySide6) |

## Agregar un formato de texto nuevo

Los archivos de texto de datapacks y packs de recursos (funciones, logros, tips…) se reconocen por su ruta y su formato,
no por el modpack. Para agregar uno, escribe un `Formato` en `src/traductor_es/modulos/datos.py` (qué ruta lo reconoce,
cómo saca los textos y cómo los reescribe), cita su documentación en un comentario y agrega a `tests/` una prueba que
traduzca un caso real recortado, otra con algo que **no** debe tocarse y la de ida y vuelta (restaurar devuelve los bytes
originales). `uv run python scripts/descargar_corpus.py` baja partes de modpacks públicos de Modrinth a `.descargas/`
(Git lo ignora); `uv run pytest -m corpus` los usa para comprobar que lo traducido sigue siendo válido.

## El mod de apoyo (Java)

`mod-runtime/forge-1.20.1/`, `mod-runtime/neoforge-1.21.1/` y `mod-runtime/fabric-1.20.1/` son mods solo de cliente (con la misma lógica de tabla y plantillas) que cambia, al mostrarlos, los textos que otros mods tienen en su código y que están en la tabla de la app. Forge 1.20.1 se compila con ForgeGradle 6 y Java 17; NeoForge 1.21.1, con ModDevGradle, Gradle 9 y Java 21; Fabric 1.20.1, con Loom 1.17, Gradle 9 y Java 21 (el mod queda compilado para Java 17):

```
uv run python scripts/construir_mod.py [forge-1.20.1 | neoforge-1.21.1 | fabric-1.20.1]
```

Corre las pruebas de Java (JUnit) y deja el jar en `src/traductor_es/recursos/mods/` (Git lo ignora; el CI lo construye y `construir_exe.py` lo incluye). Un loader o versión nuevo es un proyecto nuevo en `mod-runtime/` y una entrada en `SOPORTADOS` de `salida/mod_apoyo.py`.

## Licencia de las contribuciones

ModpackES usa la licencia [GPL-3.0-or-later](LICENSE). Al mandar un cambio aceptas que se publique bajo esa
misma licencia.

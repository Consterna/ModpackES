# Datos de terceros en el desarrollo

ModpackES se publica con GPL-3.0. Para probarlo se usan modpacks, jars, traducciones y modelos de otras
personas. Estas reglas dicen qué se puede guardar, dónde y para qué.

## Regla de oro

**Nada de terceros entra al repositorio**: ni packs, ni jars, ni pares de traducción, ni modelos. El repo lleva
código y archivos de prueba escritos por el proyecto (`tests/datos/referencia_es.json`).

Todo lo descargado vive en carpetas ignoradas por git (`.descargas/`, `.corpus/`, `.modelos/`) y no se incluye
en el instalador ni en el ejecutable.

## Packs de prueba (`.descargas/`)

`scripts/descargar_corpus.py` baja solo configs de misiones, scripts de KubeJS, libros y el índice del pack,
nunca los jars de los mods, y con un tope de 40 MB por pack.
`scripts/auditar_licencias.py` anota en `.descargas/licencias.json` la licencia del pack y de sus mods.

| Licencia del pack | Qué se hace |
|---|---|
| Libre (MIT, Apache, BSD, GPL, LGPL, CC…) | Copia local para pruebas. |
| «All Rights Reserved» | Copia local para pruebas, sin redistribuir y solo las partes que ya baja el script. Se borra si su autor lo pide. |
| No indicada o dudosa | No se usa hasta decidirlo. |

Solo se usa Modrinth, que publica la licencia de cada proyecto. CurseForge no se usa como fuente automática.

## Traducciones y glosarios

- El glosario se construye en el PC de quien usa la app, con el `es_es` de sus propios mods
  (`nucleo/glosario.py`, `fuentes/vanilla.py`). **No se incluye ningún glosario de terceros.**
- Los textos del juego de Mojang no se redistribuyen.
- Los pares inglés/español sacados de jars para medir calidad se quedan en `.descargas/banco/`. En
  `docs/calidad.md` solo van las métricas, nunca los textos.

## Modelos locales (`.modelos/`)

Se anotan la versión y la licencia de cada modelo que se baja, tomadas de su página oficial. Los que tienen
términos propios (Llama, Gemma) valen para uso local de prueba. Ningún modelo se incluye en el instalador.
Todo lo nuevo (modelos, packs y herramientas) comparte un tope de 30 GB de disco.

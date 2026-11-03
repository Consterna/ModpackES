# Cambios

Todos los cambios importantes de ModpackES quedan en este archivo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido

- Registro en archivo (`registro.log`, en la carpeta de datos) con lo que muestra la ventana, los avisos y
  los errores. Nunca guarda la clave.
- Botones «Copiar diagnóstico» (versiones, sistema y final del registro, sin tu carpeta personal ni claves)
  y «Abrir registro», para reportar problemas.
- Los errores no previstos se avisan en una ventana en vez de cerrar la app en silencio.
- Correcciones del usuario: una traducción corregida a mano manda sobre la memoria y el motor en todos
  los ámbitos, no se paga y se rechaza si pierde algún código del original (`%s`, `§a`, `$(l)`…).
- Botón «Correcciones…»: busca en la memoria por el texto en inglés o en español y permite corregir,
  guardar y quitar correcciones desde la ventana.
- Campo «Ambientación» (y `--contexto` en la línea de comandos): una descripción corta del modpack que el
  motor usa para el tono y los términos propios. Se guarda por instancia.

### Corregido

- Los términos del glosario del usuario (`glosario.json`) no se aplicaban a textos que ya estaban en la
  memoria de traducciones. Ahora mandan siempre.
- Un error no previsto durante el análisis o la traducción dejaba la ventana en «Trabajando…» con los botones
  bloqueados.

## [2.0.0] - 2026-11-03

Primera versión pública. Se reescribió desde cero y se probó de punta a punta, dentro del juego, con
Farming Crossing 4 (1.20.1, Forge).

### Añadido

- **Misiones:** FTB Quests (texto en los capítulos, carpeta `lang/` de 1.21+ y NBT de 1.12), BetterQuesting,
  HQM y Heracles.
- **Libros guía:** Patchouli, Mantle (Tinkers), Citadel, GuideME (AE2) y Lavender.
- **Scripts de KubeJS:** los textos que ve el jugador (`tell`, `displayName`, `Text.of`, tooltips, JEI/REI/EMI).
- **Textos de mods**, de KubeJS y de los resource packs del modpack en las siete variantes de español del juego.
- Detección de versión y loader con cualquier lanzador (Prism, MultiMC, CurseForge, Modrinth, ATLauncher,
  GDLauncher y el oficial), jars anidados, `.lang` antiguo y formato de pack de cada versión hasta 26.3.
- Protección de los códigos de formato con marcadores, memoria de traducciones compartida entre modpacks,
  glosario con los nombres oficiales y reglas de calidad con reintentos.
- Motor Gemini (SDK oficial) con salida JSON estricta y modo por lotes (Batch API) a mitad de precio.
- Copia de seguridad de todo lo que se cambia y botón para restaurar el original.
- Ventana con PySide6, línea de comandos (`modpackes`), exportación del resource pack y kit para servidores.
- Ejecutable de un solo archivo para Windows, construido y probado en GitHub Actions.

## 1.0 - prototipo (sin publicar)

- Script y ventana mínimos para FTB Quests, Patchouli, Citadel y lang de mods en una sola instancia.

[Sin publicar]: https://github.com/Consterna/ModpackES/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/Consterna/ModpackES/releases/tag/v2.0.0

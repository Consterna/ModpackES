# Cambios

Todos los cambios importantes de ModpackES quedan en este archivo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- Mensajes de chat de los scripts de KubeJS: el texto de `tellraw`, `title` y `say` (y `msg`, `tell`, `w`)
  cuando se manda con `runCommand` o `runCommandSilent`. Antes solo se traducía lo que pasaba por `tell`,
  `Text.of` y similares.
- Mensajes que un script arma por partes (`let mensaje = 'Tienes '; mensaje += efecto.name; player.tell(mensaje)`):
  los trozos de texto, los `name` que se suman y las tablas de nombres que se suman (`nombres[clave]`). Solo
  cuando la variable acaba en una llamada de texto como `tell`.
- Logros (título y descripción) y funciones `.mcfunction` de `kubejs/data`, que también muestran mensajes en
  el chat. Van en el grupo Scripts, con copia de seguridad, y entran en el kit para servidores.

## [2.2.0] - 2026-11-04

Interfaz nueva: una ventana guiada en pasos, con tarjetas y un solo botón principal, y un tema propio
agua marina y morado, en oscuro y en claro.

### Agregado

- Bienvenida la primera vez, con los tres pasos y un botón para configurar el motor.
- Arrastrar la carpeta de un modpack a la ventana la agrega a la lista.
- Atajos: Ctrl+F busca una instancia, F5 vuelve a buscarlas, Ctrl+Enter pulsa el botón principal y las
  flechas pasan de una instancia a otra.

### Cambiado

- Aspecto nuevo: tema propio agua marina y morado, en oscuro y en claro. Sigue el modo de Windows y tiene íconos
  en los botones. Todos los textos cumplen el contraste mínimo de WCAG (4,5:1).
- Ventana nueva, guiada en cuatro pasos (motor, analizar, traducir, listo) con un solo botón principal que
  cambia según el paso: «Analizar (gratis)», «Traducir 295 textos · US$ 0,01» y «Listo: abrir la carpeta».
- Las instancias salen como tarjetas con la versión de Minecraft, el loader y si ya están traducidas, con un
  buscador. Esos datos se leen en segundo plano, sin trabar el arranque.
- Mods, libros, misiones y scripts son tarjetas con cuántos textos faltan y una casilla para incluirlos. El
  análisis cuenta los cuatro grupos (es gratis), y el costo y lo que se traduce siguen solo a los marcados.
- El motor, su modelo y su clave van en el diálogo «Motor de traducción», que se abre desde la ficha de
  arriba («Gemini · listo» o «falta la clave»).
- Las acciones menos usadas (correcciones, restaurar, exportar, kit de servidor, diagnóstico) van en «Más».
  Las opciones avanzadas y el registro van en secciones plegables.
- Nombres más claros: «Español de» (antes «Base de la traducción»), «Velocidad» («Peticiones a la vez») y
  «Más barato, pero tarda más» («Por lotes»).
- Los avisos y errores salen en una franja dentro de la ventana, en lugar de cuadros que cortan el trabajo.
  Solo «Restaurar» y «Traducir» siguen pidiendo confirmación.
- La barra de progreso dice qué parte se está traduciendo y cuánto falta.
- Si un grupo no se puede leer al analizar (un archivo bloqueado o roto), el análisis sigue con los demás:
  ese grupo queda desmarcado y el motivo, en Detalles.
- El engranaje de arriba elige el tema (como Windows, oscuro o claro) y el aviso de versiones nuevas.

## [2.1.1] - 2026-11-03

Arreglos que encontró el análisis de seguridad de GitHub (CodeQL) después de publicar la 2.1.0.

### Corregido

- En las guías de GuideME y Lavender, el texto de un comentario `<!-- … -->` de varias líneas se tomaba como
  párrafo y se traducía. Ahora se deja como está, igual que los comentarios de una línea.

### Seguridad

- Una guía de GuideME o Lavender con una línea de etiquetas mal formada podía dejar la app trabada un tiempo
  que crecía de forma exponencial con su largo (ReDoS, detectado por CodeQL). Ahora se descarta al instante.

## [2.1.0] - 2026-11-03

Más control sobre la traducción (correcciones, ambientación, revisión), otros motores además de Gemini,
incluidos modelos gratis en el propio PC, un instalador y releases verificables.

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
- Motores compatibles con OpenAI además de Gemini: OpenRouter, DeepSeek, LM Studio y Ollama (gratis, con un
  modelo en tu PC) y uno personalizado. Se elige en la ventana o con `--motor`; cada uno guarda su clave y
  su modelo. «Probar clave» pasa a ser «Probar conexión» y carga los modelos de cualquier motor.
- Revisión automática opcional de misiones y libros (`--revisar`): el motor juzga cada traducción nueva y
  se rehacen las que tienen errores graves. Lo rehecho solo reemplaza a lo anterior si pasa las mismas
  reglas, y las correcciones del usuario no se tocan. El análisis estima el costo con la revisión.
- Banco de referencia (148 textos propios con su traducción) y `scripts/medir_calidad.py`, que mide con
  cualquier motor los textos aceptados, el chrF, los términos del glosario respetados y el costo.
- Aviso de versión nueva al abrir la ventana, con enlace a la descarga. Consulta GitHub sin datos del usuario,
  no descarga nada y se puede desactivar.
- Instalador (`ModpackES-instalador.exe`, Inno Setup) que se instala para el usuario sin permisos de
  administrador. Arranca en 1,1 s frente a 2,7 s del portable, que se sigue publicando.

### Cambiado

- En la línea de comandos, `--modelo` solo tiene valor por defecto con Gemini: con otro motor hay que
  indicarlo.
- Si `options.txt` no tenía lista de resource packs, la que se crea queda en UTF-8 sin escapar, igual que
  cuando se modifica una existente.

### Corregido

- Los términos del glosario del usuario (`glosario.json`) no se aplicaban a textos que ya estaban en la
  memoria de traducciones. Ahora mandan siempre.
- Un error no previsto durante el análisis o la traducción dejaba la ventana en «Trabajando…» con los botones
  bloqueados.

### Seguridad

- Cada release trae una atestación de origen firmada (se comprueba con `gh attestation verify`) y la lista
  de componentes en formato CycloneDX.
- Las acciones del CI van fijadas por commit, con CodeQL y Dependabot (las versiones nuevas esperan 14 días).
- La firma del ejecutable con SignPath queda preparada para cuando se apruebe el proyecto (`docs/firma.md`).

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

[Sin publicar]: https://github.com/Consterna/ModpackES/compare/v2.2.0...HEAD
[2.2.0]: https://github.com/Consterna/ModpackES/compare/v2.1.1...v2.2.0
[2.1.1]: https://github.com/Consterna/ModpackES/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/Consterna/ModpackES/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/Consterna/ModpackES/releases/tag/v2.0.0

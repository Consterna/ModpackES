# Cambios

Todos los cambios importantes de ModpackES quedan en este archivo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- **Texto escrito en el código de los mods** (opcional, apagado por defecto): la app traduce las frases que encuentra en el código Java de los
  mods y las guarda en una tabla del resource pack; el nuevo mod de apoyo **ModpackES Runtime** (solo cliente, para Forge 1.16.5, 1.17.1, 1.18.2, 1.19.2 y 1.20.1, NeoForge 1.20.1, de 1.21 a 1.21.11 y de 26.1 a 26.3, y Fabric 1.19.4, de 1.20 a 1.20.6, de 1.21 a 1.21.11 y de 26.1 a 26.3, y Quilt con los mods de Fabric hasta 1.21.1) las muestra en
  español en el chat, la barra de acción, los tooltips y el texto de los botones de una pantalla al abrirla (en Forge y NeoForge también los tooltips que no son de objetos). No cambia el texto que una pantalla dibuja directamente. Solo cambia textos idénticos a los de la tabla. «Más ▸ Instalar el mod de apoyo» y
  «Quitar el mod de apoyo», `modpackes instalar-runtime` y `--java` en `analizar` y `traducir`. El CI compila el mod con sus pruebas.

- **Mensajes de chat y datos de texto**, que antes quedaban en inglés:
  - El texto de `tellraw`, `title`, `say`, `msg`, `tell` y `w` en las funciones (`.mcfunction`) y en lo que un script de
    KubeJS manda con `runCommand` o `runCommandSilent`.
  - Títulos y descripciones de logros, y los consejos de las pantallas de carga (mod Tips, en sus dos formatos).
  - Mensajes que un script arma por partes (`mensaje += efecto.name; player.tell(mensaje)`), con sus tablas de nombres.
  - `notify`, `kick`, `openChestGUI` y `openInventoryGUI` de KubeJS (métodos tomados del código de KubeJS 1.20 y 1.21).
- **Plantillas en el mod de apoyo:** una frase con datos variables escrita con `%s` o `%d` (p. ej. «Hello %s, welcome back!») se traduce y el mod la reconoce con cualquier dato («Hello Steve, welcome back!»). Se descartan las traducciones que cambian el orden de los datos o pierden alguno, y las plantillas con casi nada de texto fijo.
- **Informe «Qué queda en inglés»:** ahora se ve en un cuadro con las categorías separadas y se puede guardar (`Más ▸ Guardar el informe…`); `modpackes cobertura --json` lo escribe como JSON para otros programas. `Más ▸ Comprobar el mod de apoyo` dice si el mod está en `mods/`, si esta copia lo trae y si ya hay tabla de textos.
- **Modo exhaustivo** para los scripts de KubeJS (opcional, apagado por defecto; `--exhaustivo` y una casilla en «Opciones avanzadas»): traduce también toda frase que parezca texto aunque no se sepa dónde se muestra. Puede tocar lógica; todo queda con copia de seguridad. Nunca toca `console.log` ni comparaciones.
- **Funciones propias de un script que solo muestran texto** (`CreateStringTooltip(evento, objeto, texto)`, `crear(id, nombre)`…): se traduce lo que se les pasa en la posición de ese parámetro. Es conservador: si el parámetro se compara, se busca, se guarda, se devuelve, va en un id o en un comando, o la función se usa como valor o está repetida, no se toca nada. Un `id` junto a un `nombre` queda intacto. En un modpack real (TaidumCraft) pasó de 101 a 35 frases sin elegir.
- Los métodos de texto de KubeJS ahora dependen de la versión (`notify`, `openChestGUI`… solo donde existen), comprobados en el código de KubeJS de 1.12 a 26.x (`formatos/kubejs_api.py`).
- Mercado de Farming for Blockheads (`farmingforblockheads_compat`): se traducen los nombres de las pestañas.
- El informe «Qué queda en inglés» también avisa de carpetas de datos con frases en inglés cuyo formato la app no conoce.
- El informe también avisa de los comandos de otros mods (como `emberstextapi queue` o `/eta queue`) que llevan una frase en inglés dentro de un script: la app no conoce su formato y no los toca, pero ya no pasan en silencio.
- Estos datos se buscan por su estructura y no por la carpeta de un modpack: `kubejs/data`, `global_packs`, `datapacks`,
  `config/openloader`, los datapacks de un mundo y cualquier otra con `data/<espacio>/functions/…`, sueltos o dentro de un `.zip`
  (se reescribe el zip y se guarda el original). Los componentes de texto valen en JSON y en SNBT (1.21.5 y posteriores).
- **Más ▸ Qué queda en inglés** y `modpackes cobertura`: lista lo que no se puede traducir y por qué (frases de scripts cuyo uso
  no se entiende y texto escrito en el código de los mods, leído de la tabla de constantes de cada clase). Solo lee.
  El análisis avisa de las frases de scripts que parecen texto.
- Pruebas con modpacks públicos de Modrinth (16 más en `scripts/descargar_corpus.py`, de 1.16.5 a 26.x con Forge, NeoForge, Fabric y Quilt) y con la instancia propia: lo traducido
  sigue siendo válido, repetir no cambia nada y restaurar devuelve los bytes originales.

### Cambiado

- **El glosario ya no deja que un mod imponga su traducción a todo el modpack.** Los nombres del propio juego (primero es_mx, después es_es) mandan sobre los de un mod, y si dos mods traducen distinto el mismo término no se usa ninguno. Antes un mod que llamaba «Acechador de medianoche» a la vaca hacía que todo el modpack la tradujera así.
- **Motores en tu PC (LM Studio, Ollama o un servidor en localhost):** los pedidos son más chicos (12 textos o 1.800 caracteres en vez de 60 o 5.000), porque un modelo pequeño se equivoca más con pedidos largos. Para medir sin saturar la GPU hay una «carga segura» en las herramientas de desarrollo (`medir_calidad.py --carga-segura`: pausas entre pedidos y espera si la GPU pasa de 80 °C).
- **Ya no se mandan ejemplos de otros mods al motor.** Con referencias limpias, los ejemplos parecidos bajaron el chrF de Gemini (−1,2, intervalo de −2,3 a −0,3) y la ganancia que se había medido antes con el contexto no se reprodujo; las pistas (clave y tipo de cada texto) se mantienen. Los ejemplos siguen en el código para probarlos con modelos locales; ver [docs/calidad.md](docs/calidad.md).
- **Contexto de vecindad en misiones y libros.** Cada texto de una misión o de un libro se manda al motor con el título bajo el que está y el texto que viene justo antes, para elegir mejor el sentido y el tono. En una comparación con un juez ganó el 56 % de los casos decididos, sin llegar a ser concluyente; ver [docs/calidad.md](docs/calidad.md).

- **El glosario ahora se exige.** Si un término del glosario sale en un texto y su traducción no lo usa (con tolerancia a plurales, tildes y mayúsculas), el texto se reintenta una vez con un aviso explícito; si sigue sin salir se acepta, para no dejar nada en inglés.

- **Traducciones más precisas.** Cada texto de un mod va ahora con de dónde sale y qué es («nombre de un objeto», «tooltip», «disco de música»…), y si el mismo texto sale en varios sitios se mandan hasta tres pistas. El motor recibe además ejemplos de textos parecidos ya traducidos (el español que traen los mods del modpack, la memoria y lo que se va traduciendo en esa misma ejecución) para seguir los mismos términos y estilo. Los términos que se repiten en los nombres («Moon Berries» en «Moon Berries Pie», «Moon Berries Jam»…) se traducen primero y se fijan en el glosario, para que todos los nombres usen la misma palabra. Un nombre que el motor devuelve igual al original se reintenta con un aviso; si sigue igual, se acepta. Con 250 textos reales de mods y Gemini 3.8 Flash, el chrF subió de 68,9 a 70,6 (promedio de tres corridas); ver [docs/calidad.md](docs/calidad.md).

- El kit para servidores incluye las funciones y los logros traducidos dondequiera que estén, también los de un datapack comprimido (`.zip`); los `.zip` que solo traen tips siguen fuera porque son de cliente.
- «Instalar el mod de apoyo» copia el mod nuevo antes de borrar los viejos, para no dejarte sin mod si la copia falla, y «Estado del mod de apoyo» avisa cuando el jar instalado es de otra versión de Minecraft en lugar de decir que todo está listo.

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

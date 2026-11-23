# Cobertura: qué texto de un modpack se traduce y qué no

[calidad.md](calidad.md) mide **qué tan bien** se traduce. Este documento mide **cuánto**: qué texto que ve el jugador queda en
inglés y por qué. Tiene dos partes: el catálogo de dónde puede vivir el texto de un modpack (la lista de verificación) y los
resultados medidos sobre un corpus de modpacks reales.

## Cómo se mide

Tres instrumentos que no comparten código, para que la ceguera de uno no se repita en los otros:

1. **Inventario independiente** (`scripts/auditoria/inventario.py`). Recorre la instancia entera y cada jar, zip y carpeta que
   trae. Lee todos los formatos de texto (JSON, JSON5, SNBT, NBT, TOML, CFG, JS, ZS, mcfunction, lang, MD, TXT) y anota toda
   frase en inglés que podría ver el jugador. No importa nada de la app.
2. **La app** (`scripts/auditoria/comparar_cobertura.py`). Reúne lo que cada módulo recogería para traducir, sin escribir nada,
   y lo cruza con el inventario. Lo que el inventario ve y la app no es la **brecha**.
3. **El juego** (mod de desarrollo `mod-runtime/sonda/`). Anota el idioma cargado y todo el texto que se dibuja. Ahí se ven
   también las claves que se crean mientras el juego corre.

El corpus se arma con `scripts/auditoria/descargar_packs.py`: packs enteros, con todos sus mods, de Modrinth y FTB. La lista
está en `scripts/auditoria/seleccion.txt`. Se guarda en `C:\dev\corpus-modpacks` y no se publica (ver
[datos-de-terceros.md](datos-de-terceros.md)).

**Ningún cambio puede bajar la calidad.** Antes de cada arreglo y al final, `scripts/auditoria/puerta_calidad.py` vuelve a
medir los bancos de calidad con las respuestas grabadas (gratis). Las traducciones, las métricas y los pedidos tienen que salir
idénticos a la línea base. Las fuentes nuevas van en módulos nuevos que no alimentan el glosario, para que los pedidos de lo que
ya se traducía no cambien.

## Fuentes de texto

Estado: ✅ la app lo traduce · 🟡 en parte · ❌ no · ⛔ no se puede de forma segura (motivo en la columna).

### Archivos de idioma y recursos

| Fuente | Dónde vive | Estado | Notas y evidencia |
|---|---|---|---|
| Idioma de los mods | `assets/<ns>/lang/en_us.json` (`.lang` antes de 1.13) en jars | ✅ | `modulos/mods.py` |
| Jars anidados de Fabric/Quilt declarados en `fabric.mod.json` → `jars` fuera de `META-INF/jars` | jar dentro de jar, en la raíz u otra carpeta | ✅ | Fabric carga lo que declara `jars[].file`. La app solo mira `META-INF/jars`, `jarjar` y `jarinjar`. Visto en Simple Pipes (FTB Cotton). |
| KubeJS, ResourceLoader, Global Packs, OpenLoader, Paxi, packs activos | `kubejs/assets`, `resources/`, `global_packs/…`, `config/openloader`, `config/paxi`, `resourcepacks/` | ✅ | `fuentes/recursos.py` |
| Lang de shaderpacks (Iris/Oculus) | `shaderpacks/<pack>/shaders/lang/en_US.lang`, en zip o en carpeta | ✅ | Iris usa el lang del shaderpack solo si la clave **no** está en el idioma del juego. Por eso un resource pack con `option.X`, `screen.X`, `value.X.<v>`… lo pisa (Iris `MixinClientLanguage`, `LanguageMap`). Con OptiFine, sin confirmar. Las claves son globales: dos shaders pueden chocar. |
| Descripción del mod en la lista de mods | `fabric.mod.json`/`quilt.mod.json` `description`; `mods.toml` `description` | ✅ (Mod Menu, NeoForge) · ⛔ Forge | Mod Menu lee `modmenu.descriptionTranslation.<modid>` y `modmenu.summaryTranslation.<modid>` si existen (`Mod.java`). NeoForge 20.4–21.x lee `fml.menu.mods.info.description.<modid>` (PR #649); desde la renovación de la lista (#3073), `neoforge.screen.mods.info.description.<modid>`. **Forge no tiene clave** (`ModListScreen`): ⛔ sin código. |
| Claves que se crean mientras el juego corre | ARRP/BRRP, Moonlight, KubeJS `ClientEvents.lang`, PonderJS (`kubejs/assets/ponderjs_generated/lang`) | 🟡 | Si el pack generado solo trae `en_us`, nuestro `es_*` gana siempre (cada idioma se aplica después de en_us). ARRP `AFTER_VANILLA` va encima de los packs del usuario. En KubeJS 1.20.1 su pack se mete **antes del primer pack .zip** del usuario: con el nuestro en carpeta, KubeJS podría quedar encima. Hay que verlo en el juego (sonda). |

### Libros guía

| Fuente | Dónde vive | Estado | Notas |
|---|---|---|---|
| Patchouli 1.17+ con `use_resource_pack` y 1.20+ | `assets/<ns>/patchouli_books/<libro>/<idioma>/` | ✅ | `modulos/libros.py` |
| Patchouli con `"i18n": true` y Modonomicon | claves de idioma | ✅ | como libro, con su tono |
| Plantillas propias de Patchouli (Blood Magic `heading`, `a.heading`) | campos de página de tipo `<mod>:<plantilla>` | ✅ | Se lee la plantilla (`templates/`, en inglés): cuenta como texto el campo que es el valor entero de un componente `patchouli:text`, `header` o `tooltip`, con los nombres de las incluidas (`<as>.<campo>`) y las variables atadas con `using`. Una variable dentro de una frase («Cost: #syphon# LP») no se toca. Van en un pedido aparte con el tono de la interfaz. |
| Patchouli 1.14–1.19 dentro del jar (`data/<ns>/patchouli_books/…`) | jar | ⛔ | Se carga del classpath. Ni un resource pack ni un datapack lo pisan. «Patchouli Resource Patch» (PRP-Arch, 1.15–1.19) hace que lea primero de assets, pero solo reemplaza archivos que ya existen. Opción: informar y sugerir PRP, o hacer lo mismo en el mod de apoyo. |
| Libros propios del modpack | `<instancia>/patchouli_books/` | ✅ | se reescriben en su lugar |
| Mantle, Citadel, Lavender, GuideME | `assets/<ns>/book/…`, `lavender/…`, `<carpeta>/_<idioma>/` | ✅ | |
| Guía de ParCool | `assets/parcool/book/parcool_guide_content_<idioma>.txt` | ❌ | la traduce a mano el pack «Traducciones de Mods» |

### Misiones

| Fuente | Dónde vive | Estado | Notas |
|---|---|---|---|
| FTB Quests: SNBT, carpeta `lang/` y NBT de 1.12 | `config/ftbquests/quests/` | ✅ | `modulos/misiones.py` |
| Nombre y descripción de los objetos de **recompensa** de FTB Quests | `rewards[].item`: `tag.display.Name`/`Lore` (hasta 1.20.4, en SNBT y en el NBT de 1.12) o `components` `custom_name`/`item_name`/`lore` (1.20.5+) | ✅ | Nunca bajo `tasks`: ahí FTB Quests compara el NBT del objeto que entrega el jugador, y cambiarle el nombre rompería la misión. El título y la descripción de la misión y de cada tarea se traducen como siempre. Pedido aparte, con el tono de la interfaz. |
| FTB Quests en otras raíces | `config/ftbquests/normal/` (FTB Interactions Remastered), `config/ftb_quests/`, `defaultconfigs/ftbquests/` | ❌ | por confirmar en el corpus |
| FTB Quests en JSON5 (26.x) | `lang/<idioma>/**/*.json5` | ✅ | `modulos/misiones.py` y `formatos/lang_json5.py`, comprobado en el código de FTB Quests (`TranslationManager`, `TranslationTable`). Lo que sigue dentro de los capítulos `.json5` (aviso de recompensa, mensaje de bloqueo, nombres de recompensa) aún no: se avisa. |
| BetterQuesting | `DefaultQuests.json`, carpeta `DefaultQuests/` | ✅ | |
| BetterQuesting v3 y lang | `properties.betterquesting.name/desc`, `DefaultQuests.lang`, `resources/betterquesting/lang/` | 🟡 | por confirmar en el corpus |
| HQM, Heracles, Odyssey | `config/hqm`, `config/heracles`, `config/odyssey` | ✅ | |

### Scripts

| Fuente | Estado | Notas |
|---|---|---|
| KubeJS: tooltips, nombres, mensajes, JEI/REI/EMI info, comandos de chat | ✅ | API por versión en `formatos/kubejs_api.py` |
| KubeJS: nombres de grupos de REI (`REIEvents.groupEntries`, `onEvent('rei.group')`) | ✅ | Solo el segundo argumento de `group*` (el primero es el id). Pedido aparte, con el tono de la interfaz, para no cambiar los lotes de los scripts. |
| KubeJS Ponder (`scene.text`), `addAnnouncement`, `.respond`, `.append` | ❓ | por confirmar en el corpus |
| KubeJS `withName`, `withCustomName`, `withLore` (nombre y descripción de un objeto en el script) | ❌ | **Se dejan a propósito (decidido el 23-11).** Cambian el NBT o los componentes del objeto. Si ese objeto se usa como ingrediente, como objeto que pide una tarea o en una comparación, traducir el nombre haría que el juego ya no lo reconozca, como pasaba con las tareas de FTB Quests (H-039). El script no dice para qué se usa cada uno. |
| CraftTweaker (`.zs`) | ✅ | |

### Datos (datapacks)

| Fuente | Dónde vive | Estado | Notas |
|---|---|---|---|
| Funciones, logros, loot tables / item modifiers, Tips | `data/<ns>/…` en datapacks del pack | ✅ | `modulos/datos.py` |
| Los mismos datos **dentro de los jars** de los mods | jar | ❌ | Se pisan con un datapack del mismo id que reemplaza el archivo entero (solo los tags se juntan). El mejor lugar es `kubejs/data`, que en KubeJS 1.20.1 va encima de todo, o los datapacks del mundo. Riesgo: congela la versión del mod de ese archivo. Lo mejor es usar `{"translate":…,"fallback":original}` (desde 1.19.4). |
| Otros registros con texto | `enchantment` (`description`), `painting_variant` (`title`, `author`), `jukebox_song`, `trim_material`/`trim_pattern`, `instrument`, `dialog` (26.x) | ❌ | WTEM los cubre (`DefaultResourceHandlers`) |
| Estructuras `.nbt` | `data/<ns>/structure(s)/*.nbt`: carteles, libros, nombres y lore de objetos en cofres, `CustomName` | ❌ | en jars y en datapacks; WTEM las reescribe |
| Origins / Apoli | `data/<ns>/origins`, `origin_layers`, `powers` | ✅ (⛔ orígenes literales de 1.11–1.12) | **Cambia según la versión.** Origins ≤1.10 (MC ≤1.20.1) y el port de Forge: el texto se usa como **clave** (`Text.translatable`), así que basta una clave igual al texto en el resource pack. Origins 1.11–1.12 (1.20.2–1.20.4): orígenes y capas son **literales** (hay que reescribir); los poderes son clave. Origins 1.13 / Apoli 2.12 (1.21): literal con clave derivada (`origin.<ns>.<ruta>.name`, `power.<ns>.<ruta>.name`), que se pisa con el resource pack. NeoOrigins: una cadena es clave. Insignias: `origins:tooltip` `text` es literal. Nunca tocar `condition`, `type`, `impact`, `icon`, `sprite` ni los subárboles de acciones. |
| Componentes `translate` con `fallback` sin entrada en en_us (BACAP) | cualquier dato | ❓ | por confirmar |

### Menús, NPC y configuración

| Fuente | Dónde vive | Estado | Notas |
|---|---|---|---|
| FancyMenu v3 (y Drippy) | `config/fancymenu/customization/*.txt` | ✅ | Texto: `label`, `hoverlabel`, `description` de los botones; `source` de los textos con `source_mode = direct`; `slider_label`, `tooltip`. Salto de línea `%n%`. Lo seguro es cambiar el texto por `{"placeholder":"local","values":{"key":"…"}}` y poner la clave en el resource pack. Riesgos: `identifier`, texturas, acciones, `linked_variable`. |
| FancyMenu v2 | igual | ✅ | `addtext` → `value`; `addbutton` → `label`, `hoverlabel`, `description` (ahí `value` es la **acción**); `%local:<clave>%`. |
| CustomMainMenu (1.12) | `config/CustomMainMenu/*.json` | ✅ | Se reescriben en su lugar `buttons.*.text`, `hoverText`, `tooltip`, `labels.*.text`, `hoverText` y los splash de `other.splash-text.texts`. Un valor que ya es clave lo traduce el juego; `web:` y `file:` son fuentes. Los marcadores `#modsloaded#` se protegen. |
| Anuncio de servidor de BisectHost Menu | `config/bhmenu-client.toml` | ✅ | `title` y `description` de `[modules.server_creator_banner.pack]`, salvo que `use_language_files = true`. Se reescriben línea por línea; el código de un cupón («CODE: LunaPixel») se protege. |
| CustomNPCs | `<mundo>/customnpcs/dialogs`, `quests` (JSON-NBT con `1b`, `3L`) | ❌ | `DialogTitle`, `DialogText`, `Options[].Title`; `Title`, `Text`, `CompleteText`. No hay mecanismo de idioma: solo reescribir, con un lector tolerante. Riesgo: `DialogCommand`. |
| Easy NPC | presets `.npc.snbt` en `config/easy_npc/` | ❌ | Un texto con forma de clave con puntos se usa como clave. |
| Información de EMI | `assets/emi/recipe/additions/*.json` `text` | ❓ | cada texto pasa por `translatable`: sirve una clave |
| Mensajes en configuración (bienvenida, MOTD…) | `config/*.toml`, `.json5`, `.cfg` | ❓ | depende de cada mod |

### Problemas de otros mods que se ven con la traducción

- **Restricted Portals (Fabric 1.20.1, con Java 17 en Windows)** arma sus logros con el nombre de los objetos de KubeJS y
  los escribe en la carpeta del mundo con la codificación del sistema (cp1252), no en UTF-8. El juego los lee como UTF-8,
  así que cualquier tilde, «ñ» o comilla angular sale como `◆`. Lo vio la sonda en Spectral Creation. No es de la app:
  pasa con cualquier nombre en español. Se arregla en el launcher, agregando `-Dfile.encoding=UTF-8` a los argumentos de
  Java de la instancia (desde Java 18 ya es así por defecto).

### Lo que no es texto que se pueda traducir

- **Texto dentro de imágenes** (texturas y GUI con letras): fuera de alcance.
- **Texto escrito en el código Java** de los mods: lo cambia el mod de apoyo cuando es idéntico a la tabla (`modulos/runtime.py`).
  Lo que una pantalla dibuja directamente necesita un Mixin.
- **Datos de los mundos** (carteles colocados, entidades, marcadores): son del mundo del jugador, no del modpack, salvo en los
  mapas de aventura. Fuera de alcance por ahora (WTEM lo hace para mapas).

## Resultados

### 19 de noviembre de 2026 · 47 modpacks

**El corpus:** 47 packs enteros (24,4 GB más tres con Origins). Son 16 de FTB y 31 de Modrinth, de 1.7.10 a 26.3, con Forge,
NeoForge, Fabric y Quilt. Todos los archivos están verificados por hash; los mods de CurseForge que no permiten la
distribución no se buscan por otros caminos. El «antes» es el código de `origin/main` (PR #44); el «después», esta rama.

| | Antes | Después |
|---|---|---|
| Claves de idioma en inglés que la app ve (1.673.802) | 99,2 % | 99,2 % |
| Resto del texto que encontró el inventario y la app recoge (386.850) | 41,8 % | 43,3 % (+5.963) |

Textos que la app recoge con los módulos nuevos (las cifras de abajo cuentan los que tienen clave; en la fila de arriba solo
entra lo que el inventario reconoce fuera de los archivos de idioma):

| Módulo nuevo | Packs | Textos |
|---|---|---|
| Opciones de los shaders | 25 | 37.110 (hasta 3.870 en un pack) |
| Descripciones de los mods | 22 | 6.036 |
| Orígenes de Origins | 3 | 871 |
| Menús de FancyMenu | 16 | 275 |
| **Total** | | **≈ 44.300** |

Las claves de idioma ya estaban casi completas. Lo que falta del 0,8 % son sobre todo archivos que el juego no carga: los
`.lang` dentro de jars de 1.13 o más nuevos, el idioma de servidor en `data/<espacio>/lang`, y `config/jaopca/lang`.

**Qué queda del «resto» y por qué.** El 57 % que la app no recoge es casi todo texto que el jugador no ve, o que no es del
modpack:
- comentarios y descripciones de opciones de configuración;
- nombres internos de estructuras;
- metadatos de mods sin pantalla que los muestre: Forge `mods.toml` y `mcmod.info` no tienen clave, y en Fabric sin Mod
  Menu no se ven;
- notas de resource packs, menús de ejemplo dentro de jars, temas del editor de FancyMenu y nombres propios de lugares.

Lo que sí se ve y queda en inglés, ordenado por cuántos packs lo tienen:

| Brecha | Packs | Textos | Por qué no se hizo ahora |
|---|---|---|---|
| Datos con texto literal **dentro de los jars** (logros, loot tables, funciones) | 13 | ≈ 700 | **Fuera de alcance (decidido el 19-11).** Hace falta un datapack de reemplazo que copia el archivo entero del mod (lo congela en su versión) y solo se carga si el pack tiene KubeJS, Paxi u OpenLoader. |
| Carteles, libros y objetos con nombre en **estructuras `.nbt`** de los jars | 14 | ≈ 1.700 | **Fuera de alcance (decidido el 19-11).** Igual que lo anterior, más reescribir NBT de estructuras. WTEM sirve de referencia. |
| `splashes.txt` de mods y packs | 7 | ≈ 85 | Un solo archivo para todos los idiomas: reemplazarlo cambia los splash también para quien juegue en inglés con el pack activo. |

Lo que esta tabla tenía además (grupos de REI, recompensas de FTB Quests, plantillas de Patchouli, CustomMainMenu y
BisectHost) quedó hecho en la segunda ronda: ver «Segunda ronda» más abajo.

### Dentro del juego · NeoForge 1.21.1 (Create Ultimate, 81 mods)

**Cómo se probó.**
- La instancia se tradujo con el simulador, así que todo lo que la app tradujo empieza con «ES».
- Se abrió en un Prism Launcher portátil con la sonda (`mod-runtime/sonda/neoforge-1.21.1`) y el juego en `es_mx`.
- `analizar_sonda.py --con-app` clasificó cada clave del idioma cargado.

**Lo que costó.** La red de este PC falla a ratos con el DNS. El instalador de NeoForge se quedó en un diálogo de error al no
poder bajar los mappings de Mojang. `completar_prism.py` los bajó con reintentos y la IP de respaldo, con el sha1
verificado, sin tocar el DNS ni el archivo hosts del sistema.

| Claves del idioma cargado (34.619) | Cuántas | Qué son |
|---|---|---|
| Traducidas por la app (llevan «ES») | 13.159 | |
| En inglés que la app tenía | 1.341 | El simulador no pasa la regla de «quedó en inglés» (su respuesta repite el original): con un motor real se traducen o se reintentan. |
| En inglés de archivos que la app ve | 12 | Nombres propios de Ponder («Peter», «Albert») y nombres de logros que el mod deja igual en su español. |
| Iguales en el español del propio juego | 129 | El `es_mx` oficial de Mojang las deja así («Badlands», «Allium»). Correcto. |
| **Del loader** (NeoForge y etiquetas `c`) | 281 + ≈ 470 | **Brecha real**: su jar está en `libraries/` del launcher, fuera de `mods/`. NeoForge trae `es_es` pero no `es_mx`, y lo que falta en un idioma cae al inglés. Se arregló con el módulo «Textos del loader». |

Antes de la sonda, ningún análisis de archivos podía ver esta brecha: es justo para lo que se pensó la prueba en el juego.

**Después del arreglo**, la misma instancia, traducida otra vez y vuelta a abrir:

| | Antes | Después |
|---|---|---|
| Claves con la marca de traducción | 13.159 | 13.698 |
| En inglés del loader | 281 | 71 |
| En inglés creadas al jugar (etiquetas `c` y otras) | 430 | 2 |

- Las 71 del loader que quedan son de FancyModLoader (`fml.loadingerrorscreen…`, `fml.messages…`), que es otro jar.
  Solo se ven en la pantalla de error cuando un mod no carga.
- Las 2 creadas al jugar son atajos de KubeJS («KubeJS», «Kubedex»), que son nombres propios.
- Lo que quedó «en inglés que la app tenía» (1.331) es del simulador: con un motor real esos textos se traducen o se
  reintentan.

**La calidad no cambió.** `puerta_calidad.py`, con las respuestas grabadas de los bancos de interfaz, libros y misiones, dio
idéntico a la línea base después de cada arreglo: las mismas traducciones, las mismas métricas y ningún pedido nuevo.

**Lo que ya se traducía sale igual.** `foto_corpus.py` tradujo con el simulador 14 packs representativos. Abarcan de
1.7.10 a 26.x y todas las fuentes: misiones, libros, scripts, datos, shaders, FancyMenu, descripciones y Origins. Cada pack
se tradujo dos veces, con el código de `origin/main` y con esta rama.
- **14 de 14:** cada archivo que la versión anterior escribía sale idéntico. Solo aparecen archivos nuevos de los módulos
  nuevos, y solo cambian dos metadatos con fecha (la marca del pack y el registro de copias).
- **`restaurar` deja byte por byte cada archivo que existía.** Por diseño, a un archivo que la app creó le deja un contenido
  neutro que el juego muestra como el original: `{ }` en el `lang/es_*.snbt` de FTB Quests y el inglés en un libro propio.
  `options.txt` sigue con el pack activado (eso es una preferencia del jugador, no un archivo del modpack).

**El inventario también se equivocó, y se corrigió.** La primera pasada contaba como texto:
- los archivos de idioma que el juego no carga (`lang/default/` de Create);
- libros en otros idiomas;
- listas de bloques de los shaders;
- comentarios y JavaScript dentro de jars;
- nombres de modificadores de atributos en NBT.

El comparador, por su parte, no reconocía trozos cortos ni títulos de markdown («### The Big One»), y daba por faltantes
textos que la app sí traducía: misiones de FTB Quests con componentes JSON y guías de AE2. Cada caso se revisó con
ejemplos reales antes de cambiar una regla.

### Segunda ronda · 19 de noviembre de 2026 (rama `feat/cobertura-pendientes`)

Lo que quedaba de la tabla de brechas, más dos huecos que encontró la sonda en el juego.

| Arreglo | Dónde aparece en el corpus | Cómo se cuidó la calidad |
|---|---|---|
| Idioma de FancyModLoader (NeoForge) | las instancias de NeoForge | Módulo del loader, espacio propio en el resource pack |
| Menú de CustomMainMenu (1.12) | 8 packs, ≈ 44 textos | Módulo nuevo al final |
| Anuncio de BisectHost Menu | 12 packs, 24 textos (el código del cupón protegido) | Módulo nuevo al final |
| Nombres de grupos de REI en KubeJS | 11 packs, 42 textos | Pedido aparte, con el tono de la interfaz |
| Nombres de recompensas de FTB Quests | 8 packs, ≈ 80 textos | Pedido aparte; nunca bajo `tasks` |
| Campos de plantillas propias de Patchouli | Blood Magic, Animus, Enchanted, Mythic Mounts, Bonsai Trees, Extreme Reactors… ≈ 1.300 textos con los jars repetidos | Pedido aparte; solo el valor entero de un componente de texto |
| **Lang con saltos de línea sin escapar** | 8 jars (Shoulder Surfing en cuatro versiones, Extended Drawers…), 1.268 claves | El juego (Gson) los acepta; la app saltaba el archivo entero sin avisar. Lo vio la sonda en Fabric. |

Un texto nuevo que vive dentro de un archivo que ya traducía otro módulo (un capítulo de FTB Quests, un libro, un script)
va en un pedido aparte, con su ámbito, para que los lotes y las pistas de lo de antes salgan idénticos (ver
`CONTRIBUTING.md`). La puerta de calidad dio idéntico a la línea base antes de cada commit.

**Dentro del juego · Forge 1.20.1 (Better MC 4, 366 mods).** La instancia se tradujo con el simulador y se recorrió a mano:
creativo, logros, libro de misiones y libros guía.

| | Código de `main` | Esta rama |
|---|---|---|
| Claves cargadas | 213.402 | 214.610 |
| Con la marca de traducción | 172.946 | 173.907 |
| En inglés en archivos que la app ve | 182 | 176 |
| En inglés que la app tenía (el simulador no pasa la regla de «quedó en inglés») | 6.804 | 6.419 |
| Del loader | 1 | 1 |
| Claves crudas en pantalla | 3 | 2 (`enchantment.galosphere.sifting.desc` y `1.20.1`: tampoco existen en el inglés del mod) |

La primera corrida tenía menos mods: el verificador de Better MC instaló 51 que faltaban, así que la segunda columna
cuenta también los suyos. En pantalla se vio la marca en el menú de Sodium, los logros de When Dungeons Arise, las
pestañas del creativo, las misiones y sus recompensas. Lo que sigue en inglés y no tiene clave («Search options...» de
Reese's Sodium Options, «Hide Recipes») está escrito en el código del mod.

**Dentro del juego · Fabric 1.20.1 (Spectral Creation, 367 mods).** La primera vez la instancia arrancó sin Fabric:
`descargar_packs.py` ponía el loader antes que Minecraft en `mmc-pack.json` (15 packs del corpus; ya está arreglado). La
sonda tampoco volcaba el idioma, porque Server Translations reemplaza el idioma del juego por su propia clase; ahora lo
avisa y lo arma desde los recursos.

| | Cuántas |
|---|---|
| Claves cargadas | 26.912 |
| Con la marca de traducción | 10.041 |
| En inglés en archivos que la app ve | 140 (la mayoría nombres de vanilla que el `es_mx` de Mojang deja iguales: «Allium», «Sculk») |
| Creadas al jugar | 302 (Amendments arma las descripciones de su configuración; Extended Drawers era el hueco de los saltos de línea, ya arreglado) |
| En inglés que la app tenía | 1.108 (efecto del simulador) |
| Claves crudas en pantalla | 0 |

**Lo que ya se traducía sale igual.** `foto_corpus.py` tradujo los 14 packs representativos con el código de `main`
(PR #46) y con esta rama:
- **10 de 14** salen idénticos en todo lo que ya se escribía; solo suman archivos nuevos (BisectHost, CustomMainMenu y el
  idioma de Extended Drawers, MossyLib y ParticleEffects, que antes se descartaban).
- **4 packs** (ftb-100, ftb-102, ftb-115 y ftb-130) cambian archivos que ya se escribían, porque ahora llevan además los
  campos nuevos. En ftb-102 y ftb-100 se tradujo con los dos códigos y se comparó campo por campo: lo único distinto son los
  nombres de recompensa, los `heading` de las plantillas de Blood Magic y los nombres de los grupos de REI. ftb-115 y
  ftb-130 cambian por las mismas reglas (recompensas, Blood Magic y Bonsai Trees).
- **14 de 14:** `restaurar` deja byte por byte cada archivo que existía.

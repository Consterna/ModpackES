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
| Jars anidados de Fabric/Quilt declarados en `fabric.mod.json` → `jars` fuera de `META-INF/jars` | jar dentro de jar, en la raíz u otra carpeta | ❌ | Fabric carga lo que declara `jars[].file`. La app solo mira `META-INF/jars`, `jarjar` y `jarinjar`. Visto en Simple Pipes (FTB Cotton). |
| KubeJS, ResourceLoader, Global Packs, OpenLoader, Paxi, packs activos | `kubejs/assets`, `resources/`, `global_packs/…`, `config/openloader`, `config/paxi`, `resourcepacks/` | ✅ | `fuentes/recursos.py` |
| Lang de shaderpacks (Iris/Oculus) | `shaderpacks/<pack>/shaders/lang/en_US.lang`, en zip o en carpeta | ❌ | Iris usa el lang del shaderpack solo si la clave **no** está en el idioma del juego. Por eso un resource pack con `option.X`, `screen.X`, `value.X.<v>`… lo pisa (Iris `MixinClientLanguage`, `LanguageMap`). Con OptiFine, sin confirmar. Las claves son globales: dos shaders pueden chocar. |
| Descripción del mod en la lista de mods | `fabric.mod.json`/`quilt.mod.json` `description`; `mods.toml` `description` | ❌ | Mod Menu lee `modmenu.descriptionTranslation.<modid>` y `modmenu.summaryTranslation.<modid>` si existen (`Mod.java`). NeoForge 20.4–21.x lee `fml.menu.mods.info.description.<modid>` (PR #649); desde la renovación de la lista (#3073), `neoforge.screen.mods.info.description.<modid>`. **Forge no tiene clave** (`ModListScreen`): ⛔ sin código. |
| Claves que se crean mientras el juego corre | ARRP/BRRP, Moonlight, KubeJS `ClientEvents.lang`, PonderJS (`kubejs/assets/ponderjs_generated/lang`) | 🟡 | Si el pack generado solo trae `en_us`, nuestro `es_*` gana siempre (cada idioma se aplica después de en_us). ARRP `AFTER_VANILLA` va encima de los packs del usuario. En KubeJS 1.20.1 su pack se mete **antes del primer pack .zip** del usuario: con el nuestro en carpeta, KubeJS podría quedar encima. Hay que verlo en el juego (sonda). |

### Libros guía

| Fuente | Dónde vive | Estado | Notas |
|---|---|---|---|
| Patchouli 1.17+ con `use_resource_pack` y 1.20+ | `assets/<ns>/patchouli_books/<libro>/<idioma>/` | ✅ | `modulos/libros.py` |
| Patchouli con `"i18n": true` y Modonomicon | claves de idioma | ✅ | como libro, con su tono |
| Patchouli 1.14–1.19 dentro del jar (`data/<ns>/patchouli_books/…`) | jar | ⛔ | Se carga del classpath. Ni un resource pack ni un datapack lo pisan. «Patchouli Resource Patch» (PRP-Arch, 1.15–1.19) hace que lea primero de assets, pero solo reemplaza archivos que ya existen. Opción: informar y sugerir PRP, o hacer lo mismo en el mod de apoyo. |
| Libros propios del modpack | `<instancia>/patchouli_books/` | ✅ | se reescriben en su lugar |
| Mantle, Citadel, Lavender, GuideME | `assets/<ns>/book/…`, `lavender/…`, `<carpeta>/_<idioma>/` | ✅ | |
| Guía de ParCool | `assets/parcool/book/parcool_guide_content_<idioma>.txt` | ❌ | la traduce a mano el pack «Traducciones de Mods» |

### Misiones

| Fuente | Dónde vive | Estado | Notas |
|---|---|---|---|
| FTB Quests: SNBT, carpeta `lang/` y NBT de 1.12 | `config/ftbquests/quests/` | ✅ | `modulos/misiones.py` |
| FTB Quests en otras raíces | `config/ftbquests/normal/` (FTB Interactions Remastered), `config/ftb_quests/`, `defaultconfigs/ftbquests/` | ❌ | por confirmar en el corpus |
| FTB Quests en JSON5 | `data.json5` y lang `.json5` | ❌ | por confirmar |
| BetterQuesting | `DefaultQuests.json`, carpeta `DefaultQuests/` | ✅ | |
| BetterQuesting v3 y lang | `properties.betterquesting.name/desc`, `DefaultQuests.lang`, `resources/betterquesting/lang/` | 🟡 | por confirmar en el corpus |
| HQM, Heracles, Odyssey | `config/hqm`, `config/heracles`, `config/odyssey` | ✅ | |

### Scripts

| Fuente | Estado | Notas |
|---|---|---|
| KubeJS: tooltips, nombres, mensajes, JEI/REI/EMI info, comandos de chat | ✅ | API por versión en `formatos/kubejs_api.py` |
| KubeJS Ponder (`scene.text`), `addAnnouncement`, `.respond`, `.append` | ❓ | por confirmar en el corpus |
| CraftTweaker (`.zs`) | ✅ | |

### Datos (datapacks)

| Fuente | Dónde vive | Estado | Notas |
|---|---|---|---|
| Funciones, logros, loot tables / item modifiers, Tips | `data/<ns>/…` en datapacks del pack | ✅ | `modulos/datos.py` |
| Los mismos datos **dentro de los jars** de los mods | jar | ❌ | Se pisan con un datapack del mismo id que reemplaza el archivo entero (solo los tags se juntan). El mejor lugar es `kubejs/data`, que en KubeJS 1.20.1 va encima de todo, o los datapacks del mundo. Riesgo: congela la versión del mod de ese archivo. Lo mejor es usar `{"translate":…,"fallback":original}` (desde 1.19.4). |
| Otros registros con texto | `enchantment` (`description`), `painting_variant` (`title`, `author`), `jukebox_song`, `trim_material`/`trim_pattern`, `instrument`, `dialog` (26.x) | ❌ | WTEM los cubre (`DefaultResourceHandlers`) |
| Estructuras `.nbt` | `data/<ns>/structure(s)/*.nbt`: carteles, libros, nombres y lore de objetos en cofres, `CustomName` | ❌ | en jars y en datapacks; WTEM las reescribe |
| Origins / Apoli | `data/<ns>/origins`, `origin_layers`, `powers` | ❌ | **Cambia según la versión.** Origins ≤1.10 (MC ≤1.20.1) y el port de Forge: el texto se usa como **clave** (`Text.translatable`), así que basta una clave igual al texto en el resource pack. Origins 1.11–1.12 (1.20.2–1.20.4): orígenes y capas son **literales** (hay que reescribir); los poderes son clave. Origins 1.13 / Apoli 2.12 (1.21): literal con clave derivada (`origin.<ns>.<ruta>.name`, `power.<ns>.<ruta>.name`), que se pisa con el resource pack. NeoOrigins: una cadena es clave. Insignias: `origins:tooltip` `text` es literal. Nunca tocar `condition`, `type`, `impact`, `icon`, `sprite` ni los subárboles de acciones. |
| Componentes `translate` con `fallback` sin entrada en en_us (BACAP) | cualquier dato | ❓ | por confirmar |

### Menús, NPC y configuración

| Fuente | Dónde vive | Estado | Notas |
|---|---|---|---|
| FancyMenu v3 (y Drippy) | `config/fancymenu/customization/*.txt` | ❌ | Texto: `label`, `hoverlabel`, `description` de los botones; `source` de los textos con `source_mode = direct`; `slider_label`, `tooltip`. Salto de línea `%n%`. Lo seguro es cambiar el texto por `{"placeholder":"local","values":{"key":"…"}}` y poner la clave en el resource pack. Riesgos: `identifier`, texturas, acciones, `linked_variable`. |
| FancyMenu v2 | igual | ❌ | `addtext` → `value`; `addbutton` → `label`, `hoverlabel`, `description` (ahí `value` es la **acción**); `%local:<clave>%`. |
| CustomMainMenu (1.12) | `config/CustomMainMenu/*.json` | ❌ | El `text` de los botones pasa por `I18n` (sirve una clave); las etiquetas no, así que hay que reescribirlas. |
| CustomNPCs | `<mundo>/customnpcs/dialogs`, `quests` (JSON-NBT con `1b`, `3L`) | ❌ | `DialogTitle`, `DialogText`, `Options[].Title`; `Title`, `Text`, `CompleteText`. No hay mecanismo de idioma: solo reescribir, con un lector tolerante. Riesgo: `DialogCommand`. |
| Easy NPC | presets `.npc.snbt` en `config/easy_npc/` | ❌ | Un texto con forma de clave con puntos se usa como clave. |
| Información de EMI | `assets/emi/recipe/additions/*.json` `text` | ❓ | cada texto pasa por `translatable`: sirve una clave |
| Mensajes en configuración (bienvenida, MOTD…) | `config/*.toml`, `.json5`, `.cfg` | ❓ | depende de cada mod |

### Lo que no es texto que se pueda traducir

- **Texto dentro de imágenes** (texturas y GUI con letras): fuera de alcance.
- **Texto escrito en el código Java** de los mods: lo cambia el mod de apoyo cuando es idéntico a la tabla (`modulos/runtime.py`).
  Lo que una pantalla dibuja directamente necesita un Mixin.
- **Datos de los mundos** (carteles colocados, entidades, marcadores): son del mundo del jugador, no del modpack, salvo en los
  mapas de aventura. Fuera de alcance por ahora (WTEM lo hace para mapas).

## Resultados

(Se completan con las mediciones del corpus.)

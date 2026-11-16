# Cambios

Todos los cambios importantes de ModpackES quedan en este archivo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- **Perfiles de calidad** («Calidad» en la ventana y `--calidad` en `analizar` y `traducir`). El análisis estima el costo de cada uno:
  - **Equilibrado** (por defecto): después de traducir, lo que quedó con dudas (cifras distintas, un paréntesis sin cerrar, usted, inglés, un término del glosario…) se corrige una vez explicando qué falló. La corrección se queda solo si pasa las reglas y un juez a ciegas la prefiere en los dos órdenes; si no, queda la primera, marcada. Cuesta cerca de un 5 % más.
  - **Máximo:** además, cada texto corto (6 palabras o menos: nombres, botones) se traduce tres veces en lotes distintos. Gana la traducción en que coinciden dos; si no coinciden, gana la de mejor promedio entre tres señales (dudas del control de calidad, términos del glosario y parecido con las otras), y el texto queda marcado para revisarlo. También activa la revisión de misiones y libros. Cuesta un 30 % más, más la revisión. Con Gemini 3.8 Flash no mejoró de forma medible (ver [docs/calidad.md](docs/calidad.md)): queda como opción.
  - **Económico:** solo los arreglos automáticos, como hasta ahora.
- **La revisión de misiones y libros ya no acepta a ciegas lo que rehace:** la versión nueva tiene que ganarle a la anterior ante un juez que no sabe cuál es cuál, en los dos órdenes. Un modelo que corrige su propia traducción tiende a cambiar cosas que estaban bien.
- **Control de calidad determinista** después de cada traducción, con las ideas de las herramientas de QA de la industria y las convenciones del español de Minecraft:
  - Se arregla solo lo que no tiene riesgo: espacios dobles o antes de la puntuación, caracteres invisibles, una palabra repetida seguida, «¿» y «¡» que faltan en una frase única, el «:» o los «...» finales que se perdieron (el juego escribe «...», no «…»), las comillas del dialecto (es_es «», es_mx "") si el original las tiene, y meses y días con mayúscula a mitad de frase. Los códigos de formato no se tocan.
  - Queda como duda, para revisarlo: cifras distintas del original (con tolerancia a «1,000» = «1.000» y a las cifras escritas con letras), paréntesis o corchetes sin pareja, formas de usted (el juego tutea), palabras en inglés que quedaron, y frases que se perdieron.
  - Las mayúsculas de título en un nombre («Espada de Diamante») solo se informan: medido sobre las respuestas grabadas, bajarlas acertaba 3 veces y fallaba 10 (nombres propios como «Wither»).
  - Al terminar, la lista completa de lo dudoso se guarda en un CSV (`informes/dudosos-<pack>-<fecha>.csv` en la carpeta de datos) y el registro dice cuántos arreglos de forma se hicieron.
- **Importar un resource pack también trae sus libros de Patchouli:** cada archivo del libro en español se empareja con el mismo archivo en inglés del mod, campo por campo, y solo si los dos tienen la misma forma.
- **Pista para las escenas de Ponder** (Create): las claves `*.ponder.*` llegan al motor como «texto de una escena de Ponder», para que traduzca frases cortas que explican lo que se ve.
- **Scripts de CraftTweaker** (`scripts/*.zs`): tooltips (`addTooltip`, `addShiftTooltip`), nombres (`displayName`, `setDisplayName`), descripciones de JEI (`addDescription` en 1.12, `addInfo` desde 1.16) y el texto de `game.setLocalization`. Ids, claves, comparaciones y comentarios no se tocan; queda copia de seguridad.
- **Loot tables e item modifiers:** el nombre (`set_name`), las líneas de descripción (`set_lore`) y, desde 1.20.5, `custom_name`, `item_name`, `lore` y las páginas de los libros escritos de `set_components`, en cualquier datapack. Lo que va como JSON dentro de una cadena se traduce por dentro y sigue siendo una cadena.
- **Nombres propios coherentes en misiones y libros:** los nombres con mayúscula que se repiten en varias frases («Arachnarch», «Bronze Dungeons») se deciden una sola vez antes de traducir y se fijan en el glosario del pack. El nombre de un jefe, una criatura única, una dimensión o un mod se deja igual. Antes un texto decía «Arachnarch» y otro «Aracnarca».
- **Versión aparte para España** (opcional; casilla en «Opciones avanzadas» y `--tambien-es-es`): el español elegido sigue yendo a todos los archivos de español salvo `es_es`, que recibe su propia traducción con los nombres del juego en es_es («Roca», «objeto»…). Solo con lo que tiene un archivo por idioma (mods, libros y la carpeta `lang/` de FTB Quests); los scripts y las misiones de los capítulos tienen un solo idioma. El análisis suma su costo, que es el de otra traducción la primera vez; después sale de la memoria. Cada texto de España va con la traducción latinoamericana como referencia, para que las dos versiones dejen sin traducir los mismos nombres y solo cambie lo que en España se dice distinto. Una palabra que no es del juego («inframundita») se corrige también en la traducción final.
- **Paquete de traducción compartible** (`.modpackes.zip`): «Más ▸ Exportar paquete de traducción…» y `modpackes paquete exportar` guardan la parte de la memoria que usa el modpack, tus correcciones de esos textos, tu glosario y los datos del pack (nombre, versión, Minecraft, dialecto, modelos y si se revisó). «Más ▸ Importar traducción…» y `modpackes paquete importar` lo aplican sin llamar a ningún motor; no pisan tus correcciones ni tus términos, descartan textos dañados (códigos cambiados, vacíos, enormes) y avisan si el paquete es de otro modpack, otra versión u otro Minecraft. Si faltan textos, la ventana dice cuántos quedan en inglés y ofrece traducirlos con el motor. Si se tradujo también la versión de España, el paquete la lleva en archivos aparte (un paquete viejo sigue sirviendo) y al aplicarlo `es_es` recibe la suya.
- **Importar un resource pack en español** (`.zip` o carpeta), aunque no esté activo en `options.txt`: sus textos se emparejan con el inglés de los mods de la instancia y pasan a la memoria, y luego se escribe la traducción sin gastar.
- **Pack listo para publicar:** «Exportar pack…» y `modpackes exportar` agregan `pack.png`, un `LEEME.txt` con aviso de traducción automática, si se revisó, los motores usados y créditos, la versión del modpack en el nombre del archivo (`Traduccion_ES_<pack>_<versión>.zip`) y `supported_formats` en el `pack.mcmeta` de 1.20.2 a 1.21.8. El kit de servidor lleva el mismo pack. El pack anota en su marca qué motores tradujeron algo.
- **Qué cambió desde la última traducción** (`modpackes cambios RUTA [--json]`; solo lee). Al actualizar un modpack, lista por mod y por archivo de misiones, libro o script las claves nuevas, las que cambiaron y las borradas, y estima el costo de traducir solo esa diferencia (lo que ya está en la memoria no cuenta). Al volver a analizar, la ventana muestra un resumen debajo del costo y `analizar` lo muestra en la consola. Cada traducción guarda en la marca del pack un índice con un hash corto de cada texto en inglés. Si el pack es de una versión anterior y no tiene índice, se compara con la memoria. Sigue la idea del `update` de [UpLang](https://github.com/QianFuv/UpLang), que compara el `en_us` viejo con el nuevo; aquí la comparación solo informa y «Traducir» aplica la diferencia.

- **Glosario del usuario desde la línea de comandos:** `modpackes glosario listar | agregar INGLÉS ESPAÑOL | quitar INGLÉS | importar ARCHIVO.json`. Son los términos (y los nombres que no se traducen) que quieres que salgan siempre igual; mandan sobre todo lo demás y, si faltan en una traducción, el texto se reintenta.

- **Texto escrito en el código de los mods** (opcional, apagado por defecto): la app traduce las frases que encuentra en el código Java de los
  mods y las guarda en una tabla del resource pack; el nuevo mod de apoyo **ModpackES Runtime** (solo cliente, para Forge 1.12.2, 1.16.5, 1.17.1, 1.18.2, 1.19.2 y 1.20.1, NeoForge 1.20.1, de 1.21 a 1.21.11 y de 26.1 a 26.3, y Fabric 1.19.4, de 1.20 a 1.20.6, de 1.21 a 1.21.11 y de 26.1 a 26.3, y Quilt con los mods de Fabric hasta 1.21.1) las muestra en
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

- **Libros más fieles al original:** el pedido de libros ya no dice «Escribe de forma clara y natural». Esa frase empujaba al modelo a reescribir en vez de traducir: sin ella, el chrF del banco de libros subió 1,45 (IC 0,80 a 2,12). Vale para todos los libros guía, en JSON o en archivos de idioma.
- **La memoria distingue cada modpack y recuerda lo dudoso:**
  - Cada traducción se guarda con su modpack y con su calidad: «ok», o el motivo por el que se aceptó con dudas.
  - Un modpack siempre usa lo suyo. De otro modpack solo usa lo que quedó bien: un término del glosario que no se cumplió en un pack ya no se copia a todos los demás.
  - Los nombres del propio juego mandan sobre la memoria («Lingote de hierro» aunque la memoria diga «Lingote de Hierro»). Por encima solo quedan tus correcciones y tu glosario.
  - Lo que la memoria tiene como bueno se vuelve a comprobar con los códigos y el glosario de hoy. Si ya no cumple (por ejemplo, agregaste un término), ese texto se traduce de nuevo una vez. Lo que se aceptó con dudas en el mismo pack no se vuelve a pedir, para no pagar en cada traducción.
  - La memoria se actualiza sola la primera vez que se abre: lo de antes queda como «ok» y para todos los packs, y se guarda una copia del archivo viejo (`memoria.sqlite.v1.bak`).
  - El paquete compartible (`.modpackes.zip`) lleva marcado lo dudoso; al aplicarlo, eso queda solo para ese modpack. Un paquete viejo sigue sirviendo.
- **Más contexto en los textos de los mods, sin costo extra:**
  - Los textos van al motor en el orden del archivo y no en orden alfabético, así que un lote junta el nombre de un objeto con su tooltip y el título de una misión con su descripción.
  - Un tooltip o una descripción dice de qué objeto habla («habla de «Teleporter»»).
  - Un texto corto de un menú («Any», «Left») va con las claves vecinas del archivo («junto a «Source Only», «None»»).
  - Si el inglés es igual a un texto del juego, la pista dice cómo lo traduce el juego («en el juego: «Alternar»»), para seguir el español de Minecraft.
  - Al decidir un nombre propio o un término que se repite, el motor recibe una o dos frases donde aparece.
  - Si el mismo texto sale con y sin espacios en los bordes, sus pistas se juntan en vez de pisarse.
  - La versión de España recibe hasta 1.500 caracteres de la traducción latinoamericana como referencia (antes 400), así que también los párrafos largos de los libros conservan las mismas decisiones.
- **Controles de forma sin depender del modelo.** Atacan lo que más se corrigió en la revisión humana de 100 textos:
  - Mayúsculas: un término del glosario que el original escribe como nombre propio («the Quantum Ring») sale con las mayúsculas del glosario («el Anillo Cuántico»). Los nombres del juego («Lingote de hierro», «Cofre») siguen en minúscula en medio de una frase.
  - Nombres que no se traducen: los del juego («Creeper», «Redstone») y los de una palabra que el modelo dejó igual al traducir los mods («Arachnarch») se protegen. Si una misión los traduce, se reintenta.
  - Palabras repetidas: un nombre corto que repite una palabra que el original no repite («Mejora de Salud mejorada») se reintenta.
  - Reintento acotado: el segundo intento recibe la primera traducción y se le pide corregir solo lo que falló. Si el término sigue en inglés, se cambia por el del glosario; lo que no se puede arreglar se acepta y se avisa como «aceptado con dudas».
- **Lo que el español del juego ya traduce manda.** Los nombres del juego se cargan antes que cualquier otro término, y cada dialecto sigue al suyo (es_mx dice «ítem» y es_es «objeto»). Un vocabulario base completa solo lo que el juego no trae suelto («Netherite» → «Netherita»), y una palabra que no es del juego («inframundita») se corrige en los términos de los mods. Un término corto dentro de uno largo («Item» en «Item Frame») ya no se exige aparte.
- **Aviso de lo aceptado con dudas:** al terminar, el informe dice cuántos textos se aceptaron sin cumplir el glosario, con una palabra repetida o con un aviso del control de calidad, con ejemplos y la ruta del CSV con la lista completa, para revisarlos en «Más ▸ Correcciones…».
- **Gemini 3.5 Flash-Lite, 3.6 Flash y posteriores ya no reciben `temperature`.** Google la ignora en esos modelos y anunció que las próximas generaciones la rechazarán. Además, cada modelo recibe un nivel de razonamiento que admite (la familia 4 no acepta «minimal»).
- **El glosario ya no deja que un mod imponga su traducción a todo el modpack.** Los nombres del propio juego (primero es_mx, después es_es) mandan sobre los de un mod, y si dos mods traducen distinto el mismo término no se usa ninguno. Antes un mod que llamaba «Acechador de medianoche» a la vaca hacía que todo el modpack la tradujera así.
- **Motores en tu PC (LM Studio, Ollama o un servidor en localhost):** los pedidos son más chicos (12 textos o 1.800 caracteres en vez de 60 o 5.000), porque un modelo pequeño se equivoca más con pedidos largos. Para medir sin saturar la GPU hay una «carga segura» en las herramientas de desarrollo (`medir_calidad.py --carga-segura`: pausas entre pedidos y espera si la GPU pasa de 80 °C).
- **Ya no se mandan ejemplos de otros mods al motor.** Con referencias limpias, los ejemplos parecidos bajaron el chrF de Gemini (−1,2, intervalo de −2,3 a −0,3) y la ganancia que se había medido antes con el contexto no se reprodujo; las pistas (clave y tipo de cada texto) se mantienen. Los ejemplos siguen en el código para probarlos con modelos locales; ver [docs/calidad.md](docs/calidad.md).
- **Contexto de vecindad en misiones y libros.** Cada texto de una misión o de un libro se manda al motor con el título bajo el que está y el texto que viene justo antes, para elegir mejor el sentido y el tono. En una comparación con un juez ganó el 56 % de los casos decididos, sin llegar a ser concluyente; ver [docs/calidad.md](docs/calidad.md).

- **El glosario ahora se exige.** Si un término del glosario sale en un texto y su traducción no lo usa (con tolerancia a plurales, tildes y mayúsculas), el texto se reintenta una vez con un aviso explícito; si sigue sin salir se acepta, para no dejar nada en inglés.

- **Traducciones más precisas.** Cada texto de un mod va ahora con de dónde sale y qué es («nombre de un objeto», «tooltip», «disco de música»…), y si el mismo texto sale en varios sitios se mandan hasta tres pistas. El motor recibe además ejemplos de textos parecidos ya traducidos (el español que traen los mods del modpack, la memoria y lo que se va traduciendo en esa misma ejecución) para seguir los mismos términos y estilo. Los términos que se repiten en los nombres («Moon Berries» en «Moon Berries Pie», «Moon Berries Jam»…) se traducen primero y se fijan en el glosario, para que todos los nombres usen la misma palabra. Un nombre que el motor devuelve igual al original se reintenta con un aviso; si sigue igual, se acepta. Con 250 textos reales de mods y Gemini 3.8 Flash, el chrF subió de 68,9 a 70,6 (promedio de tres corridas); ver [docs/calidad.md](docs/calidad.md).

- El kit para servidores incluye las funciones y los logros traducidos dondequiera que estén, también los de un datapack comprimido (`.zip`); los `.zip` que solo traen tips siguen fuera porque son de cliente.
- «Instalar el mod de apoyo» copia el mod nuevo antes de borrar los viejos, para no dejarte sin mod si la copia falla, y «Estado del mod de apoyo» avisa cuando el jar instalado es de otra versión de Minecraft en lugar de decir que todo está listo.

### Corregido

- **La máscara tapaba texto que no era código:** en «R&D», «Q&A» o «B&B», el «&D», «&A» o «&B» se tomaba por un código de color y el modelo no veía la palabra. Una frase entre llaves («{the quick brown fox}») también se tapaba entera. Ahora solo se protegen los códigos: «&6Wrench&r», «&c&l», `{image:…}`, `{@pagebreak}`, `{0}`, `{clave}`. Con las respuestas grabadas, ningún pedido de los tres bancos cambió.
- **Los libros guía que viven en los archivos de idioma se traducían como interfaz.** Desde Patchouli 1.20 casi todos los libros usan claves de idioma (`"i18n": true`), igual que Modonomicon, y la app los mandaba al motor como textos de menú, sueltos. Ahora sus claves («occultism.book.entries…», «…guide.entry…») se traducen como libro, con el título de la entrada y el texto anterior como contexto, y entran en la revisión de misiones y libros. Los nombres de objetos y los textos de menús o tooltips siguen como interfaz. Lo ya traducido de esas claves se vuelve a pedir una vez, con el tono de libro.
- **El glosario exigía términos donde la palabra tenía otro sentido:** «lead the way» pedía «Correa», «the power signal» pedía «Poder» y «the target» pedía «Diana». Ahora la app mira en el inglés y el español del juego y de los mods cómo se traduce cada palabra cuando va en minúscula. Si casi nunca sale con el término del glosario, ese término solo se manda y se exige cuando el texto lo usa como nombre: es todo el texto, va con mayúscula a mitad de frase o el texto es un nombre en estilo título. Las palabras que sí se traducen igual («fire» → «fuego») se siguen exigiendo, y los términos del usuario siempre.
- **Términos de un mod a medio traducir** («Almacen Portable de Energía», «slot de los Muslos») ya no entran en el glosario: se descarta el término que deja en español una palabra inglesa que no sale en ningún texto en español del juego ni de los mods. Los nombres de los mods de la instancia («estilo Create») no cuentan.
- **Artículo con el género equivocado** al cambiar un término que quedó en inglés: «Usa el Wrench» pasa a «Usa la Llave inglesa», no a «el Llave inglesa». Si no se sabe el género, no se cambia y queda como duda.
- **Frases que volvían en inglés después del reintento** se guardaban en la memoria como si fueran la traducción. Ahora solo se acepta lo que parece un nombre propio («Bronze Dungeons»), marcado para revisarlo; el resto queda sin traducir y se vuelve a intentar en la próxima traducción.
- **Argumentos al revés:** si el modelo cambiaba de orden dos `%s` («%s was slain by %s» → «… mató a …»), el juego ponía los valores al revés sin aviso. Ahora, en los archivos de idioma se numeran (`%2$s mató a %1$s`), como hace el propio español de Minecraft; en scripts, misiones y libros el texto se rechaza y se reintenta.
- **Escapes `\uXXXX` en scripts de KubeJS y CraftTweaker:** el modelo veía «⟦0⟧00a7cWarning» y podía romper el escape. Ahora los de caracteres visibles se decodifican («§cWarning», «éxito») y los de control quedan protegidos enteros.
- **Códigos que el modelo inventa o desordena:** se rechaza la traducción que trae un código que no estaba («§a», «%s») o que deja el cierre de un formato (`§r`, `$()`, `</b>`) antes de su apertura. Con argumentos, un «%» suelto que escribió el modelo pasa a «%%».
- **Se colaba un ejemplo en cada pedido** aunque la app no manda ejemplos (`CANTIDAD_EN_LA_APP = 0`): el tope se miraba después de agregar el primero. Los ejemplos de otros textos empeoraban la calidad y, como salían de lo traducido en esa misma ejecución, el mismo pedido cambiaba según el orden en que terminaban los hilos.
- **El glosario no veía los términos pegados a un código de color** («Defeat the &4Arachnarch», «&eBronze Dungeons»): no se mandaban al modelo ni se exigían. Ahora los códigos se quitan antes de buscar términos, en el original y en la traducción.
- **El pack no se activaba en una instancia nueva.** Si en `options.txt` solo estaban los packs internos (`["vanilla"]` o `["vanilla","mod_resources"]`), se escribía `Traduccion_ES` sin el prefijo `file/` que usa Minecraft desde 1.13, y el juego lo ignoraba. Ahora el formato sale de la versión de la instancia (también en 1.12, que no usa el prefijo).
- **«Guardar el informe de lo que queda…» no guardaba nada**, ni desde el menú «Más» ni desde el botón del cuadro del informe.
- **Libros propios del modpack** (`patchouli_books/` en la instancia): una segunda traducción no aplicaba las correcciones ni lo nuevo de la memoria, porque el español que había escrito la app se tomaba como traducción del autor; y después de «Restaurar el original», volver a traducir los dejaba en inglés.
- `traducir --simular` guardaba sus textos de prueba («ES» delante) en la memoria de traducciones, y una traducción de verdad posterior los reutilizaba. Ahora la simulación usa una memoria aparte.
- Las varias pistas de un texto que sale con distintas claves (hasta tres) llegaban al motor solo en las pruebas: la app mandaba una sola.
- En el mod de apoyo, una frase con índices explícitos fuera de orden (`"%2$s of %1$s"`) mostraba cada dato en el lugar del otro.
- El texto de un `hoverEvent` de objeto o criatura (`show_item`, `show_entity`) ya no se manda a traducir: en 1.12 es el SNBT del objeto y traducirlo rompía el comando.
- Cancelar con Gemini cortaba recién al agotar los reintentos (minutos); ahora corta enseguida, también durante la espera entre reintentos con los demás motores y en las pausas de la carga segura de los modelos locales (también mientras espera a que se enfríe la GPU).
- Cerrar la ventana mientras «Probar conexión» seguía esperando podía cerrar la app con un error de Qt.
- Unas preferencias dañadas (por ejemplo `"hilos": "muchos"`) impedían abrir la ventana, y una carpeta de un lanzador sin permiso de lectura también.
- «Restaurar el original» se cortaba a medias si faltaba alguna copia de seguridad: ahora restaura el resto, guarda lo hecho y dice cuáles faltan. Volver a traducir un archivo sin copia ya no falla.
- La línea de comandos muestra un mensaje claro, sin traza, ante un archivo bloqueado o sin permiso.

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

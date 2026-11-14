<div align="center">

<img src="src/traductor_es/ui/icono.png" alt="" width="96">

# ModpackES

**Traduce modpacks de Minecraft al español:** misiones, libros guía, scripts de KubeJS y los textos de
todos los mods, con un par de clics.

[![CI](https://github.com/Consterna/ModpackES/actions/workflows/ci.yml/badge.svg)](https://github.com/Consterna/ModpackES/actions/workflows/ci.yml)
[![Última versión](https://img.shields.io/github/v/release/Consterna/ModpackES?label=versi%C3%B3n)](https://github.com/Consterna/ModpackES/releases/latest)
[![Licencia GPL-3.0](https://img.shields.io/badge/licencia-GPL--3.0-blue)](LICENSE)
![Windows 10 y 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6)
![Minecraft 1.7.10 a 26.x](https://img.shields.io/badge/Minecraft-1.7.10%20a%2026.x-62B47A)

[**Descargar el instalador**](https://github.com/Consterna/ModpackES/releases/latest/download/ModpackES-instalador.exe)
· [versión portable](https://github.com/Consterna/ModpackES/releases/latest/download/ModpackES.exe)
· [Cómo se usa](#cómo-se-usa) · [Preguntas frecuentes](#preguntas-frecuentes) · [Cambios](CHANGELOG.md)

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/captura-claro.png">
  <img src="docs/captura.png" alt="Ventana de ModpackES con un modpack analizado: tarjetas de instancias a la izquierda; a la derecha, los pasos, las cantidades de mods, libros, misiones y scripts, y el botón «Traducir 295 textos · US$ 0,01»" width="820">
</picture>

</div>

## Qué hace

ModpackES lee tu modpack, encuentra todo lo que sigue en inglés y lo traduce con Gemini de Google o con
cualquier motor compatible con OpenAI, incluidos modelos que corren gratis en tu PC (LM Studio, Ollama).
Funciona con **cualquier versión** (de 1.7.10 a 26.x), **cualquier loader** (Forge, NeoForge, Fabric, Quilt)
y **cualquier lanzador**, y escribe a la vez las siete variantes de español del juego.

- **No modifica los jars de los mods.** Lo de los mods va en un resource pack aparte.
- **Todo tiene copia de seguridad.** Un botón devuelve el modpack a su texto original.
- **No se paga dos veces.** Lo ya traducido queda en una memoria que se reutiliza, también entre modpacks.
- **Respeta los formatos.** Colores, enlaces, variables y comandos llegan intactos; lo que no pasa las
  reglas de calidad se reintenta o queda en inglés antes que romper algo.

| Contenido | Formatos | Dónde queda |
|---|---|---|
| Textos de mods (objetos, bloques, menús, tooltips) | `lang/*.json` (1.13+) y `.lang` (1.12 y antes), incluidos los jars anidados, KubeJS y los resource packs del modpack | Resource pack `Traduccion_ES` |
| Misiones | FTB Quests (texto en los capítulos, carpeta `lang/` de 1.21+ y NBT de 1.12), BetterQuesting, HQM, Heracles | En su sitio, con copia de seguridad |
| Libros guía | Patchouli, Mantle (Tinkers), Citadel (Alex's Mobs), GuideME (AE2), Lavender. Modonomicon va por claves de idioma | Resource pack (o en su sitio, si es un libro propio del modpack) |
| Scripts de KubeJS | Lo que ve el jugador: `tell`, `notify`, `displayName`, `Text.of`, tooltips, información de JEI/REI/EMI, los mensajes armados por partes antes de un `tell`, y el texto de `tellraw`, `title` y `say` en `runCommand` | En su sitio, con copia de seguridad |
| Datapacks y tips | Funciones (`.mcfunction`: `tellraw`, `title`, `say`), títulos y descripciones de logros, y consejos de pantalla de carga (mod Tips). Se buscan por su estructura (`data/<espacio>/functions/…`), estén en `kubejs/data`, `global_packs`, `datapacks`, `config/openloader` o en los datapacks de un mundo, sueltos o dentro de un `.zip`. Los componentes de texto valen en JSON (hasta 1.21.4) y en SNBT (desde 1.21.5) | En su sitio, con copia de seguridad |
| Texto escrito en el código de los mods | Mensajes de chat, de la barra de acción, tooltips y texto de botones que un mod tiene en su código Java. Un resource pack no los alcanza: la app los traduce a una tabla que lee el mod de apoyo **ModpackES Runtime** (solo cliente, Forge 1.12.2, 1.16.5, 1.17.1, 1.18.2, 1.19.2 y 1.20.1, NeoForge 1.20.1, de 1.21 a 1.21.11 y de 26.1 a 26.3, y Fabric 1.19.4, de 1.20 a 1.20.6, de 1.21 a 1.21.11 y de 26.1 a 26.3) | Tabla en el resource pack; el mod se instala solo si lo pides |

Lo que el mod ya trae en español no se toca, y si existe una variante (por ejemplo `es_es`) se copia a las
demás sin gastar. Los libros antiguos de Patchouli que guardan el texto dentro del jar no se pueden traducir
sin modificar el mod: la app avisa cuáles son.

El español elegido (Latinoamérica por defecto) va a todos los archivos de español del juego. Con **«Traducir también
una versión aparte para España»** (`--tambien-es-es`), `es_es` recibe su propia traducción, con los nombres del juego
en España («Roca», «objeto»…). Cuesta otra traducción la primera vez; después sale de la memoria. Solo se hace con lo
que tiene un archivo por idioma (mods, libros y la carpeta `lang/` de FTB Quests). Los scripts y las misiones escritas
dentro de los capítulos tienen un solo idioma y quedan con el español elegido.

## Cómo se usa

1. Descarga e instala
   [`ModpackES-instalador.exe`](https://github.com/Consterna/ModpackES/releases/latest/download/ModpackES-instalador.exe):
   se instala solo para tu usuario, sin pedir permisos de administrador, y arranca más rápido. Si prefieres no
   instalar nada, usa la versión portable
   [`ModpackES.exe`](https://github.com/Consterna/ModpackES/releases/latest/download/ModpackES.exe).
2. Cierra Minecraft y abre ModpackES.
3. Elige la instancia en la barra de la izquierda: cada tarjeta muestra la versión de Minecraft, el loader y
   si ya está traducida. Salen las de Prism Launcher, MultiMC, CurseForge, Modrinth, ATLauncher, GDLauncher y
   el launcher oficial; si no aparece, arrastra su carpeta a la ventana o usa «Elegir carpeta…».
4. Elige el motor con la ficha de arriba a la derecha (ver [Motores](#motores)). Con Gemini, pulsa «Guardar
   clave…» y pega tu clave de [aistudio.google.com/apikey](https://aistudio.google.com/apikey); se guarda en
   el Administrador de credenciales de Windows, nunca en un archivo. Con LM Studio u Ollama no hace falta
   clave: enciende su servidor y pulsa «Probar conexión» para elegir el modelo.
5. Pulsa **Analizar (gratis)**. Las tarjetas de mods, libros, misiones y scripts muestran cuántos textos
   faltan, y el botón, cuánto costaría. Desmarca lo que no quieras traducir.
6. Pulsa **Traducir**. Al terminar activa el pack y pone el juego en español (se puede cambiar en «Opciones
   avanzadas»).

Si se corta o lo cancelas, analiza de nuevo y vuelve a traducir: sigue donde quedó. Los pasos de arriba
(Motor, Analizar, Traducir, Listo) dicen en cuál estás, y Ctrl+Enter pulsa el botón principal.

El engranaje de arriba cambia el tema (como Windows, oscuro o claro) y el aviso de versiones nuevas.

El campo **Ambientación** (opcional) le cuenta al motor de qué va el modpack: «granja acogedora, tono
amable; “Bells” es la moneda del pueblo». Ayuda con el tono y con los términos propios del pack, y se guarda
por instancia.

**Revisión automática** (opcional, en «Opciones avanzadas», solo misiones y libros): después de traducir, otro
pedido al motor juzga cada traducción nueva al estilo de [GEMBA-MQM](https://aclanthology.org/2023.wmt-1.64)
(exactitud, terminología, fluidez y estilo, con gravedad leve, grave o crítica) y las graves se vuelven a
traducir indicando el error. La nueva traducción tiene que pasar las mismas reglas; si no, queda la anterior.
Tus correcciones nunca se revisan. Sube el costo de esos textos (el análisis lo incluye) y sus marcas no son
infalibles: sirven para decidir qué rehacer, no como nota de calidad.

**Texto del código de los mods** (opcional): activa «Incluir texto escrito en el código de los mods» en «Opciones avanzadas» y pulsa **Más ▸ Instalar el mod de apoyo**. La app traduce las frases que encuentra en el código de los mods y el mod de apoyo las muestra en español en el chat, la barra de acción y los tooltips. Solo cambia un texto si es **idéntico** al de la tabla (no hay traducción en vivo ni en internet), reconoce frases con datos escritos con `%s` o `%d` como plantillas, cambia también el texto de los botones de una pantalla al abrirla y, en Forge y NeoForge, los tooltips que no son de objetos; el texto que una pantalla dibuja directamente no se puede cambiar sin Mixin y no se toca; por ahora existe para Forge 1.12.2, 1.16.5, 1.17.1, 1.18.2, 1.19.2 y 1.20.1, NeoForge 1.20.1, de 1.21 a 1.21.11 y de 26.1 a 26.3, y Fabric 1.19.4, de 1.20 a 1.20.6, de 1.21 a 1.21.11 y de 26.1 a 26.3. Quilt usa los mods de Fabric con Quilted Fabric API (hasta 1.21.1) y no se ha probado en Quilt. Para Fabric 1.16.5, 1.18.2 y 1.19.2 no puede existir: Fabric API no tiene un evento de chat del cliente en esas versiones, y la app lo dice. **Más ▸ Quitar el mod de apoyo** lo retira de la carpeta mods; en la línea de comandos: `modpackes instalar-runtime RUTA [--quitar]` y `--java` en `analizar` y `traducir`. Para comprobarlo en el juego, con el mod instalado y el juego en español, escribe `/tellraw @s "TPA request expired!"` (o cualquier frase de la tabla).

**Modo exhaustivo de scripts** (opcional, en «Opciones avanzadas» o con `--exhaustivo`): traduce también las frases de los scripts de KubeJS cuyo uso no se entiende (por ejemplo textos que pasan por una función propia del pack). Puede tocar lógica del script, por eso viene apagado; todo queda con copia de seguridad y se restaura con «Restaurar el original».

**Más ▸ Qué queda en inglés** (o `modpackes cobertura RUTA [--java]`) lista lo que no se traduce y por qué, sin cambiar nada: frases de scripts cuyo uso no se entiende, frases dentro de comandos de otros mods (p. ej. `emberstextapi queue`), cuyo formato la app no conoce y por eso no toca, y texto escrito en el código de los mods, que un resource pack no puede alcanzar. El análisis ya avisa de las frases de scripts.

**Qué cambió desde la última traducción:** cuando sale una versión nueva del modpack, vuelve a pulsar «Analizar». Debajo del costo verás una línea como «Desde la última traducción (2026-11-12): 40 nuevas, 3 cambiadas, 5 borradas.». El detalle, por mod y por archivo de misiones, libro o script, sale con `modpackes cambios RUTA`, que no escribe nada. Ahí ves las claves nuevas, las que cambiaron y las borradas, y lo que costaría traducir solo esa diferencia. Para aplicarla basta con «Traducir»: lo que ya está en la memoria no se vuelve a pagar. Para comparar, cada traducción guarda en la marca del pack (`resourcepacks/Traduccion_ES/traductor_es.json`) un hash corto de cada texto en inglés, nunca el texto. Si el pack se tradujo con una versión anterior de la app y no tiene ese índice, se cuenta como nuevo lo que no está en la memoria.

**Más ▸ Restaurar el original** devuelve misiones, scripts y libros propios al texto del modpack. Para quitar
la traducción de los mods basta con desactivar el resource pack.

**Más ▸ Correcciones…** busca cualquier texto en la memoria (en inglés o en español) y te deja corregir su
traducción a mano. La corrección manda sobre todo lo demás, vale para todas las misiones, libros y mods donde
aparezca ese texto y se aplica la próxima vez que traduzcas, sin costo. Si a la corrección le falta un código
del original (`%s`, `§a`, `$(l)`…), no se guarda, para que no rompa el juego.

> [!NOTE]
> El ejecutable no tiene firma digital, así que la primera vez Windows SmartScreen puede avisar. Pulsa
> «Más información» → «Ejecutar de todas formas». Puedes comprobar el archivo con el SHA-256 que viene en la
> página de cada versión, o con `gh attestation verify ModpackES-instalador.exe -R Consterna/ModpackES` (o
> `ModpackES.exe`), que confirma que lo construyó este repositorio en GitHub Actions.

## Motores

| Motor | Clave | Costo | Notas |
|---|---|---|---|
| **Gemini** (por defecto) | Sí, de Google AI Studio | El que estima «Analizar»; la mitad con «Más barato, pero tarda más» | El más probado: con él se tradujo Farming Crossing 4 |
| **OpenRouter** | Sí | Según el modelo que elijas | Da acceso a muchos modelos con una sola cuenta |
| **DeepSeek** | Sí | Según su lista de precios | Responde en JSON simple; el validador revisa cada texto igual |
| **LM Studio** / **Ollama** | No | Gratis | El modelo corre en tu PC, sin internet. La calidad depende del modelo y del equipo |
| **Otro compatible con OpenAI** | Opcional | Según el servidor | Cualquier servidor con `/v1/chat/completions` |

Todos los motores reciben las mismas instrucciones y pasan por las mismas reglas de calidad: lo que pierde un
código o vuelve en inglés se descarta. Con modelos locales pequeños (menos de unos 7 000 millones de
parámetros) es más probable que fallen el formato JSON y que queden más textos en inglés; LM Studio advierte
lo mismo en su documentación.

## Costo

Con `gemini-3.8-flash` un modpack grande (unos 800 000 caracteres por traducir) cuesta alrededor de **1,5 a 2
dólares**, y la mitad con la opción «Más barato, pero tarda más» (Batch API), que puede tardar desde minutos
hasta horas. Un modpack pequeño cuesta centavos. Son estimaciones con los precios de Google de noviembre de
2026; el botón «Analizar» calcula el de tu modpack antes de gastar nada.

La capa gratuita de Gemini sirve para probar, pero tiene límites de peticiones por minuto y por día que un
modpack grande supera enseguida. Con la facturación activada (nivel 1) se traduce de una vez.

## Multijugador

Las misiones y los scripts de servidor los lee el servidor. «Más ▸ Kit de servidor…» arma un `.zip` con esos
archivos ya traducidos, el resource pack para los jugadores y las instrucciones. «Exportar pack…» saca solo el
resource pack, listo para publicar: con `pack.png`, un `LEEME.txt` (aviso de traducción automática, si una persona
la revisó, motores usados y créditos), la versión del modpack en el nombre del archivo y `supported_formats` en el
`pack.mcmeta` cuando la versión lo usa (de 1.20.2 a 1.21.8).

## Compartir una traducción

Una persona traduce y paga; las demás la aplican gratis.

- **«Más ▸ Exportar paquete de traducción…»** guarda un `.modpackes.zip` con la parte de tu memoria que usa ese
  modpack, tus correcciones de esos textos, tu glosario y los datos del pack (nombre, versión, Minecraft, dialecto,
  modelos y si se revisó). No lleva nada de los mods ni del modpack.
- **«Más ▸ Importar traducción…»** aplica un `.modpackes.zip` sin llamar a ningún motor: lo guarda en tu memoria y
  escribe la traducción. Tus correcciones y tus términos del glosario no se pisan. Si el paquete es de otra versión
  del modpack, avisa: lo que cambió queda en inglés hasta que lo traduzcas.
- También importa un **resource pack en español** (`.zip` o carpeta), aunque no esté activo en el juego: sus textos se
  emparejan con el inglés de tus mods y pasan a la memoria del mismo modo.

El nombre y la versión del modpack se leen de BetterCompatibilityChecker (`config/bcc-common.json`, `bcc.json` o
`bcc-common.toml`), de Prism, de CurseForge o de `modrinth.index.json`; si no hay nada, se usa el nombre de la carpeta.

## Preguntas frecuentes

<details>
<summary><b>¿Puede romper mi modpack?</b></summary>

Cada archivo que se cambia se guarda antes en `traductor_es/respaldo` dentro de la instancia, y «Más ▸
Restaurar el original» los devuelve. Los archivos se reescriben sin pérdidas (solo cambian los textos
traducidos) y las pruebas validan el resultado con los parsers reales del juego (Gson y el SNBT de FTB
Library).
</details>

<details>
<summary><b>¿Qué pasa cuando el modpack se actualiza?</b></summary>

Analiza y traduce de nuevo. Lo que ya estaba traducido sale de la memoria sin costo y solo se paga lo nuevo.
</details>

<details>
<summary><b>¿Qué se envía y a quién?</b></summary>

Solo los textos que hay que traducir, con los códigos cambiados por marcadores, la clave del mod como
contexto y la ambientación si la escribiste. Van únicamente al motor que elijas; con LM Studio u Ollama no
salen de tu PC. No se envía nada más. Al abrirse, la app consulta en GitHub si hay una versión nueva (sin
enviar datos tuyos); se desactiva en el engranaje, con «Avisar al abrir si hay una versión nueva».

Ten en cuenta que, según las condiciones de Google, los datos de la capa gratuita de Gemini pueden usarse para
mejorar sus productos; revisa las condiciones del proveedor que uses.
</details>

<details>
<summary><b>¿Por qué un texto quedó en inglés?</b></summary>

Porque la traducción no pasó las reglas de calidad (perdía un código, cambiaba el sentido de un comando o
seguía en inglés) después de los reintentos. Es preferible a meter un texto que rompa el juego. Puedes volver
a traducir más tarde: solo se reintenta lo pendiente.
</details>

<details>
<summary><b>¿Funciona en Linux o macOS?</b></summary>

El `.exe` es para Windows. El código es Python y casi todo es multiplataforma, pero la detección de
lanzadores y el guardado de la clave solo se probaron en Windows.
</details>

## Línea de comandos

Desde el código fuente (ver [Desarrollo](#desarrollo)):

```
uv run modpackes instancias
uv run modpackes analizar "RUTA DE LA INSTANCIA"
uv run modpackes cambios "RUTA" [--json]   # qué cambió desde la última traducción y cuánto cuesta (solo lee)
uv run modpackes traducir "RUTA" [--dialecto es_es | --tambien-es-es] [--solo misiones,libros] [--lotes] [--modelo gemini-3.5-flash-lite] [--contexto "granja acogedora"] [--revisar]
uv run modpackes restaurar "RUTA"
uv run modpackes cobertura "RUTA" [--java]   # qué queda en inglés y por qué (solo lee)
uv run modpackes glosario listar | agregar "Death Knights" "Caballeros de la Muerte" | quitar "Fluix" | importar terminos.json
uv run modpackes exportar "RUTA" [ARCHIVO.zip] [--revisado] [--kit]   # pack listo para publicar (o kit de servidor)
uv run modpackes paquete exportar "RUTA" [ARCHIVO.modpackes.zip] [--revisado] [--dialecto es_es]
uv run modpackes paquete importar "RUTA" ARCHIVO.modpackes.zip|PACK.zip|CARPETA [--no-activar]   # sin API
uv run modpackes clave guardar [--motor openrouter]
uv run modpackes modelos [--motor ollama]
```

Con otro motor: `--motor openrouter|deepseek|lmstudio|ollama|personalizado`, `--modelo NOMBRE` y, para el
personalizado, `--direccion http://servidor/v1`. La clave también se puede pasar por variable de entorno:
`GEMINI_API_KEY` o `MODPACKES_CLAVE_<MOTOR>` (por ejemplo `MODPACKES_CLAVE_OPENROUTER`).

El **glosario del usuario** (`glosario`) son los términos que quieres que se traduzcan siempre igual, también los nombres
que no se traducen (`"Fluix": "Fluix"`). Mandan sobre todo lo demás y, si una traducción no los usa, el texto se reintenta
con un aviso. Se guardan en `glosario.json` de la carpeta de datos de la app y valen para todos tus modpacks.

`traducir --simular` hace una prueba completa sin la API (antepone «ES» a cada texto); úsalo en una copia. No
guarda nada en la memoria de traducciones, para que la próxima traducción de verdad no reutilice esos textos.

## Cómo protege el modpack

- Los códigos de formato (`%s`, `§a`, `&c`, `$(l)`, `{image:…}`, `${…}`, comandos, ids, enlaces) se cambian
  por marcadores antes de enviar el texto. Una traducción que pierde o inventa un marcador se descarta.
- Cada traducción pasa reglas de calidad: no puede estar vacía, seguir en inglés, tener un largo raro o meter
  saltos de línea nuevos. Lo que no pasa se reintenta y, si sigue mal, queda en inglés.
- Los archivos se reescriben sin pérdidas: solo cambian los textos traducidos y todo lo demás queda byte a byte
  igual.
- Un glosario con los nombres oficiales de Minecraft y de los mods mantiene los mismos términos en misiones,
  libros y scripts. Los términos que se repiten en los nombres de un modpack se traducen primero y se fijan, y
  el motor recibe de cada texto de dónde sale.
- Controles que no dependen del modelo: los nombres propios del glosario conservan sus mayúsculas («el Anillo
  Cuántico»), los nombres que no se traducen («Creeper», el nombre de un jefe) se protegen y un nombre que repite
  una palabra («Mejora de Salud mejorada») se reintenta. En el reintento se pide corregir solo lo que falló.
- Con un banco de 148 textos de referencia, Gemini 3.8 Flash tradujo el 100 % con un chrF de 85 y respetó
  todos los términos del glosario: detalle y límites de la medición en [docs/calidad.md](docs/calidad.md).

## Desarrollo

Requisitos: [uv](https://docs.astral.sh/uv/) (instala Python 3.13 solo) y, para las pruebas con los parsers
del juego, un JDK 17 o superior (sirve el de Prism Launcher).

```
uv sync
uv run python scripts/verificar.py            # ruff, pyright estricto, compileall y pytest con cobertura
uv run python scripts/verificar.py --rapido   # sin las pruebas de Java ni el corpus real
uv run python scripts/construir_exe.py        # dist/ModpackES.exe (portable)
uv run python scripts/construir_exe.py --instalador  # dist/ModpackES-instalador.exe (necesita Inno Setup 6.3+)
uv run python scripts/probar_exe.py           # arranca el .exe y analiza un modpack de prueba
uv run python scripts/probar_exe.py --instalador  # instala en una carpeta temporal, prueba y desinstala
```

Los datos de la app (memoria, glosario, preferencias y `registro.log`) van a `%LOCALAPPDATA%\traductor-es`;
la variable `TRADUCTOR_ES_DATOS` los lleva a otra carpeta. Las pruebas con Java buscan Gson en las bibliotecas
de Prism Launcher o usan el jar que indique `TRADUCTOR_ES_GSON` (así corren en el CI). Lee
[CONTRIBUTING.md](CONTRIBUTING.md) y el [código de conducta](CODE_OF_CONDUCT.md) antes de mandar cambios.

## Créditos

Ideas tomadas de [MinecraftModsLocalizer](https://github.com/Y-RyuZU/MinecraftModsLocalizer) (MIT),
[MineAI Modpack Translator](https://github.com/Thedrezik/MineAI-Modpack-Translator) (MIT),
[mc-questing-mod-localizer](https://github.com/peunsu/mc-questing-mod-localizer) (MIT),
[mc_translator](https://github.com/chrysoljq/mc_translator) (GPL-3.0, la ambientación del modpack) y
[AutoTranslation](https://github.com/yuefdev/minecraft-ai-translator) (AGPL, solo ideas: correcciones del
usuario y modelos locales). La revisión automática sigue el método GEMBA-MQM (Kocmi y Federmann, WMT 2023).
No se copió código de ninguno. Los formatos de cada mod se comprobaron en su código fuente (FTB Quests, BetterQuesting, HQM,
Heracles, Patchouli, Mantle, GuideME, Lavender). Las bibliotecas que usa la app están en
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Licencia

© 2026 Cristian. ModpackES es software libre bajo la [GNU General Public License v3.0 o posterior](LICENSE):
puedes usarlo, estudiarlo, modificarlo y compartirlo, siempre que las versiones que distribuyas sigan siendo
libres, con su código fuente y esta misma licencia.

ModpackES no está afiliado a Mojang Studios, Microsoft ni Google. Minecraft es una marca de Mojang Studios.

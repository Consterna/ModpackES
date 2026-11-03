# ModpackES

Traduce modpacks de Minecraft al español con la API de Gemini: **misiones, libros guía, scripts de KubeJS y
textos de los mods**. Funciona con cualquier versión (de 1.7.10 a 26.x) y cualquier loader (Forge, NeoForge,
Fabric, Quilt), y escribe las siete variantes de español del juego a la vez.

No modifica los jars de los mods. Todo lo que cambia dentro de la instancia tiene copia de seguridad y se
puede restaurar al original con un botón.

## Qué traduce

| Contenido | Formatos | Dónde queda |
|---|---|---|
| Textos de mods (objetos, bloques, menús, tooltips) | `lang/*.json` (1.13+) y `.lang` (1.12 y antes), incluidos los jars anidados, KubeJS y los resource packs del modpack | Resource pack `Traduccion_ES` |
| Misiones | FTB Quests (texto en los capítulos, carpeta `lang/` de 1.21+ y NBT de 1.12), BetterQuesting, HQM, Heracles | En su sitio, con copia de seguridad |
| Libros guía | Patchouli, Mantle (Tinkers), Citadel (Alex's Mobs), GuideME (AE2), Lavender. Modonomicon va por claves de idioma | Resource pack (o en su sitio, si es un libro propio del modpack) |
| Scripts de KubeJS | Lo que ve el jugador: `tell`, `displayName`, `Text.of`, tooltips, información de JEI/REI/EMI | En su sitio, con copia de seguridad |

Lo que el mod ya trae en español no se toca, y si existe una variante (por ejemplo `es_es`) se copia a las
demás sin gastar. Los libros antiguos de Patchouli que guardan el texto dentro del jar no se pueden traducir
sin modificar el mod: la app avisa cuáles son.

## Cómo se usa

1. Cierra Minecraft.
2. Abre `TraductorModpacks.exe`.
3. Elige la instancia de la lista. Salen las de Prism Launcher, MultiMC, CurseForge, Modrinth, ATLauncher y
   el launcher oficial; si no aparece, usa «Elegir carpeta…».
4. Pulsa «Guardar clave…» y pega tu clave de [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
   Se guarda en el Administrador de credenciales de Windows, nunca en un archivo.
5. Pulsa **1. Analizar (gratis)**: cuenta lo que falta y estima el costo.
6. Pulsa **2. Traducir**. Al terminar activa el pack y pone el juego en español (se puede desmarcar).

Si se corta o lo cancelas, vuelve a pulsar «Traducir»: lo ya traducido queda en la memoria y no se paga
dos veces, tampoco en otros modpacks que compartan mods.

**Restaurar original** devuelve misiones, scripts y libros propios al texto del modpack. Para quitar la
traducción de los mods basta con desactivar el resource pack.

## Costo

Con `gemini-3.8-flash` un modpack grande (unos 800 000 caracteres por traducir) cuesta alrededor de
**1,5 a 2 dólares**, y la mitad con la opción «Por lotes» (Batch API), que puede tardar desde minutos hasta
horas. Son estimaciones con los precios de Google de noviembre de 2026.

## Multijugador

Las misiones y los scripts de servidor los lee el servidor. «Kit de servidor…» arma un `.zip` con esos
archivos ya traducidos, el resource pack para los jugadores y las instrucciones.

## Línea de comandos

```
uv run modpackes instancias
uv run modpackes analizar "RUTA DE LA INSTANCIA"
uv run modpackes traducir "RUTA" [--dialecto es_es] [--solo misiones,libros] [--lotes] [--modelo gemini-3.5-flash-lite]
uv run modpackes restaurar "RUTA"
uv run modpackes clave guardar
uv run modpackes modelos
```

`traducir --simular` hace una prueba completa sin la API (antepone «ES» a cada texto); úsalo en una copia.

## Cómo protege el modpack

- Los códigos de formato (`%s`, `§a`, `&c`, `$(l)`, `{image:…}`, `${…}`, comandos, ids, enlaces) se cambian
  por marcadores antes de enviar el texto. Una traducción que pierde o inventa un marcador se descarta.
- Cada traducción pasa reglas de calidad: no puede estar vacía, seguir en inglés, tener un largo raro o meter
  saltos de línea nuevos. Lo que no pasa se reintenta y, si sigue mal, queda en inglés.
- Los archivos se reescriben sin pérdidas: solo cambian los textos traducidos y todo lo demás queda byte a byte
  igual. Los SNBT generados se validan con el parser real de FTB Library y los JSON con Gson en las pruebas.
- Un glosario con los nombres oficiales de Minecraft y de los mods mantiene los mismos términos en misiones,
  libros y scripts.

## Desarrollo

Requisitos: [uv](https://docs.astral.sh/uv/) (instala Python 3.13 solo) y, para las pruebas con los parsers
del juego, un JDK 17 o superior (sirve el de Prism Launcher).

```
uv sync
uv run python scripts/verificar.py            # ruff, pyright estricto, compileall y pytest con cobertura
uv run python scripts/verificar.py --rapido   # sin las pruebas de Java ni el corpus real
uv run python scripts/construir_exe.py        # dist/TraductorModpacks.exe
```

Las pruebas del corpus usan las instancias del PC en solo lectura y copias en carpetas temporales. Los datos
de la app (memoria, glosario, preferencias) van a `%LOCALAPPDATA%\traductor-es`; la variable
`TRADUCTOR_ES_DATOS` los lleva a otra carpeta.

## Créditos

Ideas tomadas de [MinecraftModsLocalizer](https://github.com/Y-RyuZU/MinecraftModsLocalizer) (MIT),
[MineAI Modpack Translator](https://github.com/Thedrezik/MineAI-Modpack-Translator) (MIT),
[mc-questing-mod-localizer](https://github.com/peunsu/mc-questing-mod-localizer) (MIT) y
[AutoTranslation](https://github.com/yuefdev/minecraft-ai-translator) (AGPL, solo ideas). Los formatos de cada
mod se comprobaron en su código fuente (FTB Quests, BetterQuesting, HQM, Heracles, Patchouli, Mantle,
GuideME, Lavender).

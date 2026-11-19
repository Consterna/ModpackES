# ModpackES Sonda

Mod de desarrollo que mide dentro del juego qué texto ve el jugador y si sigue en inglés. No cambia nada de lo que se
ve: solo escribe JSON. No va en el instalador ni lo instala `modpackes instalar-runtime`. Es solo cliente.

| Proyecto | Loader | Minecraft |
|---|---|---|
| `forge-1.20.1` | Forge 47 | 1.20.1 |
| `neoforge-1.21.1` | NeoForge 21.1 | 1.21.1 |
| `fabric-1.20.1` | Fabric (con Fabric API) | 1.20.1 |

## Compilar

```powershell
uv run python scripts/construir_mod.py sonda
```

`sonda` compila los tres con sus pruebas; `sonda/forge-1.20.1` (u otro) compila uno. Los jars quedan en `build/sonda/`.
`construir_mod.py` sin argumentos (lo que corre el CI) no los compila.

## Usar

1. Copia el jar a `mods/` de la instancia, junto al resto del modpack.
2. Abre el juego en el idioma que quieras medir (p. ej. `es_es`).
3. Juega o recorre las pantallas: todo lo que se dibuja queda anotado.
4. Dentro de un mundo, escribe `/modpackes_sonda volcar` para volcar los nombres de lo registrado.

## Qué escribe

Todo va a `<carpeta del juego>/modpackes-sonda/`. Cada JSON empieza con `formato`, `loader`, `minecraft` e `idioma`.

- **`idioma.json`**: se reescribe tras cada recarga de recursos (al arrancar, con F3+T y al cambiar de idioma).
  Trae cada clave del idioma cargado con su `valor`, su valor `en_us` y `igual` (si los dos son el mismo texto, es
  decir, si se ve en inglés). Incluye las claves que los mods crean mientras el juego corre (KubeJS, ARRP/BRRP,
  Moonlight), porque se copia el mapa que el juego tiene cargado.
- **`textos-dibujados.json`**: cada texto que pasa por la fuente del juego (`Font.drawInternal` y
  `Font.drawInBatch8xOutline`; ahí acaban `GuiGraphics.drawString` y todos los `Font.drawInBatch`), sin repetir y con
  la clase de la pantalla abierta, o `(sin pantalla)` en el HUD y el mundo. Se escribe cada 5 segundos si hay algo
  nuevo, y al cerrar. Guarda hasta 100 000 pares «texto + pantalla»; los que no caben se cuentan en
  `descartados_por_tope`.
- **`registros.json`**: lo escribe `/modpackes_sonda volcar`. Trae cada objeto (nombre y tooltip sin modo avanzado),
  bloque, entidad, efecto, encantamiento y bioma, más los atajos de teclado y sus categorías: `categoria`, `id`,
  `clave` de traducción, `valor` que se ve, `existe` (si el idioma tiene la clave), `en_us` e `igual`.

## Límites

- En Fabric fuera del entorno de desarrollo, las pantallas del juego base salen con su nombre intermedio
  (`net.minecraft.class_…`); las de los mods salen con su nombre.
- Un mod que reemplaza la fuente del juego (p. ej. otro motor de texto) puede impedir que se anote lo dibujado; si el
  mixin no aplica, el juego no arranca y el registro lo dice.
- El texto dibujado sale tal cual, con los códigos `§` si los trae. Los números que cambian (coordenadas de F3,
  contadores) generan muchas entradas: por eso el tope.

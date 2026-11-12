# Calidad medida

Resultados de `scripts/medir_calidad.py` con el banco de referencia (`tests/datos/referencia_es.json`: 148
textos escritos para el proyecto, 40 de interfaz, 48 de misiones, 35 de libros y 25 de scripts, con un
glosario de 20 términos). Las referencias son una traducción posible al español latinoamericano, no la única.

## 3 de noviembre de 2026 · Gemini 3.8 Flash

| | Sin revisión | Con revisión |
|---|---|---|
| Textos que pasaron las reglas | 148 de 148 | 148 de 148 |
| chrF promedio | 85,1 | 85,1 |
| chrF interfaz / misiones / libros / scripts | 86,4 / 84,3 / 85,6 / 83,5 | igual |
| Términos del glosario respetados | 24 de 24 | 24 de 24 |
| Costo estimado | US$ 0,011 | US$ 0,018 |
| Tiempo | 35 s | 57 s |

La revisión automática juzgó 83 textos (misiones y libros) y no encontró errores graves, así que no cambió
nada. **Con este modelo y este banco no se midió una mejora**; puede servir más con modelos más débiles o
textos más difíciles, pero eso no está medido.

Los textos más lejanos de la referencia eran alternativas válidas, no errores: «Configuración» por «Ajustes»,
«Pay de arándanos» por «Pay de mora azul», «Piscina de maná» por «Estanque de maná». Es el límite conocido
de chrF: compara con una sola referencia.

## 9 de noviembre de 2026 · textos reales de mods

Segundo banco, de 250 textos de interfaz (150 frases y 100 nombres) tomados de mods de licencia libre que ya
traen su traducción al español, de 1.7.10 a 1.21. Cada mod lo tradujo una persona distinta, así que hay mucha
más variedad que en el banco anterior. Las referencias y los textos no se publican (ver
[datos-de-terceros.md](datos-de-terceros.md)): el banco se arma en tu PC con `scripts/armar_banco_local.py`.

| | Gemini 3.8 Flash | Gemma 4 E2B local (Q4, 3,3 GB) |
|---|---|---|
| Textos que pasaron las reglas | 250 de 250 | 189 de 250 (76 %) |
| chrF promedio | 71,6 | 66,5 |
| Tiempo | 13 s | 712 s |
| Costo estimado | US$ 0,024 | 0 |

Con textos reales el chrF baja respecto al banco escrito a mano (85,1) porque cada mod usa sus propias
palabras («Criaturas» o «Mobs», «Elegantes» o «Detallados»). El modelo local pequeño dejó sin traducir
algunos nombres propios del mod y 61 textos no pasaron las reglas de calidad, que en la app se reintentan o
quedan en inglés. Es útil para traducir sin conexión ni costo, pero con menos calidad y bastante más lento
que Gemini. Se midió en una RTX 4050 con 6 GB, usando unos 2 GB de RAM; el modelo no se incluye en el
instalador.

## 11 de noviembre de 2026 · contexto, ejemplos y términos fijos

Mismos textos reales de mods (250 de interfaz), medidos con Gemini 3.8 Flash, con y sin las mejoras de precisión:
cada texto va con su clave y su tipo, el motor recibe ejemplos de textos parecidos ya traducidos, los términos que
se repiten en los nombres se traducen primero y los nombres devueltos sin traducir se reintentan. Para que la
comparación sea justa, la mitad de los mods se mide y los ejemplos salen solo de la otra mitad.

| chrF | Corrida 1 | Corrida 2 | Corrida 3 | Promedio |
|---|---|---|---|---|
| Sin pistas ni ejemplos (`--sin-contexto`) | 69,2 | 69,0 | 68,4 | 68,9 |
| Con pistas y ejemplos | 70,3 | 70,5 | 71,1 | 70,6 |

La mejora es de unos 1,7 puntos y se repitió en las tres corridas, pero es pequeña frente a la variación entre
corridas (hasta 0,8). Lo que más se espera de las pistas y los ejemplos es consistencia de términos dentro de un
modpack, que chrF mide mal porque compara con una sola referencia. No se midió con modelos locales.

## 12 de noviembre de 2026 · medir con intervalos y comparar de forma pareada

`medir_calidad.py` ahora da el intervalo de confianza al 95 % del chrF, una medida heurística de consistencia de
términos y guarda todas las traducciones; `comparar_mediciones.py` compara dos grupos de corridas con un bootstrap
pareado sobre los mismos textos, y `juzgar_calidad.py` hace pasar las traducciones por un juez (estilo GEMBA-MQM)
en dos órdenes de lectura. El banco local ahora agrega «familias» de nombres que comparten un término (399 textos).

| Banco | Base (3 corridas) | Con contexto y ejemplos (3 corridas) | Diferencia (IC 95 %) |
|---|---|---|---|
| 248 textos sueltos | 69,3 | 70,7 | +1,38 (+0,46 a +2,31): mejora |
| 394 textos, con familias de nombres | 70,5 | 70,6 | +0,18 (−0,90 a +1,26): no se distingue del ruido |

- Con el banco anterior la mejora del contexto y los ejemplos se confirma; con las familias de nombres no se ve. Una
  lectura honesta es que la mejora existe pero es pequeña y depende de los textos; no hay que prometer más de ~1 punto.
- La consistencia de términos dio 0,90 con y sin las mejoras (30 términos): Gemini ya era consistente en este banco o
  la heurística no es lo bastante sensible. Hay que probarla con modelos locales, donde se espera más variación.
- El juez (mismo modelo que tradujo, así que con sesgo) marcó entre 1,5 y 3 errores graves por cada 100 textos, casi
  todos de terminología, pero solo coincidió en el 12 % entre los dos órdenes de lectura: con una sola pasada no es
  una métrica confiable. Antes de usarlo para decidir hace falta repetirlo varias veces y votar, o usar otro modelo.

## 12 de noviembre de 2026 · glosario estricto

Si un término del glosario sale en el original y su traducción no sale en el resultado (se toleran plurales, tildes
y mayúsculas), el texto se reintenta con un aviso explícito («Usa exactamente estos términos: …»). Si tras el
reintento sigue sin salir, se acepta. `medir_calidad.py --glosario-laxo` mide sin esta regla. Banco de 399 textos y un
glosario de 2.101 términos sacado de otros mods, Gemini 3.8 Flash, tres corridas:

| | Términos respetados (corridas 1 a 3) | chrF |
|---|---|---|
| Laxo | 29, 32 y 33 de 37 | 70,9 |
| Estricto | 32, 32 y 33 de 37 | 70,9 (diferencia +0,06, IC −0,41 a +0,51) |

El efecto es pequeño: Gemini ya respeta casi todos los términos y la regla recupera uno o dos más sin tocar el chrF.
Se queda como red de seguridad, que importará más con modelos locales y con glosarios del usuario.

## 12 de noviembre de 2026 · revisión humana de 100 textos y una comparación a ciegas

Una persona revisó 100 traducciones de Gemini 3.8 Flash (60 de interfaz de mods y 40 de misiones) con `scripts/hoja_revision.py`:
**79 Bien, 20 Leve y 1 Grave**. Sin error grave: 99 %. Aceptable tal cual: 79 % (intervalo de Wilson ≈ 70–86 %). Interfaz: 47 Bien, 12 Leve,
1 Grave. Misiones: 32 Bien, 8 Leve, 0 Grave. Los Leve se repiten: mayúsculas de términos propios («Caballeros de la Muerte»),
«objetos» en vez de «ítems», «netherita» en vez de «inframundita», nombres propios que no se traducen, palabras duplicadas y
preferencia por una traducción más literal. El único Grave fue un identificador técnico dejado en inglés.

Con eso se probó un prompt con cuatro reglas nuevas (fidelidad literal, mayúsculas de términos propios, vocabulario, nombres propios
intactos). Cambió 57 de 99 textos y la misma persona los comparó **a ciegas** (A/B sin saber cuál era la nueva):
**20 prefirió la nueva, 32 la anterior y 5 igual** (prueba de signos p = 0,13). Arregló varios de los casos señalados («netherita»,
«Fluix», «Caballeros de la Muerte», «Mejora de Salud»), pero estropeó otros (dejó «Starlit Crusher» sin traducir, escribió «Mejora»
con mayúscula en frases donde no tocaba). **No se adoptó.**

Hay un motivo que impide sacar conclusiones fuertes: con Gemini 3.8 Flash dos corridas con el mismo prompt dan textos idénticos
en solo ~48 de 99 casos, y con temperatura 0 en ~38 de 99, así que la temperatura no estabiliza nada. La mitad de lo que "cambia"
entre dos versiones es variación normal. Para fijar una decisión de estilo (p. ej. «Netherita», «Fluix», «Caballeros de la Muerte»)
sirve más el **glosario del usuario** (`glosario.json`), que sí es determinista y se exige con reintento, que otra regla en el prompt.

## Cómo repetirlo

```
uv run python scripts/medir_calidad.py --revisar
uv run python scripts/medir_calidad.py --motor ollama --modelo NOMBRE --revisar
uv run python scripts/armar_banco_local.py
uv run python scripts/medir_calidad.py --banco .descargas/banco/referencia_real.json
uv run python scripts/medir_calidad.py --banco .descargas/banco/referencia_real.json --sin-contexto
uv run python scripts/comparar_mediciones.py --a build/sin1.json build/sin2.json --b build/con1.json build/con2.json
uv run python scripts/juzgar_calidad.py --entrada build/con1.json
```

El costo es una estimación con los precios de Google de noviembre de 2026, no lo que cobró la API.

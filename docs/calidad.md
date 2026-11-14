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
## 12 de noviembre de 2026 · un juez más fuerte y glosarios que se contradicen

Probé como juez a Gemini 3.1 Pro (distinto y más fuerte que el que tradujo) sobre las traducciones de Gemini 3.8 Flash. Con las
traducciones sin ejemplos y referencias limpias marcó 4,1 y 4,6 errores graves por cada 100 textos (según el orden de lectura),
contra 1,0 y 1,3 del juez Flash: el fuerte ve cuatro veces más. Casi todo es terminología (13 de 16), no cambios de sentido.
Dos eran **críticos y venían del glosario**: «Cow» y «Villager» salían como «Acechador de medianoche», el nombre que un mod
cualquiera le pone a esa criatura, y el glosario estricto lo imponía. Otros graves eran de dialecto («Cristal» en vez de «Vidrio»,
«inframundita» en vez de «Netherita», «Azada» en vez de «Azadón»).

Por eso el glosario ahora no deja que un mod imponga su término (`Glosario.agregar_pares(..., fuente=, oficial=)`): los
nombres del propio juego (es_mx antes que es_es) ganan a los de un mod, y si dos mods traducen distinto el mismo término no
se usa ninguno. `armar_banco_local.py` arma el glosario del banco igual (con los textos de vanilla de Mojang, solo en local).

| Glosario del banco | Términos | Errores graves por cada 100 según el juez (orden normal / inverso) | chrF |
|---|---|---|---|
| Antes (lo primero que aparece) | 2.076 | 9,9 / 12,2 | 71,0 |
| Ahora (juego primero, sin contradicciones) | 5.131 | 6,1 / 11,4 | 70,4 (−0,6, no se distingue del ruido) |

El juez sigue siendo ruidoso (acuerdo entre órdenes del 30–50 %), pero baja en los dos órdenes y desaparecen los casos
críticos del glosario («Cow» sale «Vaca», «Glass» sale «Vidrio»). El chrF no cambia porque las referencias de cada mod siguen
sus propias convenciones. Lo que queda por encima de ~90 % de textos sin error grave es sobre todo terminología y dialecto, y
la forma de cerrarlo es el glosario, no otra vuelta del modelo.
## 12 de noviembre de 2026 · ¿ayudan los ejemplos parecidos? (resultado negativo)

Se probó con el banco de 399 textos (con familias de nombres), Gemini 3.8 Flash y tres corridas por condición, comparando
de forma pareada: sin ejemplos, 8 ejemplos por palabras sueltas, 8 ejemplos con peso extra a las frases de dos palabras
seguidas (bigramas) y 14 ejemplos.

| Comparación | Diferencia de chrF (IC 95 %) |
|---|---|
| 0 ejemplos → 8 por palabras sueltas | −0,64 (−1,68 a +0,51), no se distingue del ruido |
| 8 por palabras → 8 con bigramas | +0,12 (−0,42 a +0,68), no se distingue del ruido |
| 8 → 14 ejemplos | +0,23 (−0,39 a +0,85), no se distingue del ruido |

Con Gemini y este banco los ejemplos no mejoran el chrF, y ajustar cómo se buscan (bigramas) o cuántos se mandan tampoco.
Por eso **no se agregó** la búsqueda con bigramas: sumaría código sin una ganancia medida. Lo que sí queda abierto es
si ayudan con modelos locales pequeños, que cometen más errores de términos y estilo, y si mejoran la consistencia
en packs grandes; se mide cuando se pruebe el modelo local.

## 12 de noviembre de 2026 · modelo local en «carga segura»

Gemma 4 E2B (Q4, 3,3 GB) con `llama.cpp` (Vulkan), 12 capas en la GPU y el resto en RAM, 1 pedido a la vez, lotes de 12
textos o 1.800 caracteres, descansando un 30 % del tiempo (`medir_calidad.py --carga-segura`). Banco de 100 textos reales.

| | Gemma 4 E2B local, carga segura | Gemini 3.8 Flash (2 corridas) |
|---|---|---|
| Textos que pasaron las reglas | 100 de 100 | 100 de 100 |
| chrF | 64,1 (IC 59,7 a 69,2) | 68,9 |
| Términos del glosario | 6 de 8 | 7 de 8 |
| Tiempo | 1.700 s (510 s de descanso) | 13 s |

- Diferencia pareada con Gemini: **+4,8 de chrF a favor de Gemini** (IC +0,2 a +9,4): el modelo local pierde algo, pero
  en este banco no se queda lejos.
- **Uso del PC durante los 28 minutos:** temperatura máxima de la GPU 56 °C, uso máximo 49 % y promedio 21 %, VRAM máxima
  1,1 GB (muestras cada 5 s con `nvidia-smi`). No se acercó al límite de 80 °C que vigila la app.
- La corrida anterior sin carga segura (250 textos, lotes de 60, 4 pedidos a la vez) dejó 189 de 250 textos aceptados
  (76 %) y la GPU al ~78 %. Ahora se aceptaron los 100, pero no es una comparación controlada (otro banco y varios
  cambios a la vez: lotes más chicos, glosario estricto, contexto); no se puede atribuir la mejora a uno solo.
- Costo: tarda unas 130 veces más que Gemini, pero no cuesta nada y no usa internet.

Cómo repetirlo (con el servidor apagado al terminar y el puerto comprobado antes):

```
llama-server -m modelo.gguf --host 127.0.0.1 --port 8089 -c 4096 -ngl 12 -t 4 -np 1 --no-webui
uv run python scripts/medir_calidad.py --motor personalizado --direccion http://127.0.0.1:8089/v1 --modelo gemma-4-e2b --carga-segura --banco .descargas/banco/referencia_100.json
```
## 12 de noviembre de 2026 · referencias limpias: los ejemplos de otros mods no ayudan

Al revisar los textos con peor chrF vi que muchas «referencias» de los mods eran traducciones a medias, con inglés y
español mezclados («Conveyor Belt Interruptor de», «Nivel II is better than Nivel I»). Castigaban traducciones buenas. Ahora
`armar_banco_local.py` descarta los pares cuya referencia comparte demasiadas palabras con el inglés (unos 1.500 de 13.900)
y el chrF del mismo motor sube a ~75. Con ese banco limpio (399 textos, Gemini 3.8 Flash, tres corridas por condición):

| Comparación | Diferencia de chrF (IC 95 %) |
|---|---|
| Sin pistas ni ejemplos → pistas y 8 ejemplos (el PR 4 completo) | −0,54 (−1,64 a +0,60), no se distingue del ruido |
| Sin pistas ni ejemplos → solo pistas | +0,70 (−0,18 a +1,59), no se distingue del ruido |
| Solo pistas → pistas y 8 ejemplos | **−1,24 (−2,26 a −0,27), empeora** |

- La ganancia de +1,4 que medí antes del PR 4 con el banco sucio **no se reproduce**: era en parte ruido de las referencias.
- Mandar ejemplos de otros mods empeora un poco el chrF con Gemini (también −0,64, sin significación, con el banco
  anterior). Una explicación posible es que cada mod tiene su propio vocabulario y los ejemplos arrastran el de otros.
  Por eso **la app ya no manda ejemplos por defecto** (`CANTIDAD_EN_LA_APP = 0`); el código sigue y `medir_calidad.py
  --n-ejemplos N` permite probarlos, sobre todo con modelos locales pequeños, que no se midieron.
- Las pistas (clave y tipo) quedan: no empeoran y la tendencia es positiva (+0,70), aunque no es concluyente.
- Los modelos no usaban regionalismos de España: busqué «vosotros», «ordenador», «zumo», «coger» y formas en «-áis/-éis» en
  las salidas de Gemini y de Gemma E2B y no apareció ninguno, así que no hice un chequeo de dialecto.
## 12 de noviembre de 2026 · contexto de vecindad en misiones

Cada texto de una misión (y de un libro) ahora lleva el título bajo el que está y la línea que viene antes, además
de su clave: «misión: description · dentro de «Mechanical Press…» · viene después de «The boiler will…»». En el corpus
no hay traducciones humanas de misiones, así que se mide con una comparación pareada: dos traducciones del mismo
texto (sin y con el contexto) pasan por un juez en los dos órdenes (`scripts/preferencia_pareada.py`). Una victoria
solo cuenta si el juez elige lo mismo en los dos órdenes. Banco local: misiones de FTB Quests de dos packs del corpus.

| Comparación | Textos distintos | Gana la mejora | Gana la base | Empate o juez inconsistente | p (signos) |
|---|---|---|---|---|---|
| Control: base contra base (120 textos) | 89 | 35 | 35 | 19 | 1,000 |
| Con vecindad contra base (120 textos) | 91 | 39 | 30 | 22 | 0,336 |
| Con vecindad contra base (400 textos) | 277 | 101 | 80 | 96 | 0,137 |

- El control sale 35 a 35: con el orden cambiado el juez no favorece a ningún lado cuando no hay diferencia real.
- La vecindad gana el 56–57 % de los casos decididos en las dos medidas, pero la diferencia no llega a ser
  concluyente (p = 0,14). Es una tendencia positiva, no una mejora demostrada. Cuesta unos 150 caracteres más por
  texto de entrada. Se mantiene porque no empeora y es barata, y se vuelve a medir con otros motores.
- El juez es el mismo modelo que tradujo, así que puede preferir su propio estilo; conviene repetirlo con otro.

## 13 de noviembre de 2026 · controles de forma y la temperatura que Gemini ignora

**La temperatura no estabiliza nada porque Gemini ya no la usa.** Google documenta que desde 3.5 Flash-Lite y
3.6 Flash la API ignora `temperature`, `top_p` y `top_k`, y que las próximas generaciones los rechazarán con un
error 400. Eso explica que antes «temperatura 0» no subiera la coincidencia entre corridas. La app ya no la manda a
esos modelos. Sin ella, la coincidencia sigue igual: en el banco de interfaz de 399 textos, dos corridas idénticas dan
el mismo texto en un 66–72 % de los casos, y las tres a la vez en ~59 %. Lo que fija un término es el glosario y la
memoria, no un parámetro.

**Controles de forma deterministas** para los «Leve» de la revisión humana (mayúsculas de términos del universo,
nombres que no se traducen, palabras duplicadas):
- un término del glosario que el original escribe como nombre propio dentro de una frase en minúscula sale con las
  mayúsculas del glosario (no los nombres del juego, que en español van en minúscula en medio de una frase);
- los nombres del juego que no se traducen («Creeper») y los de una palabra que el modelo dejó igual se protegen;
- un nombre corto que repite una palabra que el original no repite se reintenta;
- el reintento recibe la primera traducción y se le pide corregir solo lo que falló. Si el término sigue en inglés se
  cambia por el del glosario, y lo que no se arregla se acepta como «aceptado con dudas».

`medir_calidad.py --sin-controles` mide sin ellos y `--vanilla .descargas/vanilla` carga los nombres del juego como
oficiales, igual que la app. Gemini 3.8 Flash, tres corridas por condición:

| Banco | Comparación | Resultado |
|---|---|---|
| Interfaz (399 textos) | Primera versión: mayúsculas aunque el original pusiera mayúscula a todo | **−0,92 de chrF (IC −1,67 a −0,14), empeora** |
| Interfaz (399 textos) | Versión final: solo dentro de frases en minúscula | +0,24 (IC −0,26 a +0,81), no se distingue del ruido |
| Misiones (200 textos), juez Gemini 3.6 Flash | Con controles contra sin ellos, 137 textos distintos | 44 a 35 a favor de los controles (p = 0,37) |

- La primera versión estaba mal: en inglés los nombres de objetos ponen mayúscula a cada palabra («Speed Upgrade
  Module»), así que la regla creía que «Upgrade» era un nombre propio y escribía «Módulo de Mejora de velocidad».
  Ahora una mayúscula solo cuenta si la frase tiene alguna palabra larga en minúscula.
- Términos del glosario respetados: 221–228 de 244 con controles y 222–227 sin ellos. Contando plurales y otras
  formas (la exactitud de términos de WMT25, nueva en `medir_calidad.py`): 234–239 contra 236–239.
- En misiones la tendencia es positiva pero no concluyente. Ese banco no trae glosario del pack, así que ahí solo
  actúan los nombres del juego y las repeticiones; la mayor parte de los 137 cambios es la variación normal de Gemini.
- Se mantienen porque no empeoran y cubren casos concretos que el modelo falla una y otra vez. Las pruebas de
  `tests/test_controles_de_forma.py` reproducen los casos de la revisión humana.

## 13 de noviembre de 2026 · lo que traduce el juego manda (y un intento que no sirvió)

Primero probé un vocabulario base que imponía «item» → «objeto» por delante del juego, porque el es_mx de Minecraft
dice «Ítem». Funcionó en lo que buscaba: los textos con «item» pasaron de 62 «ítem» a 63 «objeto» en tres corridas.
Pero el chrF bajó **−1,07 (IC −1,76 a −0,42)** y los términos respetados del banco cayeron de ~225 a ~207: los
términos de los mods («Tubería de ítems») chocaban con la regla. Además, la decisión fue no corregir al juego: **lo
que el español del propio juego ya traduce se deja así, en cada dialecto**. El juego tampoco es uniforme: es_mx dice
«ítem» (101 veces) y es_es «objeto» (96).

Cómo queda:
- los nombres del juego se cargan antes que todo lo demás (menos el glosario del usuario);
- el vocabulario base solo completa lo que el juego no trae suelto («Netherite» → «Netherita») y se agrega después;
- una palabra que no es del juego («inframundita») se corrige en los términos de los mods;
- un término corto dentro de uno largo («Item» en «Item Frame») ya no se exige aparte;
- lo aceptado con dudas en el reintento sale en el informe final, con ejemplos, para revisarlo a mano.

| Comparación (interfaz, 399 textos, tres corridas) | Diferencia de chrF (IC 95 %) | Términos respetados |
|---|---|---|
| Vocabulario «objeto» por delante del juego | **−1,07 (−1,76 a −0,42), empeora** | 205–207 de 244 |
| Versión final (el juego manda) | +0,26 (−0,30 a +0,78), no se distingue del ruido | 227–230 de 244 |

**Caché de Gemini:** la caché implícita solo se activa con un prefijo idéntico de 4.096 tokens o más. Nuestro mensaje
de sistema es mucho más corto, y alargarlo con el glosario entero en cada pedido costaría más de lo que ahorra la
caché. No se hace.

## 13 de noviembre de 2026 · versión aparte para España

Con `--tambien-es-es`, `es_es` recibe su propia traducción (con los nombres del juego en España) y los demás archivos
de español siguen al dialecto elegido. Prueba real con Gemini 3.8 Flash: las 339 misiones de un modpack libre del
corpus (FTB Quests con carpeta `lang/`), US$ 0,09 las dos versiones.

| | Primera prueba: dos traducciones independientes | Con la versión latinoamericana como referencia |
|---|---|---|
| Textos donde es_mx y es_es deciden distinto qué nombre dejar en inglés | 64 de 339 | **8 de 339** |
| «inframundita» en es_es (el juego dice «netherita») | 2 | **0** |
| Textos idénticos en los dos dialectos | 100 | 224 |

- En la primera prueba cada dialecto decidía por su cuenta: es_mx dejaba «Arachnarch», «Summoner» y «Knight
  Phantoms», y es_es los traducía («Aracnarca», «Invocador», «caballeros fantasma»). Era la variación propia del
  modelo, no el dialecto. Ahora cada texto de España lleva la traducción latinoamericana con la instrucción de
  conservar sus decisiones y cambiar solo lo que en España se dice distinto. es_es sigue adaptando el dialecto
  («Entra en» por «Entra a», «lucha» por «pelea», «vigilarte la espalda»).
- «inframundita» ya no puede salir: las palabras que no son del juego se corrigen también en la traducción final, no
  solo en el glosario.
- **Lo que queda:** la versión es_mx no es coherente consigo misma con los nombres de jefes: en un texto deja
  «Arachnarch» y en otro escribe «Aracnarca»; deja «Summoner» y en otro pone «Convocador». La solución de hoy es el
  glosario del usuario (`"Arachnarch": "Arachnarch"`); lo siguiente es fijar esas decisiones dentro de cada modpack.

## 14 de noviembre de 2026 · nombres propios coherentes y códigos de color que escondían términos

En la prueba anterior, la versión es_mx no era coherente consigo misma: dejaba «Arachnarch» en un texto y escribía
«Aracnarca» en otro, o «Summoner» y «Convocador». Hubo dos cambios:

- **Nombres propios que se repiten, decididos una vez.** Antes de traducir misiones y libros, la app busca los nombres
  con mayúscula que salen en dos o más frases («Arachnarch», «Bronze Dungeons», «Starlit Crusher»), los traduce
  primero (el nombre de un jefe, una criatura única, una dimensión o un mod se deja igual) y fija esa decisión en el
  glosario del pack. La versión de España recibe los que quedaron sin traducir.
- **Códigos de color pegados a un término.** En «Defeat the &4Arachnarch» el «4» del código va pegado al nombre, y la
  búsqueda de palabras completas del glosario no lo veía: el término no se mandaba al modelo y la comprobación no lo
  exigía. En la traducción pasaba igual («&emazmorras» no se leía como «mazmorras»). Las misiones usan estos códigos
  todo el tiempo, así que el glosario fallaba en silencio en buena parte del texto. Ahora los códigos se quitan antes
  de buscar términos (`mascara.sin_formato`).

Prueba real (Gemini 3.8 Flash, 339 misiones de un modpack libre, una corrida por versión, US$ 0,09 cada una), contando
los nombres que se repiten y que es_mx unas veces deja en inglés y otras traduce:

| Versión | Nombres con decisiones distintas |
|---|---|
| Sin estos cambios | 13 |
| Nombres decididos una vez (primera prueba) | 7 |
| Lo mismo, repetido | 13 |
| **Con los códigos de color arreglados** | **1** («Wither») |

- Las dos corridas intermedias muestran cuánto varía Gemini: 7 y 13 con el mismo código. El arreglo de los códigos
  es lo que cambió el resultado: el nombre fijado ya se exigía en todas las frases, también en «Defeat the
  &4Arachnarch».
- Ahora «Arachnarch» queda igual en todos los textos y «Summoner» es «Invocador» en todos («mazmorra del Invocador»).
- Es una sola corrida en un solo modpack: la tendencia es clara, pero conviene confirmarla en otros.

## 14 de noviembre de 2026 · modelos locales solo con CPU (tope de 6 GB por modelo)

Tres modelos locales con `llama.cpp` compilado **solo para CPU** (sin GPU; commit `9183a55`), en un Xeon de 4 núcleos
a 2,1 GHz (AVX2 y AVX-512) con 15 GB de RAM. El usuario tiene un **tope de 6 GB de memoria por modelo**, así que la RAM
cuenta tanto como la calidad. Banco de interfaz armado de nuevo con `armar_banco_local.py` sobre los 24 packs del corpus
(553 jars): **400 textos**, glosario de 10.732 términos y los nombres del juego de vanilla 26.3 (`--vanilla`). Como en CPU
cada corrida tardó menos de 20 minutos, se midió el banco entero y no hizo falta la muestra de 100 textos. Mismos ajustes
para todos: `-c 4096 -np 1 -t 4 --reasoning off --cache-ram 0`, un pedido a la vez (`--hilos 1`), lotes locales de 12
textos o 1.800 caracteres, sin ejemplos (lo que usa la app).

| | Gemma 4 E2B | Gemma 4 E4B | Qwen3.5 4B |
|---|---|---|---|
| Archivo (Hugging Face, Apache 2.0) | QAT Q4_0 de Google, 3,35 GB | QAT Q4_0 de Google, 5,15 GB | Q4_K_M de unsloth, 2,74 GB |
| Textos aceptados | 397 de 400 (2 corridas iguales) | 399 de 400 | 399 de 400 |
| chrF (IC 95 %) | 73,7 (71,2 a 76,3); 2.ª corrida 73,6 | **74,6 (72,1 a 77,1)** | 70,7 (67,8 a 73,3) |
| Términos del glosario respetados | 532 de 612 (568 con plurales y otras formas) | **544 de 612** (569) | 522 de 612 (568) |
| Rechazos por motivo | códigos dañados 3 | códigos dañados 1 | códigos dañados 1 |
| Tiempo (400 textos) | **456 s** (1,1 s por texto) | 850 s (2,1 s) | 1.127 s (2,8 s) |
| Velocidad (lectura / escritura) | ~300 / ~16 tokens por segundo | ~86 / ~10 | ~80 / ~7 |
| RAM pico sin mmap (`--load-mode none`) | **3,7 GiB** | 5,7 GiB | 3,5 GiB |
| RAM pico con mmap (lo normal de `llama.cpp`) | 4,7 GiB | 7,9 GiB | 5,7 GiB |

Comparaciones pareadas (`comparar_mediciones.py`, mismos textos):

| Comparación | Diferencia de chrF (IC 95 %) |
|---|---|
| Gemma 4 E2B (2 corridas) → Gemma 4 E4B | +0,96 (−0,17 a +2,16), no se distingue del ruido |
| Qwen3.5 4B → Gemma 4 E2B (2 corridas) | **+2,90 (+1,39 a +4,36), Gemma mejor** |
| Qwen3.5 4B → Gemma 4 E4B | **+3,95 (+2,35 a +5,59), Gemma mejor** |
| Gemma 4 E4B sin ejemplos → con `--n-ejemplos 8` | −0,12 (−1,02 a +0,73), no se distingue del ruido |

Con 8 ejemplos, E4B aceptó los 400 textos (sin rechazos), pero respetó menos términos (530 de 613 contra 544 de 612) y
tardó 884 s. Tampoco ayuda en el modelo local: **se mantiene `CANTIDAD_EN_LA_APP = 0`**.

- **Cómo leer la RAM.** Con mmap (lo que hace `llama.cpp` por defecto), el archivo del modelo cuenta en la RAM del
  proceso y, además, en CPU los pesos Q4 se reordenan en una copia aparte para ir más rápido: una parte se cuenta dos
  veces. Sin mmap (`--load-mode none`) se carga una sola copia: es la memoria que el modelo necesita de verdad. Esa cifra
  se midió aparte, con un pedido de ~700 tokens (los búferes se reservan al cargar según `-c 4096`, así que el pico no
  cambia con más pedidos). Son GiB (lo que Windows muestra como «GB»): E4B sin mmap ocupa 5,7 GiB (6,1 GB decimales),
  **justo en el tope**, y con mmap lo pasa (7,9 GiB). E2B y Qwen caben con margen.
- **Dos ajustes que importan en CPU.** Sin `--reasoning off`, Gemma 4 «piensa» antes de responder: un pedido de dos textos
  tardó 34 s (568 tokens) en vez de 2,4 s (41 tokens). Sin `--cache-ram 0`, `llama-server` guarda prompts viejos en RAM
  (hasta 8 GB por defecto) y la RAM de E2B subió de 4,7 a 5,5 GiB en una corrida; no cambia la calidad (73,7 y 73,6).
- Dos corridas de E2B con los mismos ajustes dieron el mismo texto en 339 de 395 casos (86 %); Gemini daba 66–72 % en el
  banco anterior. En cada modelo solo un texto salió idéntico al inglés («Icon» en Gemma, «Chest Slayer» en Qwen), y no apareció
  ningún regionalismo de España («vosotros», «ordenador», «coger», «-áis/-éis»). La consistencia de términos dio
  0,78–0,81 en los cuatro casos, sin diferencias claras.
- Las corridas se hicieron con el código anterior a los nombres propios coherentes y los códigos de color (sección de
  arriba). Repetí E2B con el código que ya los incluye: 397 de 400, chrF 73,7 (IC 71,1 a 76,2; diferencia pareada
  +0,03, IC −0,32 a +0,44), 530 de 610 términos (el total cambia porque
  ahora se ven los términos pegados a un código de color, que salen en 5 de los 400 textos), 443 s y la misma RAM. En la
  interfaz esos cambios no mueven el resultado, porque los nombres propios solo se unifican en misiones y libros.
- **No es comparable con la referencia anterior** (Gemma 4 E2B, chrF 64,1 en 100 textos, 12 de noviembre): aquel banco
  era otro, de antes de limpiar las referencias a medias, y se midió con GPU y carga segura. Gemini no se midió en este
  banco (sin clave de API), así que tampoco hay una comparación directa con él.

**Recomendación:** con CPU y 6 GB por modelo, **Gemma 4 E2B (QAT Q4_0)** como modelo local por defecto. E4B da +1 punto
de chrF y 12 términos más, pero la mejora no se distingue del ruido, tarda casi el doble y solo cabe en 6 GB si se carga
sin mmap y sin caché de prompts. Queda como opción para quien prefiera algo más de calidad y tenga RAM de sobra. Qwen3.5
4B no se recomienda: es claramente peor que los dos Gemma y el más lento. En cualquier caso, `--reasoning off`.

Cómo repetirlo (comprobando antes que el puerto esté libre y apagando el servidor al terminar):

```
llama-server -m gemma-4-E2B_q4_0-it.gguf --alias gemma-4-e2b --host 127.0.0.1 --port PUERTO -c 4096 -np 1 -t 4 --reasoning off --cache-ram 0 --no-webui
uv run python scripts/medir_calidad.py --motor personalizado --direccion http://127.0.0.1:PUERTO/v1 --modelo gemma-4-e2b --banco .descargas/banco/ui_final.json --vanilla .descargas/vanilla --hilos 1 --salida build/gemma-4-e2b.json
uv run python scripts/comparar_mediciones.py --a build/qwen3.5-4b.json --b build/gemma-4-e2b.json
```

`.descargas/vanilla/` (en_us, es_mx y es_es de la última versión) se armó a mano desde los servidores de Mojang: en_us
del jar del cliente, leído por rangos, y es_mx y es_es del índice de assets. `descargar_lang.py` baja solo los idiomas
de los mods.

## Cómo repetirlo

```
uv run python scripts/medir_calidad.py --revisar
uv run python scripts/medir_calidad.py --motor ollama --modelo NOMBRE --revisar
uv run python scripts/armar_banco_local.py
uv run python scripts/medir_calidad.py --banco .descargas/banco/referencia_real.json
uv run python scripts/medir_calidad.py --banco .descargas/banco/referencia_real.json --sin-contexto
uv run python scripts/comparar_mediciones.py --a build/sin1.json build/sin2.json --b build/con1.json build/con2.json
uv run python scripts/juzgar_calidad.py --entrada build/con1.json
uv run python scripts/armar_banco_misiones.py --textos 400
uv run python scripts/medir_calidad.py --sin-vecindad --banco .descargas/banco/misiones.json --salida build/base.json
uv run python scripts/medir_calidad.py --banco .descargas/banco/misiones.json --salida build/mejora.json
uv run python scripts/preferencia_pareada.py --a build/base.json --b build/mejora.json
uv run python scripts/medir_calidad.py --banco .descargas/banco/ui_final.json --vanilla .descargas/vanilla --sin-controles
```

El costo es una estimación con los precios de Google de noviembre de 2026, no lo que cobró la API.

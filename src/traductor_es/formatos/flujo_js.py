"""Mensajes que un script arma por partes y manda después.

    let mensaje = 'Te has ganado '
    mensaje += efecto.name            // «name» es un texto que ve el jugador
    mensaje += global.nombres[clave]   // «nombres» es una tabla de textos que ve el jugador
    player.tell(mensaje)

Aquí solo se lee el código para saber qué variables, miembros y tablas acaban en un mensaje. Decidir qué
cadenas se traducen es cosa del módulo de scripts.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from .javascript import CadenaJs

_IDENT = r"[A-Za-z_$][\w$]*"
_RUTA = rf"{_IDENT}(?:\.{_IDENT})*"
_AGREGADO = re.compile(rf"\b({_IDENT})\s*\+=\s*({_RUTA})(?:(\[[^\]\n]*\])(?:\.({_IDENT}))?)?")
_ASIGNADA = re.compile(rf"({_IDENT})\s*\+?=\s*$")
_CLAVE = re.compile(rf"(?:({_IDENT})|['\"]([^'\"\n]+)['\"])\s*:\s*$")
_VENTANA = 160  #: cuánto código hacia atrás se mira para saber a qué se asigna una cadena


@dataclass(frozen=True, slots=True)
class Flujo:
    variables: frozenset[str] = frozenset()  #: variables que se pasan a una llamada de texto: `tell(mensaje)`
    miembros: frozenset[str] = frozenset()  #: `mensaje += efecto.name` → «name»
    tablas: frozenset[str] = frozenset()  #: `mensaje += global.nombres[clave]` → «nombres»


def analizar(src: str, llamadas: str) -> Flujo:
    """`llamadas`: expresión regular con las llamadas cuyo argumento es texto para el jugador."""
    pasadas = re.compile(rf"(?:{llamadas})\s*\(\s*({_IDENT})\s*[,)]")
    variables = frozenset(pasadas.findall(src))
    if not variables:
        return Flujo()
    miembros: set[str] = set()
    tablas: set[str] = set()
    for variable, ruta, indice, miembro in _AGREGADO.findall(src):
        if variable not in variables:
            continue
        ultimo = ruta.rsplit(".", 1)[-1]
        if miembro:  # `efectos[i].name`: el texto es el miembro
            miembros.add(miembro)
        elif indice:  # `nombres[clave]`: el texto está en la tabla
            tablas.add(ultimo)
        elif "." in ruta:
            miembros.add(ultimo)
    return Flujo(variables, frozenset(miembros), frozenset(tablas))


def asignada_a(src: str, cadena: CadenaJs) -> str | None:
    """La variable a la que se asigna o se suma esta cadena (`msg = '…'`, `msg += '…'`)."""
    m = _ASIGNADA.search(src[max(0, cadena.inicio - _VENTANA) : cadena.inicio])
    return m.group(1) if m else None


def clave_de(src: str, cadena: CadenaJs) -> str | None:
    """La clave de objeto a la que pertenece esta cadena como valor (`name: '…'`)."""
    m = _CLAVE.search(src[max(0, cadena.inicio - _VENTANA) : cadena.inicio])
    return (m.group(1) or m.group(2)) if m else None


def cuerpos_de_tabla(src: str, cadenas: Sequence[CadenaJs], tablas: Iterable[str]) -> list[tuple[int, int]]:
    """Posiciones (inicio, fin) del contenido de las tablas `x.nombres = { … }` con esos nombres."""
    nombres = frozenset(tablas)
    if not nombres:
        return []
    en_cadena = {c.inicio: c.fin for c in cadenas}
    cuerpos: list[tuple[int, int]] = []
    for m in re.finditer(rf"({_RUTA})\s*=\s*\{{", src):
        if m.group(1).rsplit(".", 1)[-1] not in nombres:
            continue
        i, profundidad = m.end(), 1
        while i < len(src) and profundidad:
            if i in en_cadena:
                i = en_cadena[i]
                continue
            profundidad += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        cuerpos.append((m.end(), i))
    return cuerpos


# ---------------------------------------------------------------------------------------------- funciones de texto
#: Métodos que transforman un texto sin cambiar de qué se trata (el resultado sigue siendo ese texto o sus líneas).
_TRANSFORMA = frozenset({
    "split", "trim", "trimStart", "trimEnd", "replace", "replaceAll", "slice", "substring", "concat", "join", "map",
    "filter", "forEach", "toString", "padStart", "padEnd", "repeat",
})  # fmt: skip
#: Si en la línea se compara o se busca el texto, es lógica: esa función no se toca.
_LOGICA = re.compile(
    r"[!=]==?(?!>)|\.(?:includes|indexOf|startsWith|endsWith|match|test|search|equals|localeCompare)\s*\(|\bswitch\b|\bcase\b"
)
_FUNCIONES = (
    re.compile(rf"\bfunction\s+({_IDENT})\s*\(([^)]*)\)\s*\{{"),
    re.compile(
        rf"\b(?:const|let|var)\s+({_IDENT})\s*=\s*(?:async\s*)?(?:function\s*\w*\s*)?\(([^)]*)\)\s*(?:=>\s*)?\{{"
    ),
    re.compile(rf"\b(?:const|let|var)\s+({_IDENT})\s*=\s*({_IDENT})\s*=>\s*\{{"),
)
_ASIGNACION = re.compile(rf"\s*(?:(?:const|let|var)\s+)?({_IDENT})\s*(\+?=)(?!=)")
_CALLBACK = re.compile(rf"(?:\(\s*({_IDENT})\s*(?:,[^)]*)?\)|\b({_IDENT}))\s*=>|function\s*\(\s*({_IDENT})")


def _en_blanco(src: str, cadenas: Sequence[CadenaJs]) -> str:
    """El código con las cadenas y los comentarios en blanco (mismas posiciones): solo queda lo que es código."""
    letras = list(src)
    for c in cadenas:
        for i in range(c.inicio, c.fin):
            if letras[i] != "\n":
                letras[i] = " "
    limpio = "".join(letras)
    return re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), limpio, flags=re.S)


def _cierre(limpio: str, abierta: int) -> int:
    profundidad, i = 1, abierta
    while i < len(limpio) and profundidad:
        profundidad += {"{": 1, "}": -1}.get(limpio[i], 0)
        i += 1
    return i if profundidad == 0 else -1


def _linea(cuerpo: str, pos: int) -> tuple[int, str]:
    inicio = cuerpo.rfind("\n", 0, pos) + 1
    fin = cuerpo.find("\n", pos)
    return inicio, cuerpo[inicio : len(cuerpo) if fin < 0 else fin]


def _tomar_callbacks(trozo: str, base: int, vistos: set[str], pendientes: list[str], declaraciones: set[int]) -> None:
    """`texto.map(l => …)`: el parámetro del callback también es texto y se sigue; su declaración no es un uso."""
    for cb in _CALLBACK.finditer(trozo):
        grupo = 1 if cb.group(1) else 2 if cb.group(2) else 3
        nuevo = cb.group(grupo)
        if nuevo:
            declaraciones.add(base + cb.start(grupo))
            if nuevo not in vistos:
                vistos.add(nuevo)
                pendientes.append(nuevo)


def _uso_permitido(
    cuerpo: str, nombre: str, m: re.Match[str], vistos: set[str], pendientes: list[str], declaraciones: set[int]
) -> bool:
    """Un uso de un nombre de texto que no es mostrarlo directamente: ¿es solo derivar otro texto de él?"""
    inicio_linea, linea = _linea(cuerpo, m.start())
    if _LOGICA.search(linea):
        return False
    asignacion = _ASIGNACION.match(linea)
    if asignacion:
        if asignacion.start(1) + inicio_linea <= m.start() < asignacion.end(1) + inicio_linea:
            return True  # es el lado izquierdo: se vuelve a asignar
        derivado = asignacion.group(1)
        if derivado not in vistos:
            vistos.add(derivado)
            pendientes.append(derivado)
        _tomar_callbacks(linea[m.end() - inicio_linea :], m.end(), vistos, pendientes, declaraciones)
        return True
    metodo = re.match(rf"\s*{re.escape(nombre)}\s*\.\s*(\w+)\s*\(", linea)
    if metodo and metodo.group(1) in _TRANSFORMA and metodo.start() + inicio_linea <= m.start():
        _tomar_callbacks(linea[metodo.end() :], inicio_linea + metodo.end(), vistos, pendientes, declaraciones)
        return True
    return False


def _parametro_es_solo_texto(
    cuerpo: str,
    parametro: str,
    patron: str,
    plantillas: list[tuple[CadenaJs, set[str]]],
    es_sumidero: Callable[[CadenaJs], bool],
) -> bool:
    """Todos los usos del parámetro (y de lo derivado) son mostrarlo: nunca se compara, busca, guarda ni devuelve."""
    sumidero_antes = re.compile(rf"(?:{patron})\s*\(\s*$")
    pendientes, vistos, sumideros = [parametro], {parametro}, 0
    declaraciones: set[int] = set()  # dónde se declara el parámetro de un callback (`l => …`): no es un uso
    while pendientes:
        nombre = pendientes.pop()
        # un `${nombre}` dentro de una plantilla vale solo si la plantilla se muestra tal cual
        for c, nombres in plantillas:
            if nombre in nombres and not es_sumidero(c):
                return False
            sumideros += nombre in nombres
        for m in re.finditer(rf"(?<![\w$.]){re.escape(nombre)}(?![\w$])", cuerpo):
            if m.start() in declaraciones:
                continue
            if sumidero_antes.search(cuerpo[: m.start()]) and re.match(r"\s*[,)]", cuerpo[m.end() :]):
                sumideros += 1
            elif not _uso_permitido(cuerpo, nombre, m, vistos, pendientes, declaraciones):
                return False
    return sumideros > 0


def funciones_de_texto(
    src: str, cadenas: Sequence[CadenaJs], patron: str, es_sumidero: Callable[[CadenaJs], bool]
) -> set[tuple[str, int]]:
    """Funciones del propio script cuyo parámetro N solo sirve para mostrarse: {(nombre, posición del parámetro)}.

    Pasar una frase en esa posición es escribir un texto visible, aunque la llamada no sea `tell` ni `Text.of`. Es
    conservador: si el parámetro se compara, se busca, se guarda, se devuelve o se pasa a algo que no se entiende, la
    función queda fuera. La función tampoco puede usarse como valor (`callback = f`): solo se llama.
    """
    limpio = _en_blanco(src, cadenas)
    plantillas_todas = [
        (c, set(re.findall(_IDENT, " ".join(re.findall(r"\$\{([^{}\n]*)\}", c.texto)))))
        for c in cadenas
        if c.comilla == "`" and "${" in c.texto
    ]
    resultado: set[tuple[str, int]] = set()
    definiciones: dict[str, int] = {}
    encontradas: list[tuple[str, list[str], int, int, int]] = []
    for patron_def in _FUNCIONES:
        for m in patron_def.finditer(limpio):
            nombre, params = m.group(1), [p.strip() for p in m.group(2).split(",")]
            fin = _cierre(limpio, m.end())
            if fin > 0:
                definiciones[nombre] = definiciones.get(nombre, 0) + 1
                encontradas.append((nombre, params, m.start(), m.end(), fin))
    for nombre, params, desde, inicio, fin in encontradas:
        fuera = limpio[:desde] + " " + limpio[fin:]  # el resto del script, sin la propia definición
        usos_como_valor = re.search(rf"(?<![\w$.]){re.escape(nombre)}(?![\w$])(?!\s*\()", fuera)
        if definiciones[nombre] != 1 or usos_como_valor:
            continue
        cuerpo = limpio[inicio : fin - 1]
        plantillas = [(c, n) for c, n in plantillas_todas if inicio <= c.inicio < fin]
        for i, bruto in enumerate(params):
            parametro = bruto.split("=")[0].strip()
            if re.fullmatch(_IDENT, parametro) and _parametro_es_solo_texto(
                cuerpo, parametro, patron, plantillas, es_sumidero
            ):
                resultado.add((nombre, i))
    return resultado

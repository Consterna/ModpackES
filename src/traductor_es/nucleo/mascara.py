"""Protección de códigos: todo lo que el traductor no debe tocar se cambia por ⟦n⟧ antes de enviarlo.

Al volver, la traducción solo se acepta si trae exactamente los mismos marcadores.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Final

#: Carácter de uso privado con el que los formatos marcan escapes que hay que conservar tal cual.
ESCAPE_CRUDO: Final = chr(0xE000)

_PATRONES: Final[tuple[str, ...]] = (
    # escapes del formato de origen (\n en SNBT, etc.), incluido barra + salto real; uno de control, entero
    ESCAPE_CRUDO + r"(?:u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[\s\S])",
    r"\$\([^)]*\)",  # macros de Patchouli: $(l) $(item) $(l:ruta) $()
    r"\$\{[^{}\n]*\}",  # expresiones de plantillas de JavaScript: ${precio}
    r"\{[^{}\n]*\}",  # FTB Quests {image:..} {@pagebreak} {clave}, {0} de Java
    r"%(?:\d+\$)?[-#+0,(]*\d*(?:\.\d+)?[sdfxXcbeEgGoh%n]",  # printf: %s %1$s %d %.1f %%
    r"[§&][0-9a-fk-orA-FK-OR]",  # códigos de color y estilo
    r"<NEWLINE>",  # salto de los libros de Citadel
    r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>",  # etiquetas: GuideME <ItemLink .../>, <br>, <b>
    r"!\[[^\]]*\]\([^)\s]*\)",  # imagen markdown completa
    r"\]\([^)\s]+\)",  # destino de un enlace markdown: el texto sí se traduce
    r"https?://[^\s)\]}>\"']+",  # enlaces
    r"\\[nrt]",  # \n escrito como texto
    r"[\n\r\t]",  # saltos reales
    r"(?<![\w/:.])/[a-z][a-z0-9_]*",  # comandos como /home o /tpa
    r"\b[a-z0-9_.-]+:[a-z0-9_./-]*[a-z0-9_/]",  # ids de recursos: minecraft:stone, create:item/x
)
PROTEGER: Final = re.compile("|".join(f"(?:{p})" for p in _PATRONES))
TOKEN: Final = re.compile(r"⟦(\d+)⟧")
_MARCADOR_CON_ESPACIOS: Final = re.compile(r"⟦\s*(\d+)\s*⟧")
_LETRAS: Final = re.compile(r"[^\W\d_]{2}")


@dataclass(frozen=True, slots=True)
class Enmascarado:
    texto: str
    tokens: tuple[str, ...]


def enmascarar(texto: str) -> Enmascarado:
    tokens: list[str] = []

    def cambiar(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return f"⟦{len(tokens) - 1}⟧"

    return Enmascarado(PROTEGER.sub(cambiar, texto), tuple(tokens))


def desenmascarar(traducido: str, tokens: tuple[str, ...]) -> str | None:
    """Restaura los códigos. Devuelve None si el traductor perdió, repitió o inventó algún marcador.

    Antes repara un desliz frecuente de los modelos: espacios dentro del marcador («⟦ 0 ⟧»).
    """
    traducido = _MARCADOR_CON_ESPACIOS.sub(lambda m: f"⟦{m.group(1)}⟧", traducido)
    vistos = sorted(int(n) for n in TOKEN.findall(traducido))
    if vistos != list(range(len(tokens))):
        return None
    restaurado = TOKEN.sub(lambda m: tokens[int(m.group(1))], traducido)
    return None if "⟦" in restaurado or "⟧" in restaurado else restaurado


def es_traducible(texto: str) -> bool:
    """Hay algo que traducir si, quitando los códigos, quedan al menos dos letras seguidas."""
    return bool(_LETRAS.search(TOKEN.sub(" ", enmascarar(texto).texto)))


def separar_bordes(texto: str) -> tuple[str, str, str]:
    """Separa espacios iniciales y finales, que se conservan tal cual y no se mandan a traducir."""
    nucleo = texto.strip()
    if not nucleo:
        return texto, "", ""
    inicio = len(texto) - len(texto.lstrip())
    return texto[:inicio], nucleo, texto[inicio + len(nucleo) :]


#: Códigos de color y formato de Minecraft («&4», «§l»), pegados al texto que colorean.
_CODIGO_DE_FORMATO = re.compile(r"[&§][0-9a-fk-orA-FK-OR]")


def sin_formato(texto: str) -> str:
    """El texto sin códigos de color ni de formato, para buscar palabras en él.

    «Defeat the &4Arachnarch»: con el código, el «4» va pegado al nombre y «Arachnarch» no es una palabra completa.
    """
    return _CODIGO_DE_FORMATO.sub("", texto)


# ---------------------------------------------------------------- argumentos y pares de formato
#: Un argumento printf que recibe un valor (no `%%` ni `%n`): %s %d %1$s %.1f
_ARGUMENTO: Final = re.compile(r"%(?:(\d+)\$)?[-#+0,(]*\d*(?:\.\d+)?[sdfxXcbeEgGoh]")
#: Códigos que cierran un formato: §r, $() de Patchouli, $(/l), </b>
_CIERRE: Final = re.compile(r"[§&][rR]|\$\(\)|\$\(/[a-z]*\)|</[A-Za-z][A-Za-z0-9]*>")
#: Códigos que no abren nada: saltos y listas de Patchouli, teclas, <br> y etiquetas que se cierran solas
_NEUTRO: Final = re.compile(r"\$\((?:br2?|li|p|k:[^)]*)\)|<br\s*/?>|<[^<>]*/>")
#: Códigos que abren un formato que luego se cierra: colores y estilos, macros de Patchouli, etiquetas
_APERTURA: Final = re.compile(r"[§&][0-9a-fk-oA-FK-O]|\$\([^)]+\)|<[A-Za-z][^<>]*>")


def _orden(traducido: str) -> list[int]:
    """Los marcadores en el orden en que los escribió el modelo."""
    return [int(n) for n in TOKEN.findall(_MARCADOR_CON_ESPACIOS.sub(lambda m: f"⟦{m.group(1)}⟧", traducido))]


def es_argumento(token: str) -> bool:
    return _ARGUMENTO.fullmatch(token) is not None


def posicionar_argumentos(traducido: str, tokens: tuple[str, ...]) -> tuple[tuple[str, ...], bool] | None:
    """Si el modelo cambió el orden de los argumentos sin posición («%s … %s»), los numera según el original.

    «%s was slain by %s» → «⟦1⟧ fue asesinado por ⟦0⟧»: sin numerar, el juego pondría los valores al revés. Con
    `%1$s` y `%2$s` (que Minecraft admite y usa en su propio español) cada valor va a su sitio.
    Devuelve (tokens, si cambiaron), o None si no se puede arreglar: el original mezcla argumentos con y sin número.
    """
    argumentos = [i for i, t in enumerate(tokens) if es_argumento(t)]
    if len(argumentos) < 2:
        return tokens, False
    elegidos = set(argumentos)
    orden = [i for i in _orden(traducido) if i in elegidos]
    if orden == argumentos:
        return tokens, False
    sin_numero = [i for i in argumentos if (m := _ARGUMENTO.fullmatch(tokens[i])) and m.group(1) is None]
    if not sin_numero:  # ya están numerados: cambiarlos de orden es válido
        return tokens, False
    if len(sin_numero) != len(argumentos):
        return None
    nuevos = list(tokens)
    for numero, i in enumerate(argumentos, 1):
        nuevos[i] = tokens[i].replace("%", f"%{numero}$", 1)
    return tuple(nuevos), True


def escapar_porcentajes(traducido: str) -> str:
    """Un «%» que escribió el modelo («50 %») pasa a «%%»: con argumentos, un «%» suelto rompe el formato."""
    return traducido.replace("%", "%%")


def pares_en_orden(traducido: str, tokens: tuple[str, ...]) -> bool:
    """¿Cada código que abre un formato (§l, $(l), <b>) sigue antes del que lo cierra (§r, $(), </b>)?

    Mover un par entero es válido («the §aIron§r §bSword§r» → «la §bEspada§r de §aHierro§r»); lo que no vale es
    dejar el cierre antes de su apertura, que pinta otras palabras.
    """
    posicion = {indice: lugar for lugar, indice in enumerate(_orden(traducido))}
    abiertos: list[int] = []
    for indice, token in enumerate(tokens):
        if _CIERRE.fullmatch(token):
            cierre = posicion.get(indice)
            if cierre is not None and any(posicion.get(a, -1) > cierre for a in abiertos):
                return False
            abiertos = []
        elif _APERTURA.fullmatch(token) and not _NEUTRO.fullmatch(token):
            abiertos.append(indice)
    return True


def codigos_inventados(restaurado: str, tokens: tuple[str, ...], porcentajes: int = 0) -> bool:
    """¿La traducción trae códigos que no vienen de los marcadores (un «§a» o un «%s» que escribió el modelo)?

    `porcentajes` son los «%%» que se agregaron a propósito con `escapar_porcentajes`.
    """
    esperados = Counter(tokens)
    if porcentajes:
        esperados["%%"] += porcentajes
    return Counter(enmascarar(restaurado).tokens) != esperados

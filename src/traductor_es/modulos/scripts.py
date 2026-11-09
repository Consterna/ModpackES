"""Texto escrito directamente en los scripts de KubeJS (tooltips, mensajes, nombres visibles).

Solo se traducen cadenas en sitios donde son texto para el jugador. Todo lo que es lógica (ids, tags,
recetas, comparaciones) se deja igual. Los archivos se traducen en el sitio, con copia de seguridad.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..formatos import comandos, componente, flujo_js, javascript
from ..formatos.kubejs_api import llamadas_de_texto
from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, contar, parece_clave

AMBITO = "script"
CARPETAS = ("kubejs/client_scripts", "kubejs/server_scripts", "kubejs/startup_scripts")

#: Llamadas cuyo argumento de texto es siempre algo que ve el jugador (de todas las versiones de KubeJS; la lista por
#: versión está en `formatos/kubejs_api.py`).
LLAMADAS_TEXTO = llamadas_de_texto(None)
#: Llamadas que ejecutan un comando: si es `tellraw`, `title`, `say`…, el texto del mensaje se traduce.
LLAMADAS_COMANDO = frozenset({"runCommand", "runCommandSilent"})
#: `Text.of("…")`, `Text.red("…")`, `Component.literal("…")`…
AYUDAS_TEXTO = frozenset({
    "of", "literal", "string", "black", "darkBlue", "darkGreen", "darkAqua", "darkRed", "darkPurple", "gold", "gray",
    "darkGray", "blue", "green", "aqua", "red", "lightPurple", "yellow", "white",
})  # fmt: skip
RECEPTORES_TEXTO = frozenset({"Text", "Component"})
#: Dentro de estos eventos, `add`, `addAll`… reciben líneas de tooltip, textos de idioma o de información.
EVENTOS_TEXTO = (
    "ItemEvents.tooltip", "ClientEvents.lang", "JEIEvents.information", "REIEvents.information",
    "EMIEvents.information", "onEvent:item.tooltip", "onEvent:jei.information", "onEvent:rei.information",
    "onEvent:client.generate_assets",
)  # fmt: skip
LLAMADAS_EN_EVENTO = frozenset({"add", "addAll", "insert", "addAdvanced", "addItem", "addFluid", "addLang", "addLine"})


def _llamadas_re(llamadas: frozenset[str]) -> str:
    """Las llamadas de texto (`tell`, `Text.of`…) como regex, para saber qué variables acaban en un mensaje."""
    return (
        rf"\b(?:{'|'.join(sorted(llamadas))})|\b(?:{'|'.join(sorted(RECEPTORES_TEXTO))})"
        rf"\.(?:{'|'.join(sorted(AYUDAS_TEXTO))})"
    )


_EXPRESION = re.compile(r"\$\{[^{}\n]*\}")
#: Lo que va entre `<>` o `[]` en el texto de otro mod (etiquetas de formato) o entre `${}` (código del script).
_ETIQUETA = re.compile(r"<[^<>\n]*>|\[[^\[\]\n]*\]|\$\{[^{}\n]*\}")
_PALABRA = re.compile(r"[A-Za-z']+")
#: Palabras de enlace del inglés que casi nunca aparecen en un comando: dos o más indican una frase.
_ENLACES_INGLES = frozenset({
    "the", "and", "of", "to", "is", "are", "you", "your", "it", "we", "that", "this", "be", "have", "will",
    "can", "not", "with", "for", "from", "until", "when", "if", "my", "i",
})  # fmt: skip


def _parece_texto(texto: str) -> bool:
    """Texto para personas y no un identificador: tiene un espacio, una mayúscula o una letra no ASCII."""
    t = texto.strip()
    return es_traducible(t) and not parece_clave(t) and (" " in t or t != t.lower() or not t.isascii())


def _seguro(c: javascript.CadenaJs, traduccion: str) -> bool:
    """En una plantilla, un «${» nuevo sería código vivo: esa traducción no se usa."""
    return c.comilla != "`" or traduccion.count("${") == c.texto.count("${")


def es_texto_visible(c: javascript.CadenaJs, llamadas: frozenset[str] = LLAMADAS_TEXTO) -> bool:
    if c.comparada or not _parece_texto(c.texto):
        return False
    if c.comilla == "`" and c.texto.count("${") != len(_EXPRESION.findall(c.texto)):
        return False  # plantilla con expresiones complejas: no se puede proteger con seguridad
    if c.funcion in llamadas:
        return True
    if c.funcion in AYUDAS_TEXTO and c.receptor in RECEPTORES_TEXTO:
        return True
    return c.funcion in LLAMADAS_EN_EVENTO and any(ctx.startswith(EVENTOS_TEXTO) for ctx in c.contexto)


_LOGICA = ("recipes", "tags", "loot", "worldgen", "registry", "highPriorityData")


def parece_frase_sin_elegir(c: javascript.CadenaJs) -> bool:
    """Una cadena con aspecto de frase (3 palabras o más, empieza en mayúscula) fuera de recetas y etiquetas."""
    t = c.texto.strip()
    return (
        not c.comparada
        and c.receptor != "console"  # los registros del script no los ve el jugador
        and t[:1].isupper()
        and len(t.split()) >= 3
        and _parece_texto(t)
        and not any(m in ctx for ctx in c.contexto for m in _LOGICA)
    )


def _plantilla_segura(c: javascript.CadenaJs) -> bool:
    return c.comilla != "`" or c.texto.count("${") == len(_EXPRESION.findall(c.texto))


def _es_sumidero(c: javascript.CadenaJs, llamadas: frozenset[str]) -> bool:
    """La cadena se le pasa directamente a algo que le muestra texto al jugador (`tell`, `Text.of`…)."""
    return c.funcion in llamadas or (c.funcion in AYUDAS_TEXTO and c.receptor in RECEPTORES_TEXTO)


def es_texto_de_funcion(c: javascript.CadenaJs, funciones: set[tuple[str, int]]) -> bool:
    """La cadena va en la posición de un parámetro que la función solo muestra (ver `flujo_js.funciones_de_texto`)."""
    if c.receptor is not None or c.funcion is None or c.comparada or (c.funcion, c.arg) not in funciones:
        return False  # una llamada con receptor (`x.f(...)`) es un método, no la función del script
    t = c.texto.strip()
    return _plantilla_segura(c) and es_traducible(t) and not parece_clave(t) and any(ch.isalpha() for ch in t)


def textos_armados(
    src: str, cadenas: list[javascript.CadenaJs], flujo: flujo_js.Flujo, tablas: frozenset[str]
) -> list[javascript.CadenaJs]:
    """Cadenas que son parte de un mensaje armado por trozos: `let msg = 'Hola '; msg += x; player.tell(msg)`.

    Se eligen las que se asignan o suman a una variable que acaba en `tell`…, los valores `name:` de lo que se
    suma a ella (`msg += efecto.name`) y los valores de las tablas de nombres que se suman (`msg += nombres[k]`).
    """
    cuerpos = flujo_js.cuerpos_de_tabla(src, cadenas, tablas)
    elegidas: list[javascript.CadenaJs] = []
    for c in cadenas:
        if c.comparada or not _plantilla_segura(c) or not any(ch.isalpha() for ch in c.texto):
            continue
        if flujo_js.asignada_a(src, c) in flujo.variables:
            # Trozos como «or » o «and » no parecen texto solos, pero aquí sí lo son
            visible = es_traducible(c.texto.strip()) and not parece_clave(c.texto)
        else:
            clave = flujo_js.clave_de(src, c)
            visible = (
                clave is not None
                and (clave in flujo.miembros or any(a <= c.inicio < b for a, b in cuerpos))
                and _parece_texto(c.texto)
            )
        if visible:
            elegidas.append(c)
    return elegidas


def unidades_comando(cmd: comandos.Comando) -> list[str]:
    """Los textos que ve el jugador dentro de un comando de chat."""
    if not cmd.json:
        return [cmd.cuerpo] if _parece_texto(cmd.cuerpo) else []
    partes = componente.unidades(cmd.cuerpo)  # None: formato que no se reconoce, no se toca
    return [p for p in partes or [] if not parece_clave(p)]


def aplicar_comando(cmd: comandos.Comando, traducciones: Mapping[str, str]) -> str:
    if not cmd.json:
        return cmd.prefijo + traducciones.get(cmd.cuerpo, cmd.cuerpo)
    return cmd.prefijo + componente.reconstruir(cmd.cuerpo, traducciones)


def comando_visible(c: javascript.CadenaJs) -> comandos.Comando | None:
    """El comando de chat que esta cadena le pasa a `runCommand`, si lo hay y trae texto para traducir."""
    if c.comparada or c.funcion not in LLAMADAS_COMANDO:
        return None
    if c.comilla == "`" and c.texto.count("${") != len(_EXPRESION.findall(c.texto)):
        return None
    cmd = comandos.analizar(c.texto)
    return cmd if cmd is not None and unidades_comando(cmd) else None


def frase_en_comando_ajeno(c: javascript.CadenaJs) -> bool:
    """`runCommand` recibe un comando que no es de chat y que lleva una frase en inglés (p. ej. `emberstextapi queue`).

    La app no conoce el formato de los comandos de otros mods y no los toca: solo se avisa en el informe.
    """
    if c.comparada or c.funcion not in LLAMADAS_COMANDO or comandos.analizar(c.texto) is not None:
        return False
    palabras = _PALABRA.findall(_ETIQUETA.sub(" ", c.texto))
    return len(palabras) >= 5 and sum(p.lower() in _ENLACES_INGLES for p in palabras) >= 2


@dataclass(slots=True)
class _Script:
    ruta: Path
    src: str
    cadenas: list[javascript.CadenaJs]
    elegidas: list[javascript.CadenaJs]
    #: Cadenas elegidas que son un comando de chat (por posición): se traduce el mensaje, no la línea entera.
    ordenes: dict[int, comandos.Comando] = field(default_factory=dict[int, comandos.Comando])

    def unidades(self, c: javascript.CadenaJs) -> list[str]:
        cmd = self.ordenes.get(c.inicio)
        return [c.texto] if cmd is None else unidades_comando(cmd)

    def nuevo(self, c: javascript.CadenaJs, traducciones: Mapping[str, str]) -> str | None:
        """El texto nuevo de la cadena, o None si no hay traducción o no es seguro usarla."""
        cmd = self.ordenes.get(c.inicio)
        if cmd is None:
            nuevo = traducciones.get(c.texto)
        else:
            nuevo = aplicar_comando(cmd, traducciones)
            if nuevo == c.texto:
                return None  # ninguna parte del mensaje tiene traducción
        return nuevo if nuevo is not None and _seguro(c, nuevo) else None


class ScriptsKubeJS:
    nombre = "Scripts de KubeJS"
    ambito = AMBITO

    def __init__(self, ctx: Contexto, exhaustivo: bool = False) -> None:
        """`exhaustivo`: traduce también toda cadena con aspecto de frase, aunque no se sepa dónde se muestra.

        Puede tocar lógica del script (una frase que se compara o se guarda), por eso es opcional.
        """
        self.ctx = ctx
        self.exhaustivo = exhaustivo
        self._scripts: list[_Script] = []
        self.sin_elegir: list[tuple[Path, list[str]]] = []
        #: Por script, los comandos de otros mods con una frase en inglés (no se tocan; van al informe)
        self.comandos_ajenos: list[tuple[Path, list[str]]] = []

    def _archivos(self) -> list[Path]:
        juego = self.ctx.instancia.juego
        return [p for c in CARPETAS if (juego / c).is_dir() for p in sorted((juego / c).rglob("*.js"))]

    def detectar(self) -> bool:
        return bool(self._archivos())

    def describir(self) -> str:
        return contar(len(self._archivos()), "script")

    def _leer(self) -> list[tuple[Path, str, list[javascript.CadenaJs]]]:
        leidos: list[tuple[Path, str, list[javascript.CadenaJs]]] = []
        for ruta in self._archivos():
            original = self.ctx.respaldo.original(ruta)
            if original is None:
                continue
            try:
                src = original.decode("utf-8")
                leidos.append((ruta, src, javascript.escanear(src)))
            except (ValueError, UnicodeDecodeError):
                self.ctx.registro(f"{ruta.name}: no pude leerlo con seguridad, se deja igual")
        return leidos

    def candidatas(self) -> list[tuple[Path, list[str]]]:
        """Por script, las frases que no se eligieron para traducir (para el informe de cobertura)."""
        self.recolectar()
        return self.sin_elegir

    def recolectar(self) -> list[Pieza]:
        self._scripts = []
        self.sin_elegir = []
        self.comandos_ajenos = []
        leidos = self._leer()
        llamadas = llamadas_de_texto(self.ctx.instancia.version.partes)  # las de esta versión de KubeJS
        patron = _llamadas_re(llamadas)
        flujos = [flujo_js.analizar(src, patron) for _, src, _ in leidos]
        # Una tabla de nombres se define en un archivo y se usa en otro
        tablas: frozenset[str] = frozenset(t for f in flujos for t in f.tablas)
        for (ruta, src, cadenas), flujo in zip(leidos, flujos, strict=True):
            elegidas: list[javascript.CadenaJs] = []
            en_comando: dict[int, comandos.Comando] = {}
            for c in cadenas:
                if es_texto_visible(c, llamadas):
                    elegidas.append(c)
                elif (cmd := comando_visible(c)) is not None:
                    elegidas.append(c)
                    en_comando[c.inicio] = cmd
            vistas = {c.inicio for c in elegidas}
            elegidas += [c for c in textos_armados(src, cadenas, flujo, tablas) if c.inicio not in vistas]
            propias = flujo_js.funciones_de_texto(src, cadenas, patron, lambda c: _es_sumidero(c, llamadas))
            if propias:  # funciones del propio script cuyo parámetro solo se muestra
                vistas = {c.inicio for c in elegidas}
                elegidas += [c for c in cadenas if c.inicio not in vistas and es_texto_de_funcion(c, propias)]
            if self.exhaustivo:
                vistas = {c.inicio for c in elegidas}
                elegidas += [
                    c for c in cadenas if c.inicio not in vistas and parece_frase_sin_elegir(c) and _plantilla_segura(c)
                ]
            if elegidas:
                self._scripts.append(_Script(ruta, src, cadenas, elegidas, en_comando))
            vistas = {c.inicio for c in elegidas}
            frases = [c.texto for c in cadenas if c.inicio not in vistas and parece_frase_sin_elegir(c)]
            if frases:
                self.sin_elegir.append((ruta, frases))
            ajenos = [c.texto for c in cadenas if c.inicio not in vistas and frase_en_comando_ajeno(c)]
            if ajenos:
                self.comandos_ajenos.append((ruta, ajenos))
        return [
            Pieza(t, f"script: {c.funcion or 'mensaje'}")
            for s in self._scripts
            for c in s.elegidas
            for t in s.unidades(c)
        ]

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        for s in self._scripts:
            nuevos = {c.inicio: n for c in s.elegidas if (n := s.nuevo(c, traducciones)) is not None}
            resumen.traducidos += len(nuevos)
            resumen.pendientes += len(s.elegidas) - len(nuevos)
            datos = javascript.reemplazar(s.src, s.cadenas, nuevos).encode("utf-8")
            actual = s.ruta.read_bytes() if s.ruta.is_file() else None
            if nuevos and actual != datos:
                self.ctx.respaldo.escribir(s.ruta, datos)
                resumen.archivos.append(s.ruta)
        return resumen

    def restaurar(self) -> list[Path]:
        return self.ctx.respaldo.restaurar("kubejs/")

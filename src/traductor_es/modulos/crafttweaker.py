"""Scripts de CraftTweaker (`scripts/*.zs`): tooltips, nombres y descripciones de JEI que el modpack escribe.

ZenScript se parece a JavaScript en lo que importa aquí (cadenas, llamadas, comentarios `//` y `/* */`), así que se
usa el mismo lector que para KubeJS. Lo único distinto son los comentarios con `#` (y las directivas como
`#priority`): se tapan con espacios antes de leer, para que un apóstrofo dentro de un comentario no parezca el
comienzo de una cadena. Las posiciones no cambian, así que el archivo se reescribe sobre el original.

Solo se traduce lo que se sabe que se muestra:
- `.addTooltip("…")`, `.addShiftTooltip("…")` y `.setDisplayName("…")`;
- `.displayName = "…"`;
- `mods.jei.JEI.addDescription(<…>, "…")` (1.12) y `mods.jei.JEI.addInfo(<…>, ["…"])` (1.16 y posteriores);
- `game.setLocalization("clave", "…")`: el segundo argumento, que es el texto.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..formatos import javascript
from .base import Contexto, Pieza, Resumen, contar, parece_clave
from .cambios import Lugar

AMBITO = "script"
CARPETA = "scripts"
#: Llamadas cuyo argumento de texto se ve en el juego.
LLAMADAS = frozenset({"addTooltip", "addShiftTooltip", "setDisplayName", "addDescription", "addInfo"})
_ASIGNACION_NOMBRE = re.compile(r"\.displayName\s*=\s*$")


def tapar_comentarios_almohadilla(src: str) -> str:
    """El código con cada comentario `#…` cambiado por espacios (mismo largo). No toca un `#` dentro de una cadena."""
    salida = list(src)
    comilla: str | None = None
    i = 0
    while i < len(src):
        c = src[i]
        if comilla:
            if c == "\\":
                i += 2
                continue
            if c == comilla:
                comilla = None
        elif c in "\"'":
            comilla = c
        elif c == "/" and src.startswith("//", i):  # el lector de JS ya entiende estos: se saltan enteros
            fin = src.find("\n", i)
            i = len(src) if fin < 0 else fin
            continue
        elif c == "/" and src.startswith("/*", i):
            fin = src.find("*/", i + 2)
            i = len(src) if fin < 0 else fin + 2
            continue
        elif c == "#":
            fin = src.find("\n", i)
            fin = len(src) if fin < 0 else fin
            salida[i:fin] = " " * (fin - i)
            i = fin
            continue
        i += 1
    return "".join(salida)


def es_texto_visible(src: str, c: javascript.CadenaJs) -> bool:
    """¿La cadena es un texto que el jugador ve?"""
    if c.comparada or not c.texto.strip() or parece_clave(c.texto):
        return False
    if c.funcion in LLAMADAS:
        return True
    if c.funcion == "setLocalization":
        return c.arg == 1  # el primero es la clave
    return c.funcion is None and bool(_ASIGNACION_NOMBRE.search(src[: c.inicio]))


@dataclass(slots=True)
class _Script:
    ruta: Path
    src: str
    cadenas: list[javascript.CadenaJs]
    elegidas: list[javascript.CadenaJs]


class ScriptsCraftTweaker:
    nombre = "Scripts de CraftTweaker"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._scripts: list[_Script] = []

    def _archivos(self) -> list[Path]:
        carpeta = self.ctx.instancia.juego / CARPETA
        return sorted(carpeta.rglob("*.zs")) if carpeta.is_dir() else []

    def detectar(self) -> bool:
        return bool(self._archivos())

    def describir(self) -> str:
        return contar(len(self._archivos()), "script de CraftTweaker", "scripts de CraftTweaker")

    def recolectar(self) -> list[Pieza]:
        self._scripts = []
        for ruta in self._archivos():
            original = self.ctx.respaldo.original(ruta)
            if original is None:
                continue
            try:
                src = original.decode("utf-8")
                cadenas = javascript.escanear(tapar_comentarios_almohadilla(src))
            except (ValueError, UnicodeDecodeError):
                self.ctx.registro(f"{ruta.name}: no pude leerlo con seguridad, se deja igual")
                continue
            elegidas = [c for c in cadenas if es_texto_visible(src, c)]
            if elegidas:
                self._scripts.append(_Script(ruta, src, cadenas, elegidas))
        return [
            Pieza(c.texto, f"script de CraftTweaker: {c.funcion or 'nombre'}")
            for s in self._scripts
            for c in s.elegidas
        ]

    def lugares(self) -> list[Lugar]:
        juego = self.ctx.instancia.juego
        return [Lugar(s.ruta.relative_to(juego).as_posix(), [c.texto for c in s.elegidas]) for s in self._scripts]

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        for s in self._scripts:
            nuevos = {c.inicio: traducciones[c.texto] for c in s.elegidas if c.texto in traducciones}
            resumen.traducidos += len(nuevos)
            resumen.pendientes += len(s.elegidas) - len(nuevos)
            datos = javascript.reemplazar(s.src, s.cadenas, nuevos).encode("utf-8")
            actual = s.ruta.read_bytes() if s.ruta.is_file() else None
            if nuevos and actual != datos:
                self.ctx.respaldo.escribir(s.ruta, datos)
                resumen.archivos.append(s.ruta)
        return resumen

    def restaurar(self) -> list[Path]:
        return self.ctx.respaldo.restaurar(f"{CARPETA}/")

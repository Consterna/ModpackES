"""Textos de idioma de mods, KubeJS y resource packs: van al resource pack, para todas las variantes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ..fuentes.recursos import Pendiente
from .base import Contexto, Pieza, Resumen, con_vecindad, contar
from .cambios import Lugar

AMBITO = "ui"
#: Solo los nombres de cosas van al glosario. Textos de controles o menús («Right», «All») no son términos:
#: mandarlos como glosario confundiría al modelo en frases normales («That's right»).
_CLAVES_DE_NOMBRES = (
    "item.",
    "block.",
    "entity.",
    "effect.",
    "enchantment.",
    "biome.",
    "fluid.",
    "fluid_type.",
    "painting.",
    "trim_material.",
    "trim_pattern.",
    "attribute.name.",
    "jukebox_song.",
)


#: (prefijo o sufijo de la clave, qué es) en orden: lo primero que coincide manda.
_TIPOS_POR_SUFIJO = (((".desc", ".description", ".tooltip", ".info", ".lore"), "descripción o tooltip de un objeto"),)
_TIPOS_POR_PREFIJO = (
    ("item.", "nombre de un objeto"),
    ("block.", "nombre de un bloque"),
    ("entity.", "nombre de una criatura o entidad"),
    ("effect.", "nombre de un efecto de poción"),
    ("enchantment.", "nombre de un encantamiento"),
    ("biome.", "nombre de un bioma"),
    ("fluid", "nombre de un fluido"),
    ("jukebox_song.", "nombre de un disco de música"),
    ("advancements.", "logro"),
    ("subtitles.", "subtítulo de un sonido"),
    ("key.", "nombre de una tecla o categoría de controles"),
    ("death.", "mensaje de muerte"),
    ("commands.", "mensaje de un comando"),
    ("container.", "título de un menú o contenedor"),
    ("gui.", "texto de la interfaz"),
    ("screen.", "texto de una pantalla"),
    ("itemgroup.", "pestaña del inventario creativo"),
    ("creativetab.", "pestaña del inventario creativo"),
    ("tooltip.", "tooltip"),
    ("message.", "mensaje al jugador"),
    ("config.", "opción de configuración"),
    ("options.", "opción de configuración"),
    ("jei.", "texto de JEI/REI/EMI (recetas)"),
    ("emi.", "texto de JEI/REI/EMI (recetas)"),
    ("rei.", "texto de JEI/REI/EMI (recetas)"),
)


def tipo_de_clave(clave: str) -> str:
    """Qué es el texto según su clave («nombre de un objeto», «tooltip»…); vacío si no se sabe."""
    bajo = clave.lower()
    for sufijos, tipo in _TIPOS_POR_SUFIJO:
        if bajo.endswith(sufijos):
            return tipo
    if bajo.startswith("item.") and any(m in bajo for m in ("music_disc", "record")):
        return "nombre de un disco de música"
    if ".ponder." in f".{bajo}":  # «create.ponder.fan_direction.text_1»: las escenas animadas de Create
        return "texto de una escena de Ponder (tutorial animado de Create): frase corta que explica lo que se ve"
    return next((tipo for prefijo, tipo in _TIPOS_POR_PREFIJO if bajo.startswith(prefijo)), "")


def es_nombre(clave: str) -> bool:
    """La clave es el nombre de un objeto, bloque, criatura… (y no una descripción o un tooltip)."""
    return clave.startswith(_CLAVES_DE_NOMBRES) and not clave.endswith((".desc", ".description", ".tooltip", ".info"))


#: Hasta cuántos caracteres de un texto vecino van en la pista, y cuántas claves hermanas.
_LARGO_EN_PISTA = 60
_HERMANAS = 2
#: Un texto de menú de hasta estas palabras («Left», «Mode») es ambiguo sin sus hermanas.
_PALABRAS_CORTO = 3
_PREFIJOS_DE_MENU = ("gui.", "key.", "screen.", "container.", "config.", "options.", "button.", "tooltip.")
_SUFIJOS_DE_DESCRIPCION = (".desc", ".description", ".tooltip", ".info", ".lore")


def _corto(texto: str) -> str:
    plano = " ".join(texto.split())
    return plano if len(plano) <= _LARGO_EN_PISTA else plano[: _LARGO_EN_PISTA - 1] + "…"


def _nombre_del_objeto(clave: str, textos: Mapping[str, str]) -> str | None:
    """El nombre del objeto o bloque del que habla una descripción: «item.m.wrench.tooltip.0» → «item.m.wrench»;
    «tooltip.m.wrench» → «item.m.wrench» o «block.m.wrench»."""
    partes = clave.split(".")
    for i in range(len(partes) - 1, 1, -1):
        candidata = ".".join(partes[:i])
        if candidata != clave and es_nombre(candidata) and textos.get(candidata):
            return textos[candidata]
    if partes[0] in ("tooltip", "desc", "description") and len(partes) >= 3:
        for prefijo in ("item", "block"):
            for i in range(len(partes), 2, -1):
                candidata = ".".join((prefijo, *partes[1:i]))
                if textos.get(candidata):
                    return textos[candidata]
    return None


def _hermanas(clave: str, textos: Mapping[str, str]) -> list[str]:
    """Los textos de las claves vecinas en el archivo con el mismo padre («gui.m.mode.left» junto a
    «gui.m.mode.right»): la de antes y la de después."""
    padre = clave.rsplit(".", 1)[0] + "."
    claves = list(textos)
    if clave not in textos:
        return []
    i = claves.index(clave)
    vecinas = [k for k in (claves[i - 1] if i else None, claves[i + 1] if i + 1 < len(claves) else None) if k]
    return [
        _corto(textos[k]) for k in vecinas if k.startswith(padre) and "." not in k[len(padre) :] and textos[k].strip()
    ][:_HERMANAS]


def textos_del_juego(ingles: Mapping[str, str], traducido: Mapping[str, str]) -> dict[str, str]:
    """{inglés: español} de los textos del juego que no son nombres y tienen una sola traducción («Done» → «Listo»)."""
    vistos: dict[str, set[str]] = {}
    for clave, en in ingles.items():
        es = traducido.get(clave)
        if es is not None and en.strip() and es.strip() and en != es and not es_nombre(clave):
            vistos.setdefault(en.strip(), set()).add(es.strip())
    return {en: next(iter(es)) for en, es in vistos.items() if len(es) == 1}


def pista_con_contexto(
    namespace: str, clave: str, textos: Mapping[str, str], juego: Mapping[str, str] | None = None
) -> str:
    """La pista de `Mods.pista` y, si ayuda a elegir el sentido, un poco de contexto barato:

    - una descripción o tooltip lleva el nombre de su objeto («de «Llave inglesa»»);
    - un texto corto de un menú lleva una o dos claves hermanas («junto a «Right»»);
    - si el inglés es igual a un texto del juego, cómo lo dice el juego («en el juego: «Listo»»).
    """
    partes = [Mods.pista(namespace, clave)]
    ingles = textos.get(clave, "")
    bajo = clave.lower()
    if not es_nombre(clave) and (bajo.endswith(_SUFIJOS_DE_DESCRIPCION) or bajo.split(".")[0] in ("tooltip", "desc")):
        if (nombre := _nombre_del_objeto(clave, textos)) is not None:
            partes.append(f"habla de «{_corto(nombre)}»")
    elif (
        bajo.startswith(_PREFIJOS_DE_MENU)
        and 0 < len(ingles.split()) <= _PALABRAS_CORTO
        and (hermanas := _hermanas(clave, textos))
    ):
        partes.append("junto a " + ", ".join(f"«{h}»" for h in hermanas))
    if juego and (del_juego := juego.get(ingles.strip())):
        partes.append(f"en el juego: «{_corto(del_juego)}»")
    return " · ".join(partes)


#: Ámbito de los textos de libros que viven en los archivos de idioma (Patchouli con `i18n`, Modonomicon…).
AMBITO_LIBRO = "libro"
#: Una clave de libro tiene uno de estos tramos («mysticalagriculture.guide.entry…», «occultism.book.…»).
_CLAVE_DE_LIBRO = re.compile(r"(^|[._])(book|books|guide|guidebook|lexicon|codex|journal|manual)([._]|$)", re.I)
_NO_ES_LIBRO = ("options.", "config.", "key.", "gui.", "tooltip.", "item.", "block.", "itemgroup.", "creativetab.")
#: Un texto de libro de hasta estas palabras y sin punto final es un título (de entrada, de página o de categoría).
_PALABRAS_TITULO = 6


def es_clave_de_libro(clave: str) -> bool:
    """¿La clave es texto de un libro guía («occultism.book.entries.ritual.page1»)? No los nombres de objetos ni los
    textos de menús o tooltips («item.m.guide_book», «gui.m.book_title»)."""
    bajo = clave.lower()
    return bool(_CLAVE_DE_LIBRO.search(bajo)) and not bajo.startswith(_NO_ES_LIBRO) and not es_nombre(clave)


def _es_titulo_de_libro(p: Pieza, clave: str) -> bool:
    texto = p.texto.strip()
    return clave.lower().endswith((".name", ".title", ".category")) or (
        len(texto.split()) <= _PALABRAS_TITULO and not texto.endswith((".", "!", "?", ":"))
    )


def _salto_nuevo(original: str, traduccion: str) -> bool:
    return any(c in traduccion and c not in original for c in ("\r", "\n"))


class Mods:
    nombre = "Textos de mods (objetos, bloques, menús)"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._pendientes: list[Pendiente] = []
        self._ambitos: dict[str, str] = {}  #: texto → ámbito, para los que no son de interfaz

    def detectar(self) -> bool:
        return True

    def describir(self) -> str:
        return contar(len(self.ctx.instancia.jars()), "mod")

    def recolectar(self) -> list[Pieza]:
        tabla = self.ctx.instancia.tabla_idiomas()
        preferidas = (self.ctx.dialecto, *(v for v in ("es_mx", "es_es") if v != self.ctx.dialecto))
        self._pendientes = tabla.pendientes(self.ctx.variantes, preferidas)
        copiados = sum(1 for p in self._pendientes if p.existente is not None)
        if copiados:
            self.ctx.registro(f"{copiados} textos se copian de otra variante de español, sin gastar")
        juego = textos_del_juego(tabla.textos("minecraft", "en_us"), tabla.textos("minecraft", self.ctx.dialecto))
        por_mod: dict[str, Mapping[str, str]] = {}
        piezas: list[Pieza] = []
        # Los libros guía de los archivos de idioma van como libro, con el título y el texto anterior (por libro)
        libros: dict[str, list[tuple[Pieza, str]]] = {}
        for p in self._pendientes:
            if p.existente is None:
                textos = por_mod.get(p.namespace)
                if textos is None:
                    textos = por_mod[p.namespace] = tabla.textos(p.namespace, "en_us")
                if es_clave_de_libro(p.clave):
                    libros.setdefault(p.namespace, []).append((Pieza(p.ingles, f"{p.namespace}: {p.clave}"), p.clave))
                else:
                    piezas.append(Pieza(p.ingles, pista_con_contexto(p.namespace, p.clave, textos, juego)))
        self._ambitos = {}
        for del_libro in libros.values():
            claves = {id(pieza): clave for pieza, clave in del_libro}
            con_contexto = con_vecindad(
                [pieza for pieza, _ in del_libro],
                lambda q, claves=claves: _es_titulo_de_libro(q, claves.get(id(q), "")),
            )
            for pieza in con_contexto:
                piezas.append(Pieza(pieza.texto, pieza.pista, AMBITO_LIBRO))
                self._ambitos[pieza.texto] = AMBITO_LIBRO
        return piezas

    def ambito_de(self, texto: str) -> str:
        """El ámbito de un texto que juntó `recolectar` («libro» para los libros guía; si no, interfaz)."""
        return self._ambitos.get(texto, AMBITO)

    def lugares(self) -> list[Lugar]:
        """Por mod (espacio de nombres), {clave: inglés} de lo que la app traduce (tras `recolectar`)."""
        por_mod: dict[str, dict[str, str]] = {}
        for p in self._pendientes:
            if p.existente is None:
                por_mod.setdefault(p.namespace, {})[p.clave] = p.ingles
        return [Lugar(ns, textos) for ns, textos in sorted(por_mod.items())]

    @staticmethod
    def pista(namespace: str, clave: str) -> str:
        """«mod: clave · tipo»: de dónde sale el texto y qué es, para elegir el sentido correcto."""
        tipo = tipo_de_clave(clave)
        return f"{namespace}: {clave} · {tipo}" if tipo else f"{namespace}: {clave}"

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        por_archivo: dict[tuple[str, str], dict[str, str]] = {}
        for p in self._pendientes:
            texto = p.existente if p.existente is not None else traducciones.get(p.ingles)
            if texto is not None and self.ctx.instancia.legacy and _salto_nuevo(p.ingles, texto):
                texto = None  # un .lang no puede guardar saltos de línea reales: se queda en inglés
            if texto is None:
                resumen.pendientes += 1
                continue
            if p.existente is None:
                resumen.traducidos += 1
            for variante in p.faltan:
                por_archivo.setdefault((p.namespace, variante), {})[p.clave] = texto
        if (
            not por_archivo
            and self.ctx.pack is None
            and not (self.ctx.instancia.juego / "resourcepacks" / "Traduccion_ES").is_dir()
        ):
            return resumen  # nada que escribir y nada viejo que vaciar: no se crea un pack vacío
        pack = self.ctx.pack_listo()
        for (namespace, variante), textos in sorted(por_archivo.items()):
            try:
                resumen.archivos.append(pack.escribir_lang(namespace, variante, textos))
            except ValueError:  # un mod con un espacio de nombres imposible de guardar no detiene a los demás
                self.ctx.registro(
                    f"El espacio de nombres «{namespace}» no se puede guardar en el pack: se deja en inglés"
                )
                resumen.pendientes += len(textos)
        pack.vaciar_idiomas_viejos()
        return resumen

    def nombres(self, traducciones: Mapping[str, str]) -> dict[str, str]:
        """{inglés: traducción} de los nombres de objetos, bloques… recién traducidos (para el glosario)."""
        return {
            p.ingles: traducciones[p.ingles]
            for p in self._pendientes
            if p.existente is None and p.ingles in traducciones and es_nombre(p.clave)
        }

    def restaurar(self) -> list[Path]:
        return []  # no toca la instancia: basta con desactivar el resource pack

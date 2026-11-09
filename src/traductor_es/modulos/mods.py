"""Textos de idioma de mods, KubeJS y resource packs: van al resource pack, para todas las variantes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..fuentes.recursos import Pendiente
from .base import Contexto, Pieza, Resumen, contar

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


def es_nombre(clave: str) -> bool:
    """La clave es el nombre de un objeto, bloque, criatura… (y no una descripción o un tooltip)."""
    return clave.startswith(_CLAVES_DE_NOMBRES) and not clave.endswith((".desc", ".description", ".tooltip", ".info"))


def _salto_nuevo(original: str, traduccion: str) -> bool:
    return any(c in traduccion and c not in original for c in ("\r", "\n"))


class Mods:
    nombre = "Textos de mods (objetos, bloques, menús)"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._pendientes: list[Pendiente] = []

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
        return [Pieza(p.ingles, f"{p.namespace}: {p.clave}") for p in self._pendientes if p.existente is None]

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

"""Qué cambió en el inglés del modpack desde la última traducción.

Al traducir se guarda en la marca del resource pack un índice: por cada módulo y cada lugar (un mod, un archivo de
misiones, un libro, un script…) un hash corto de cada texto en inglés. Al volver a analizar se compara con lo que
hay ahora y se dice qué es nuevo, qué cambió y qué ya no está, con el costo de traducir solo esa diferencia.

Hay dos clases de lugar:
- con claves (los textos de un mod: `item.x.wrench`): se compara clave por clave;
- en orden (un archivo de misiones, un libro, un script): no hay claves estables, así que se comparan las listas de
  textos con `difflib`; un texto reemplazado en su sitio cuenta como cambiado, uno agregado como nuevo.

Solo lee: este módulo no escribe nada.
"""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

#: Versión del formato del índice. Si cambia, un índice viejo se ignora (se compara con la memoria).
VERSION_INDICE = 1
#: Orden de los grupos en el informe: el mismo que en el resto de la app.
_ORDEN_GRUPOS = {"mods": 0, "java": 1, "libros": 2, "misiones": 3, "scripts": 4}
#: Cuántas claves o textos de ejemplo se muestran por lugar.
MAX_EJEMPLOS = 5

#: {clave: hash} para un lugar con claves, [hash, …] para uno en orden.
HuellaLugar = dict[str, str] | list[str]
#: {nombre del módulo: {"grupo": …, "lugares": {lugar: huella}}}
Indice = dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Lugar:
    """Los textos en inglés de un lugar: con claves ({clave: texto}) o en orden (lista de textos)."""

    donde: str
    textos: Mapping[str, str] | Sequence[str]


def huella(texto: str) -> str:
    """Hash corto del texto: 12 cifras hexadecimales bastan para distinguir los textos de un modpack."""
    return hashlib.blake2b(texto.encode("utf-8"), digest_size=6).hexdigest()


def huella_de(lugar: Lugar) -> HuellaLugar:
    if isinstance(lugar.textos, Mapping):
        return {clave: huella(texto) for clave, texto in sorted(lugar.textos.items())}
    return [huella(t) for t in lugar.textos]


def indice_de(modulos: Iterable[tuple[str, str, list[Lugar]]]) -> Indice:
    """Índice de (grupo, nombre del módulo, lugares). Si un lugar se repite en un módulo, vale el primero."""
    indice: Indice = {}
    for grupo, nombre, lugares in modulos:
        entrada = indice.setdefault(nombre, {"grupo": grupo, "lugares": {}})
        for lugar in lugares:
            entrada["lugares"].setdefault(lugar.donde, huella_de(lugar))
    return indice


def mezclar(anterior: Indice | None, nuevo: Indice, grupos: Iterable[str]) -> Indice:
    """El índice nuevo, con lo del anterior que esta ejecución no volvió a mirar (otros grupos).

    De los grupos que sí se tradujeron se queda solo lo nuevo: un módulo que ya no está desaparece del índice.
    """
    vistos = set(grupos)
    mezcla = {nombre: e for nombre, e in (anterior or {}).items() if e.get("grupo") not in vistos}
    mezcla.update(nuevo)
    return mezcla


def leer_indice(marca: Mapping[str, Any]) -> tuple[Indice, str] | None:
    """(índice, fecha) guardados en la marca del pack, o None si no hay o es de otro formato."""
    datos = marca.get("indice")
    if not isinstance(datos, dict):
        return None
    datos = cast(dict[str, Any], datos)
    modulos = datos.get("modulos")
    if datos.get("version") != VERSION_INDICE or not isinstance(modulos, dict):
        return None
    limpio: Indice = {}
    for nombre, entrada in cast(dict[Any, Any], modulos).items():
        if isinstance(entrada, dict) and isinstance(cast(dict[str, Any], entrada).get("lugares"), dict):
            limpio[str(nombre)] = cast(dict[str, Any], entrada)
    return limpio, str(datos.get("fecha", ""))


def para_la_marca(indice: Indice, fecha: str) -> dict[str, Any]:
    return {"version": VERSION_INDICE, "fecha": fecha, "modulos": indice}


# ---------------------------------------------------------------------- comparación


@dataclass(slots=True)
class CambiosLugar:
    """Lo que cambió en un lugar. `nuevas` y `cambiadas` son claves (o los textos, si el lugar va en orden)."""

    grupo: str
    modulo: str
    donde: str
    nuevas: list[str] = field(default_factory=list[str])
    cambiadas: list[str] = field(default_factory=list[str])
    borradas: list[str] = field(default_factory=list[str])  #: claves; vacío si el lugar va en orden
    cantidad_borradas: int = 0
    #: Textos en inglés que habría que traducir (los nuevos y los que cambiaron)
    textos: list[str] = field(default_factory=list[str])

    @property
    def vacio(self) -> bool:
        return not (self.nuevas or self.cambiadas or self.cantidad_borradas)

    def __str__(self) -> str:
        partes: list[str] = []
        for nombre, lista, n in (
            ("nuevas", self.nuevas, len(self.nuevas)),
            ("cambiadas", self.cambiadas, len(self.cambiadas)),
            ("borradas", self.borradas, self.cantidad_borradas),
        ):
            if not n:
                continue
            ejemplos = ", ".join(_corto(x) for x in lista[:MAX_EJEMPLOS])
            mas = f" y {n - MAX_EJEMPLOS} más" if n > MAX_EJEMPLOS and ejemplos else ""
            partes.append(f"{n} {nombre}" + (f" ({ejemplos}{mas})" if ejemplos else ""))
        return f"{self.donde}: " + "; ".join(partes)


def _corto(texto: str, largo: int = 50) -> str:
    plano = " ".join(texto.split())
    return plano if len(plano) <= largo else plano[: largo - 1] + "…"


def _comparar_claves(c: CambiosLugar, antes: Mapping[str, Any], ahora: Mapping[str, str]) -> None:
    for clave, texto in ahora.items():
        previo = antes.get(clave)
        if previo is None:
            c.nuevas.append(clave)
            c.textos.append(texto)
        elif previo != huella(texto):
            c.cambiadas.append(clave)
            c.textos.append(texto)
    c.borradas = sorted(k for k in antes if k not in ahora)
    c.cantidad_borradas = len(c.borradas)


def _comparar_orden(c: CambiosLugar, antes: Sequence[Any], ahora: Sequence[str]) -> None:
    previos = [str(h) for h in antes]
    actuales = [huella(t) for t in ahora]
    comparador = difflib.SequenceMatcher(None, previos, actuales, autojunk=False)
    for op, i1, i2, j1, j2 in comparador.get_opcodes():
        if op == "equal":
            continue
        pares = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for j in range(j1, j2):
            (c.cambiadas if j - j1 < pares else c.nuevas).append(ahora[j])
            c.textos.append(ahora[j])
        c.cantidad_borradas += (i2 - i1) - pares


def comparar(anterior: Indice, actuales: Iterable[tuple[str, str, list[Lugar]]]) -> list[CambiosLugar]:
    """Por cada lugar con algún cambio: claves nuevas, cambiadas y borradas, y los textos a traducir."""
    salida: list[CambiosLugar] = []
    vistos: set[str] = set()
    for grupo, nombre, lugares in actuales:
        vistos.add(nombre)
        previos: dict[str, Any] = anterior.get(nombre, {}).get("lugares", {})
        en_este: set[str] = set()
        for lugar in lugares:
            if lugar.donde in en_este:
                continue
            en_este.add(lugar.donde)
            c = CambiosLugar(grupo, nombre, lugar.donde)
            antes = previos.get(lugar.donde)
            if isinstance(lugar.textos, Mapping):
                _comparar_claves(c, cast(dict[str, Any], antes) if isinstance(antes, dict) else {}, lugar.textos)
            else:
                _comparar_orden(c, cast(list[Any], antes) if isinstance(antes, list) else [], lugar.textos)
            if not c.vacio:
                salida.append(c)
        salida += [_todo_borrado(grupo, nombre, d, h) for d, h in previos.items() if d not in en_este]
    for nombre, entrada in anterior.items():
        if nombre not in vistos:  # el módulo entero ya no está (p. ej. se quitaron las misiones)
            grupo = str(entrada.get("grupo", ""))
            salida += [_todo_borrado(grupo, nombre, d, h) for d, h in entrada.get("lugares", {}).items()]
    return [c for c in salida if not c.vacio]


def _todo_borrado(grupo: str, modulo: str, donde: str, previo: Any) -> CambiosLugar:
    c = CambiosLugar(grupo, modulo, str(donde))
    if isinstance(previo, dict):
        c.borradas = sorted(str(k) for k in cast(dict[Any, Any], previo))
        c.cantidad_borradas = len(c.borradas)
    elif isinstance(previo, list):
        c.cantidad_borradas = len(cast(list[Any], previo))
    return c


def sin_indice(
    actuales: Iterable[tuple[str, str, list[Lugar]]], pendiente: Callable[[str, str], bool]
) -> list[CambiosLugar]:
    """Sin índice anterior: cuenta como nuevo cada texto que todavía no tiene traducción.

    `pendiente(módulo, texto)` dice si el texto falta (no está en la memoria ni en el glosario).
    No se pueden saber cambiadas ni borradas.
    """
    salida: list[CambiosLugar] = []
    for grupo, nombre, lugares in actuales:
        for lugar in lugares:
            c = CambiosLugar(grupo, nombre, lugar.donde)
            pares = lugar.textos.items() if isinstance(lugar.textos, Mapping) else ((t, t) for t in lugar.textos)
            for etiqueta, texto in pares:
                if pendiente(nombre, texto):
                    c.nuevas.append(etiqueta)
                    c.textos.append(texto)
            if not c.vacio:
                salida.append(c)
    return salida


@dataclass(slots=True)
class Cambios:
    """El informe «qué cambió desde la última traducción»."""

    lugares: list[CambiosLugar] = field(default_factory=list[CambiosLugar])
    #: «indice» si se comparó con la última traducción, «memoria» si no había índice y se usó la memoria
    base: str = "indice"
    fecha: str = ""  #: fecha de la última traducción (si hay índice)

    @property
    def nuevas(self) -> int:
        return sum(len(c.nuevas) for c in self.lugares)

    @property
    def cambiadas(self) -> int:
        return sum(len(c.cambiadas) for c in self.lugares)

    @property
    def borradas(self) -> int:
        return sum(c.cantidad_borradas for c in self.lugares)

    def resumen(self) -> str:
        """Una línea: «Desde la última traducción (fecha): 3 nuevas, 1 cambiada, 2 borradas.»"""
        if self.base == "memoria":
            inicio = "Sin índice de una traducción anterior (se compara con la memoria)"
        else:
            inicio = "Desde la última traducción" + (f" ({self.fecha[:10]})" if self.fecha else "")
        if not self.lugares:
            return f"{inicio}: no cambió nada."
        return f"{inicio}: {self.nuevas} nuevas, {self.cambiadas} cambiadas, {self.borradas} borradas."

    def texto(self) -> str:
        """El detalle por grupo y por lugar, para leer en la consola."""
        lineas = [self.resumen()]
        grupo_actual = None
        for c in sorted(self.lugares, key=lambda c: (_ORDEN_GRUPOS.get(c.grupo, 9), c.modulo, c.donde)):
            if (c.grupo, c.modulo) != grupo_actual:
                grupo_actual = (c.grupo, c.modulo)
                lineas.append(f"== {c.modulo} ==")
            lineas.append(f"  {c}")
        return "\n".join(lineas)

    def en_json(self) -> list[dict[str, Any]]:
        return [
            {
                "grupo": c.grupo,
                "modulo": c.modulo,
                "donde": c.donde,
                "nuevas": c.nuevas,
                "cambiadas": c.cambiadas,
                "borradas": c.borradas,
                "cantidad_borradas": c.cantidad_borradas,
            }
            for c in self.lugares
        ]


__all__ = [
    "Cambios",
    "CambiosLugar",
    "Lugar",
    "comparar",
    "huella",
    "indice_de",
    "leer_indice",
    "mezclar",
    "para_la_marca",
    "sin_indice",
]

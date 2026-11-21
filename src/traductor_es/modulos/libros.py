"""Libros guía: Patchouli, Mantle (Tinkers), Citadel (Alex's Mobs), GuideME (AE2) y Lavender.

Todos buscan primero el archivo en el idioma del juego y, si no está, usan el inglés archivo por archivo
(comprobado en el código de cada mod). Por eso se escriben solo los archivos que faltan en cada variante.
Modonomicon y los libros de Patchouli con `i18n` usan claves de idioma: los traduce el módulo de mods, con
el ámbito de libro (ver `mods.es_clave_de_libro`).
"""

from __future__ import annotations

import json
import re
import textwrap
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..formatos import json_cadenas, markdown
from ..fuentes.contenedores import Carpeta
from ..fuentes.recursos import Fuente
from ..nucleo.mascara import es_traducible
from .base import Contexto, Pieza, Resumen, aplicar, con_vecindad, parece_clave, piezas_de
from .cambios import Lugar

AMBITO = "libro"
CAMPOS_PATCHOULI = frozenset(
    {"name", "description", "text", "title", "subtitle", "landing_text", "link_text", "header"}
)
CAMPOS_MANTLE = frozenset({"text", "title", "subText", "effects", "properties", "description"})
_IDIOMA = re.compile(r"[a-z]{2,3}_[a-z]{2,4}")
_PATCHOULI = re.compile(r"assets/([^/]+)/patchouli_books/([^/]+)/([^/]+)/(.+\.json)")
_PATCHOULI_DATA = re.compile(r"data/([^/]+)/patchouli_books/([^/]+)/en_us/.+\.json")
_BOOK = re.compile(r"assets/([^/]+)/book/([^/]+)/([^/]+)/(.+\.(?:json|txt))")
_LAVENDER = re.compile(r"assets/([^/]+)/lavender/(entries|categories)/([^/]+)/(.+\.md)")
_GUIA = re.compile(r"assets/([^/]+)/([^/]+)/(.+\.md)")
_NO_GUIA = frozenset({"lavender", "patchouli_books", "book", "lang"})
_PREFERIDAS = ("es_mx", "es_es")
#: Componentes de una plantilla de Patchouli que muestran texto, y su campo (`BookTemplate.registerComponent`)
_COMPONENTES_DE_TEXTO = {"patchouli:text": "text", "patchouli:header": "text", "patchouli:tooltip": "tooltip"}
#: Una variable que es el valor entero del campo («#heading» o «#heading#»): el texto de la página se ve tal cual
_VARIABLE_ENTERA = re.compile(r"#([\w.]+)#?")
AMBITO_PLANTILLA = "ui"
_CABECERA_GUIDEME = re.compile(rb"\A\s*---\s*\n(?:.*\n)*?\s*(?:navigation|item_ids)\s*:", re.MULTILINE)


@dataclass(slots=True)
class _Archivo:
    sistema: str
    ingles: bytes
    destino: Callable[[str], str]  #: variante → ruta relativa (al pack, o a la instancia si `externo`)
    existentes: dict[str, bytes] = field(default_factory=dict[str, bytes])
    externo: bool = False
    piezas: list[Pieza] = field(default_factory=list[Pieza])
    generar: Callable[[Mapping[str, str]], tuple[bytes, int, int]] | None = None
    libro: tuple[str, str] | None = None  #: (espacio, libro) de una entrada de Patchouli, para buscar sus plantillas


def variables_de_texto(plantillas: Mapping[str, Any], tipo: str, visitadas: frozenset[str] = frozenset()) -> set[str]:
    """Los campos de una página con esa plantilla que Patchouli muestra como texto.

    Una variable cuenta si es el valor entero de un componente de texto, encabezado o tooltip. Las de una plantilla
    incluida se nombran «<as>.<variable>», salvo que `using` las ate a otra variable o a un valor fijo
    (`TemplateInclusion.qualifyName`). Una variable dentro de una frase («Cost: #syphon# LP») suele ser un número o un
    dato técnico: no cuenta.
    """
    datos = plantillas.get(tipo)
    if not isinstance(datos, dict) or tipo in visitadas:
        return set()
    plantilla: dict[str, Any] = datos  # pyright: ignore[reportUnknownVariableType]
    variables: set[str] = set()
    for comp in _lista(plantilla.get("components")):
        campo = _COMPONENTES_DE_TEXTO.get(str(comp.get("type")))
        valor = comp.get(campo) if campo else None
        for v in valor if isinstance(valor, list) else [valor]:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(v, str) and (m := _VARIABLE_ENTERA.fullmatch(v)):
                variables.add(m.group(1))
    espacio = tipo.split(":", 1)[0]
    for inc in _lista(plantilla.get("include")):
        hija, como, using = inc.get("template"), inc.get("as"), inc.get("using")
        if not isinstance(hija, str) or not isinstance(como, str):
            continue
        atadas: dict[str, Any] = using if isinstance(using, dict) else {}  # pyright: ignore[reportUnknownVariableType]
        for v in variables_de_texto(plantillas, hija if ":" in hija else f"{espacio}:{hija}", visitadas | {tipo}):
            atada = atadas.get(v)
            if atada is None:
                variables.add(f"{como}.{v}")
            elif isinstance(atada, str) and atada.startswith("#"):
                variables.add(atada[1:])
    return variables


def _lista(valor: object) -> list[dict[str, Any]]:
    """Los objetos de una lista JSON (lo demás se ignora)."""
    return [x for x in valor if isinstance(x, dict)] if isinstance(valor, list) else []  # pyright: ignore[reportUnknownVariableType]


def _fuentes_ordenadas(fuentes: list[Fuente]) -> Iterator[tuple[str, Callable[[], bytes]]]:
    """(ruta, lector) de todas las fuentes, de menor a mayor prioridad (la última que aparece manda)."""
    for f in sorted(fuentes, key=lambda f: f.prioridad):
        c = f.contenedor
        for nombre in c.nombres():
            if nombre.endswith((".json", ".txt", ".md")) and nombre.startswith("assets/"):
                yield nombre, (lambda c=c, n=nombre: c.leer(n))


class Libros:
    nombre = "Libros guía"
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._idiomas = frozenset({"en_us", *ctx.variantes})
        self._archivos: list[_Archivo] = []
        self._grupos: dict[tuple[str, ...], dict[str, bytes]] | None = None
        #: Plantillas de Patchouli en inglés por libro: {libro: {"espacio:ruta": plantilla}}
        self._plantillas: dict[str, dict[str, Any]] = {}
        self._ambitos: dict[str, str] = {}
        self.sin_traducir_posible: list[str] = []  #: libros de Patchouli antiguos (texto en data/, dentro del jar)

    # ------------------------------------------------------------------ búsqueda
    def _agrupar(self) -> dict[tuple[str, ...], dict[str, bytes]]:
        """{(sistema, ...clave del archivo): {idioma: contenido}} con la versión que ve el juego (se lee una vez)."""
        if self._grupos is None:
            self._grupos = self._leer_grupos()
        return self._grupos

    def _leer_grupos(self) -> dict[tuple[str, ...], dict[str, bytes]]:
        grupos: dict[tuple[str, ...], dict[str, bytes]] = {}
        datos_viejos: set[str] = set()
        self._plantillas = {}
        for nombre, leer in _fuentes_ordenadas(self.ctx.instancia.fuentes()):
            clave: tuple[str, ...] | None = None
            idioma = ""
            if m := _PATCHOULI.fullmatch(nombre):
                if m.group(4).startswith("templates/"):
                    if m.group(3) == "en_us":  # Patchouli usa la del idioma del juego o, si no está, la inglesa
                        self._leer_plantilla(m.group(2), f"{m.group(1)}:{m.group(4)[10:-5]}", leer)
                    continue
                clave, idioma = ("patchouli", m.group(1), m.group(2), m.group(4)), m.group(3)
            elif m := _BOOK.fullmatch(nombre):
                sistema = "citadel" if nombre.endswith(".txt") else "mantle"
                clave, idioma = (sistema, m.group(1), m.group(2), m.group(4)), m.group(3)
            elif m := _LAVENDER.fullmatch(nombre):
                resto = m.group(4).split("/", 1)
                if len(resto) == 2 and _IDIOMA.fullmatch(resto[0]):
                    clave, idioma = ("lavender", m.group(1), m.group(2), m.group(3), resto[1]), resto[0]
                else:
                    clave, idioma = ("lavender", m.group(1), m.group(2), m.group(3), m.group(4)), "en_us"
            elif (m := _GUIA.fullmatch(nombre)) and m.group(2) not in _NO_GUIA:
                resto = m.group(3).split("/", 1)
                if len(resto) == 2 and resto[0].startswith("_") and _IDIOMA.fullmatch(resto[0][1:]):
                    clave, idioma = ("guideme", m.group(1), m.group(2), resto[1]), resto[0][1:]
                else:
                    clave, idioma = ("guideme", m.group(1), m.group(2), m.group(3)), "en_us"
            # Solo hacen falta el inglés y el español: los demás idiomas no se leen
            if clave is not None and idioma in self._idiomas:
                try:
                    grupos.setdefault(clave, {})[idioma] = leer()
                except (KeyError, OSError):
                    continue
        for c in self.ctx.instancia.contenedores_mods():
            for nombre in c.nombres():
                if m := _PATCHOULI_DATA.fullmatch(nombre):
                    datos_viejos.add(f"{m.group(1)}:{m.group(2)}")
        self.sin_traducir_posible = sorted(datos_viejos)
        # Un .md suelto (changelog, README) no es una guía: solo cuentan las carpetas con páginas de GuideME
        guias = {
            (k[1], k[2])
            for k, v in grupos.items()
            if k[0] == "guideme" and "en_us" in v and _CABECERA_GUIDEME.search(v["en_us"][:2000])
        }
        return {k: v for k, v in grupos.items() if k[0] != "guideme" or (k[1], k[2]) in guias}

    def _leer_plantilla(self, libro: str, tipo: str, leer: Callable[[], bytes]) -> None:
        try:
            datos = json.loads(leer().decode("utf-8-sig"))
        except (KeyError, OSError, ValueError):
            return
        if isinstance(datos, dict):
            self._plantillas.setdefault(libro, {})[tipo] = datos

    def _variables_de_pagina(self, libro: tuple[str, str], tipo: str) -> set[str]:
        """Los campos de texto de una página de ese tipo según su plantilla (vacío si es de Patchouli o no hay)."""
        plantillas = self._plantillas.get(libro[1], {})
        if ":" not in tipo:  # sin espacio: el del libro (`BookTemplate.createTemplate`); se prueba el de la entrada
            tipo = f"{libro[0]}:{tipo}"
        return set() if tipo.startswith("patchouli:") else variables_de_texto(plantillas, tipo)

    def _externos(self) -> dict[tuple[str, ...], dict[str, bytes]]:
        """Libros propios del modpack en <instancia>/patchouli_books/<libro>/<idioma>/.

        El español que escribió la propia app no cuenta como traducción del autor: si no, una segunda pasada
        (con correcciones o más memoria) lo dejaría como estaba.
        """
        base = self.ctx.instancia.juego / "patchouli_books"
        grupos: dict[tuple[str, ...], dict[str, bytes]] = {}
        for nombre in Carpeta(base).nombres() if base.is_dir() else []:
            partes = nombre.split("/", 2)
            if len(partes) == 3 and _IDIOMA.fullmatch(partes[1]) and nombre.endswith(".json"):
                if partes[2].startswith("templates/") or partes[1] not in self._idiomas:
                    continue
                ruta = base / nombre
                contenido = ruta.read_bytes() if partes[1] == "en_us" else self.ctx.respaldo.original(ruta)
                if contenido is not None:
                    grupos.setdefault(("externo", partes[0], partes[2]), {})[partes[1]] = contenido
        return grupos

    def detectar(self) -> bool:
        return bool(self._agrupar() or self._externos())

    def describir(self) -> str:
        grupos = {**self._agrupar(), **self._externos()}
        libros = {(k[0], k[1], k[2]) for k in grupos}
        por_sistema: dict[str, int] = {}
        for sistema, *_ in libros:
            por_sistema[sistema] = por_sistema.get(sistema, 0) + 1
        texto = ", ".join(f"{n} de {s}" for s, n in sorted(por_sistema.items())) or "ninguno"
        if self.sin_traducir_posible:
            texto += f" · {len(self.sin_traducir_posible)} antiguos dentro del jar (no se pueden traducir con un pack)"
        return texto

    # ------------------------------------------------------------------ recolección
    def recolectar(self) -> list[Pieza]:
        self._archivos = []
        for clave, por_idioma in [*self._agrupar().items(), *self._externos().items()]:
            ingles = por_idioma.get("en_us")
            if ingles is None:
                continue
            sistema = clave[0]
            archivo = _Archivo(sistema, ingles, self._destino(clave), externo=sistema == "externo")
            if sistema == "patchouli":
                archivo.libro = (clave[1], clave[2])
            archivo.existentes = {v: por_idioma[v] for v in self.ctx.variantes if v in por_idioma}
            if not archivo.existentes:  # si ya hay alguna variante de español, se copia sin gastar
                self._preparar(archivo)
            self._archivos.append(archivo)
        if self.sin_traducir_posible:
            self.ctx.registro(
                "Libros antiguos de Patchouli con el texto dentro del jar (no se traducen sin modificar el mod): "
                + ", ".join(self.sin_traducir_posible)
            )
        piezas = [p for a in self._archivos for p in a.piezas]
        # Un texto que también es del libro se traduce solo como libro (y esa traducción sirve para los dos)
        propios = {p.texto for p in piezas if not p.ambito}
        piezas = [p for p in piezas if not p.ambito or p.texto not in propios]
        self._ambitos = {p.texto: p.ambito for p in piezas if p.ambito}
        return piezas

    def ambito_de(self, texto: str) -> str:
        """El ámbito de un texto que juntó `recolectar` («ui» para los campos de plantilla; si no, libro)."""
        return self._ambitos.get(texto, AMBITO)

    @staticmethod
    def _destino(clave: tuple[str, ...]) -> Callable[[str], str]:
        sistema = clave[0]
        if sistema == "patchouli":
            return lambda v: f"assets/{clave[1]}/patchouli_books/{clave[2]}/{v}/{clave[3]}"
        if sistema in ("mantle", "citadel"):
            return lambda v: f"assets/{clave[1]}/book/{clave[2]}/{v}/{clave[3]}"
        if sistema == "lavender":
            return lambda v: f"assets/{clave[1]}/lavender/{clave[2]}/{clave[3]}/{v}/{clave[4]}"
        if sistema == "guideme":
            return lambda v: f"assets/{clave[1]}/{clave[2]}/_{v}/{clave[3]}"
        return lambda v: f"patchouli_books/{clave[1]}/{v}/{clave[2]}"  # externo

    def _preparar(self, a: _Archivo) -> None:
        try:
            texto = a.ingles.decode("utf-8-sig")
        except UnicodeDecodeError:
            return
        if a.sistema in ("patchouli", "externo", "mantle"):
            self._preparar_json(a, texto, CAMPOS_MANTLE if a.sistema == "mantle" else CAMPOS_PATCHOULI)
        elif a.sistema == "citadel":
            self._preparar_citadel(a, texto)
        else:
            self._preparar_markdown(a, texto)

    def _preparar_json(self, a: _Archivo, texto: str, campos: frozenset[str]) -> None:
        try:
            cadenas = json_cadenas.escanear(texto)
        except ValueError:
            return
        elegidas = [
            c
            for c in cadenas
            if c.campo in campos and not c.texto.strip().startswith("#") and not parece_clave(c.texto)
        ]
        a.piezas = con_vecindad(
            [p for c in elegidas for p in piezas_de(c.texto, f"libro: {c.campo}")],
            lambda p: p.pista in ("libro: name", "libro: title"),
        )
        # Campos que una plantilla propia muestra como texto («heading» de Blood Magic): van aparte y con el tono de la
        # interfaz (casi siempre son nombres), para que los lotes y pistas del libro salgan igual que sin ellos
        extra = self._de_plantilla(a, cadenas, campos)
        a.piezas += [
            Pieza(p.texto, p.pista, AMBITO_PLANTILLA)
            for c in extra
            for p in piezas_de(c.texto, f"libro: {c.campo} (dato de una página con plantilla)")
        ]
        elegidas += extra

        def generar(trad: Mapping[str, str]) -> tuple[bytes, int, int]:
            nuevos = {c.inicio: aplicar(c.texto, trad) for c in elegidas}
            hechos = sum(1 for p in a.piezas if p.texto in trad)
            return json_cadenas.reemplazar(texto, cadenas, nuevos).encode("utf-8"), hechos, len(a.piezas) - hechos

        a.generar = generar

    def _de_plantilla(
        self, a: _Archivo, cadenas: list[json_cadenas.CadenaJson], campos: frozenset[str]
    ) -> list[json_cadenas.CadenaJson]:
        if a.libro is None:
            return []
        tipos = {
            c.ruta[1]: c.texto for c in cadenas if len(c.ruta) == 3 and c.ruta[0] == "pages" and c.ruta[2] == "type"
        }
        variables = {i: self._variables_de_pagina(a.libro, tipo) for i, tipo in tipos.items()}
        return [
            c
            for c in cadenas
            if len(c.ruta) == 3
            and c.ruta[0] == "pages"
            and isinstance(c.ruta[2], str)
            and c.ruta[2] not in campos
            and c.ruta[2] in variables.get(c.ruta[1], ())
            and not c.texto.strip().startswith("#")
            and not parece_clave(c.texto)
        ]

    def _preparar_citadel(self, a: _Archivo, texto: str) -> None:
        texto = texto.replace("\r\n", "\n")
        bloques: list[tuple[bool, list[str]]] = []  # (es párrafo, líneas)
        for linea in texto.split("\n"):
            if not linea.strip() or linea.strip() == "<NEWLINE>":
                bloques.append((False, [linea]))
            elif bloques and bloques[-1][0]:
                bloques[-1][1].append(linea.strip())
            else:
                bloques.append((True, [linea.strip()]))
        ancho = max((len(x) for es, b in bloques if es for x in b), default=80)
        parrafos = [" ".join(b) for es, b in bloques if es]
        a.piezas = con_vecindad([Pieza(p, "libro: página") for p in parrafos if es_traducible(p)], lambda _p: False)

        def generar(trad: Mapping[str, str]) -> tuple[bytes, int, int]:
            salida: list[str] = []
            for es, b in bloques:
                if not es:
                    salida.extend(b)
                    continue
                original = " ".join(b)
                salida.extend(
                    textwrap.wrap(
                        trad.get(original, original), max(ancho, 30), break_long_words=False, break_on_hyphens=False
                    )
                    or [""]
                )
            hechos = sum(1 for p in a.piezas if p.texto in trad)
            return "\n".join(salida).encode("utf-8"), hechos, len(a.piezas) - hechos

        a.generar = generar

    def _preparar_markdown(self, a: _Archivo, texto: str) -> None:
        lineas, segs = markdown.segmentar(texto)
        a.piezas = con_vecindad(
            [Pieza(s.texto, "guía: título" if s.inicio < 5 else "guía: texto") for s in segs if es_traducible(s.texto)],
            lambda p: p.pista == "guía: título",
        )

        def generar(trad: Mapping[str, str]) -> tuple[bytes, int, int]:
            hechos = sum(1 for p in a.piezas if p.texto in trad)
            return markdown.reconstruir(lineas, segs, dict(trad)).encode("utf-8"), hechos, len(a.piezas) - hechos

        a.generar = generar

    def lugares(self) -> list[Lugar]:
        """Por archivo de libro en inglés, los textos que se traducen, en orden (tras `recolectar`)."""
        return [Lugar(a.destino("en_us"), [p.texto for p in a.piezas]) for a in self._archivos if a.piezas]

    # ------------------------------------------------------------------ escritura
    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        for a in self._archivos:
            try:
                self._escribir_libro(a, traducciones, resumen)
            except ValueError as e:  # una ruta imposible de guardar en el pack: ese libro se deja en inglés
                self.ctx.registro(f"No pude guardar un libro: {e}")
        return resumen

    def _escribir_libro(self, a: _Archivo, traducciones: Mapping[str, str], resumen: Resumen) -> None:
        generado: bytes | None = None
        for variante in self.ctx.variantes:
            destino = a.destino(variante)
            if variante in a.existentes:
                # Ya hay traducción del autor: si el pack tiene una copia vieja en esa ruta, que sea la oficial
                if not a.externo and self._en_pack(destino) not in (None, a.existentes[variante]):
                    resumen.archivos.append(self.ctx.pack_listo().escribir(destino, a.existentes[variante]))
                continue
            copia = next((a.existentes[v] for v in (*_PREFERIDAS, *a.existentes) if v in a.existentes), None)
            if copia is not None:
                contenido = copia
            else:
                if a.generar is None:
                    continue
                if generado is None:
                    generado, hechos, faltan = a.generar(traducciones)
                    resumen.traducidos += hechos
                    resumen.pendientes += faltan
                    if hechos == 0:
                        break  # nada traducido: el juego ya usa el inglés por su cuenta
                contenido = generado
            resumen.archivos.append(self._escribir(a, destino, contenido))

    def _en_pack(self, relativa: str) -> bytes | None:
        pack = self.ctx.pack
        ruta = (pack.raiz if pack else self.ctx.instancia.juego / "resourcepacks" / "Traduccion_ES") / relativa
        return ruta.read_bytes() if ruta.is_file() else None

    def _escribir(self, a: _Archivo, destino: str, contenido: bytes) -> Path:
        if a.externo:
            ruta = self.ctx.instancia.juego / destino
            if not ruta.is_file() or ruta.read_bytes() != contenido:
                self.ctx.respaldo.escribir(ruta, contenido, neutro=a.ingles)  # al restaurar queda el inglés
            return ruta
        return self.ctx.pack_listo().escribir(destino, contenido)

    def restaurar(self) -> list[Path]:
        return self.ctx.respaldo.restaurar("patchouli_books/")

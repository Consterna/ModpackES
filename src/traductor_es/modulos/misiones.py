"""Misiones: FTB Quests (SNBT en línea, carpeta lang y NBT de 1.12), BetterQuesting, HQM y Heracles."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..formatos import json_cadenas, nbt, snbt
from .base import Contexto, Pieza, Resumen, aplicar, con_vecindad, contar, unidades
from .cambios import Lugar

AMBITO = "mision"
#: Campos con texto visible en FTB Quests (1.12 usa «text» para la descripción larga).
CAMPOS_FTBQ = frozenset({"title", "subtitle", "description", "text", "hover", "lock_message"})
_NEUTRO_SNBT = b"{\n}\n"


def _es_titulo(pieza: Pieza) -> bool:
    return pieza.pista.endswith("title")


def _relativa(ctx: Contexto, ruta: Path) -> str:
    return ruta.relative_to(ctx.instancia.juego).as_posix()


@dataclass(slots=True)
class _Trabajo:
    """Un archivo a traducir: cómo sacar sus textos y cómo escribirlo con las traducciones."""

    destinos: list[Path]
    piezas: list[Pieza]
    generar: Callable[[Mapping[str, str]], tuple[bytes, int, int]]  #: (contenido, traducidos, pendientes)
    neutro: bytes = b""
    extra: dict[str, object] = field(default_factory=dict[str, object])
    fuente: Path | None = None  #: el archivo en inglés, si no es el mismo destino (carpeta lang de FTB Quests)


class _Base:
    nombre = ""
    ambito = AMBITO

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self._trabajos: list[_Trabajo] = []

    def detectar(self) -> bool:
        raise NotImplementedError

    def describir(self) -> str:
        raise NotImplementedError

    def _prefijos(self) -> list[str]:
        raise NotImplementedError

    def recolectar(self) -> list[Pieza]:
        self._trabajos = list(self._preparar())
        return [p for t in self._trabajos for p in t.piezas]

    def _preparar(self) -> Iterator[_Trabajo]:
        raise NotImplementedError

    def lugares(self) -> list[Lugar]:
        """Por archivo de misiones, sus textos en orden (tras `recolectar`)."""
        vistos: set[str] = set()
        salida: list[Lugar] = []
        for t in self._trabajos:
            ruta = t.fuente or (t.destinos[0] if t.destinos else None)
            if ruta is None:
                continue
            donde = _relativa(self.ctx, ruta)
            if donde not in vistos:  # en la carpeta lang hay un trabajo por variante del mismo archivo en inglés
                vistos.add(donde)
                salida.append(Lugar(donde, [p.texto for p in t.piezas]))
        return salida

    def escribir(self, traducciones: Mapping[str, str]) -> Resumen:
        resumen = Resumen()
        for t in self._trabajos:
            datos, traducidos, pendientes = t.generar(traducciones)
            resumen.traducidos += traducidos
            resumen.pendientes += pendientes
            for destino in t.destinos:
                actual = destino.read_bytes() if destino.is_file() else None
                if actual != datos:
                    self.ctx.respaldo.escribir(destino, datos, t.neutro)
                    resumen.archivos.append(destino)
        return resumen

    def restaurar(self) -> list[Path]:
        return [r for p in self._prefijos() for r in self.ctx.respaldo.restaurar(p)]

    def _original(self, ruta: Path) -> bytes | None:
        return self.ctx.respaldo.original(ruta)


# ====================================================================== FTB Quests


class FTBQuests(_Base):
    nombre = "Misiones de FTB Quests"

    def raices(self) -> list[Path]:
        base = self.ctx.instancia.juego / "config" / "ftbquests"
        if not base.is_dir():
            return []
        return [
            d
            for d in sorted(base.iterdir())
            if d.is_dir()
            and (
                (d / "chapters").is_dir()
                or (d / "data.snbt").is_file()
                or (d / "file.nbt").is_file()
                or (d / "lang").is_dir()
            )
        ]

    @staticmethod
    def formato(raiz: Path) -> str:
        lang = raiz / "lang"
        if (lang / "en_us.snbt").is_file() or (lang / "en_us").is_dir():
            return "lang"
        if (raiz / "file.nbt").is_file() or next(raiz.rglob("*.nbt"), None) is not None:
            return "nbt"
        return "snbt"

    def detectar(self) -> bool:
        if self.ctx.solo_por_idioma:
            return any(self.formato(r) == "lang" for r in self.raices())
        return bool(self.raices())

    def describir(self) -> str:
        nombres = {"lang": "textos en lang/ (1.21+)", "nbt": "NBT binario (1.12)", "snbt": "texto en los capítulos"}
        return ", ".join(f"{r.name}: {nombres[self.formato(r)]}" for r in self.raices())

    def _prefijos(self) -> list[str]:
        return [_relativa(self.ctx, r) + "/" for r in self.raices()]

    def _preparar(self) -> Iterator[_Trabajo]:
        for raiz in self.raices():
            formato = self.formato(raiz)
            if self.ctx.solo_por_idioma and formato != "lang":
                continue  # los capítulos tienen un solo idioma: ya los tradujo la pasada principal
            if formato == "lang":
                yield from self._lang(raiz)
            elif formato == "nbt":
                yield from self._nbt(raiz)
            else:
                yield from self._snbt(raiz)

    # ---------------------------------------------------------------- SNBT en línea (1.14 - 1.20)
    def _snbt(self, raiz: Path) -> Iterator[_Trabajo]:
        for ruta in sorted(raiz.rglob("*.snbt")):
            if "lang" in ruta.relative_to(raiz).parts:
                continue
            original = self._original(ruta)
            if original is None:
                continue
            try:
                yield self._trabajo_snbt(original.decode("utf-8"), [ruta], lambda c: c.campo in CAMPOS_FTBQ, {})
            except (ValueError, UnicodeDecodeError):
                self.ctx.registro(f"{ruta.name} está dañado: se deja igual")

    def _trabajo_snbt(
        self, src: str, destinos: list[Path], filtro: Callable[[snbt.Cadena], bool], fijos: Mapping[int, str]
    ) -> _Trabajo:
        cadenas = [c for c in snbt.escanear(src) if filtro(c)]
        piezas = con_vecindad(
            [Pieza(u, f"misión: {c.campo}") for c in cadenas if c.inicio not in fijos for u in unidades(c.texto)],
            _es_titulo,
        )

        def generar(trad: Mapping[str, str]) -> tuple[bytes, int, int]:
            nuevos: dict[int, str] = {}
            hechos = faltan = 0
            for c in cadenas:
                if c.inicio in fijos:
                    nuevos[c.inicio] = fijos[c.inicio]
                    continue
                us = unidades(c.texto)
                hechos += sum(1 for u in us if u in trad)
                faltan += sum(1 for u in us if u not in trad)
                nuevos[c.inicio] = aplicar(c.texto, trad)
            return snbt.reemplazar(src, cadenas, nuevos).encode("utf-8"), hechos, faltan

        return _Trabajo(destinos, piezas, generar, _NEUTRO_SNBT)

    # ---------------------------------------------------------------- carpeta lang (2001.4+ / 2100+)
    def _lang(self, raiz: Path) -> Iterator[_Trabajo]:
        lang = raiz / "lang"
        fuentes = [lang / "en_us.snbt"] if (lang / "en_us.snbt").is_file() else []
        if (lang / "en_us").is_dir():
            fuentes += sorted((lang / "en_us").rglob("*.snbt"))
        for fuente in fuentes:
            try:
                src = fuente.read_bytes().decode("utf-8")
                cadenas = snbt.escanear(src)
            except (ValueError, UnicodeDecodeError):
                self.ctx.registro(f"{fuente.name} está dañado: se deja igual")
                continue
            relativa = fuente.relative_to(lang).as_posix().removeprefix("en_us")
            # Cada variante de español que el modpack ya trae conserva sus textos; el resto se completa
            for variante in self.ctx.variantes:
                destino = lang / f"{variante}{relativa}"
                fijos = self._fijos(destino, cadenas)
                trabajo = self._trabajo_snbt(src, [destino], lambda _c: True, fijos)
                trabajo.fuente = fuente
                yield trabajo

    def _fijos(self, destino: Path, cadenas: list[snbt.Cadena]) -> dict[int, str]:
        """Traducciones que trae el modpack en ese idioma, puestas en las posiciones del archivo en inglés."""
        original = self._original(destino)
        if original is None:
            return {}
        try:
            previas_lista = snbt.escanear(original.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        previas: dict[str | None, list[str]] = {}
        for c in previas_lista:
            previas.setdefault(c.campo, []).append(c.texto)
        fijos: dict[int, str] = {}
        vistos: dict[str | None, int] = {}
        for c in cadenas:
            n = vistos.get(c.campo, 0)
            vistos[c.campo] = n + 1
            lista = previas.get(c.campo, [])
            if n < len(lista) and lista[n].strip() and lista[n] != c.texto:
                fijos[c.inicio] = lista[n]
        return fijos

    # ---------------------------------------------------------------- NBT binario (1.12)
    def _nbt(self, raiz: Path) -> Iterator[_Trabajo]:
        for ruta in sorted(raiz.rglob("*.nbt")):
            original = self._original(ruta)
            if original is None:
                continue
            try:
                arbol, compresion = nbt.leer(original)
            except (ValueError, EOFError, OSError):
                self.ctx.registro(f"No pude leer {ruta.name}: se deja igual")
                continue
            textos = [c for c in nbt.cadenas(arbol) if c.campo in CAMPOS_FTBQ]
            if not textos:
                continue
            piezas = con_vecindad(
                [Pieza(u, f"misión: {c.campo}") for c in textos for u in unidades(c.texto)], _es_titulo
            )

            def generar(
                trad: Mapping[str, str], original: bytes = original, compresion: nbt.Compresion = compresion
            ) -> tuple[bytes, int, int]:
                arbol, _ = nbt.leer(original)  # árbol nuevo cada vez: no se acumulan cambios
                hechos = faltan = 0
                for c in nbt.cadenas(arbol):
                    if c.campo in CAMPOS_FTBQ:
                        us = unidades(c.texto)
                        hechos += sum(1 for u in us if u in trad)
                        faltan += sum(1 for u in us if u not in trad)
                        nbt.poner(c, aplicar(c.texto, trad))
                return nbt.escribir(arbol, compresion), hechos, faltan

            yield _Trabajo([ruta], piezas, generar)


# ====================================================================== JSON (BetterQuesting, HQM, Heracles)


class _MisionesJson(_Base):
    """Misiones guardadas en JSON: se traducen en el sitio con copia de seguridad."""

    carpetas: tuple[str, ...] = ()
    excluir: frozenset[str] = frozenset()

    def _archivos(self) -> list[Path]:
        juego = self.ctx.instancia.juego
        archivos: list[Path] = []
        for carpeta in self.carpetas:
            base = juego / carpeta
            if base.is_file():
                archivos.append(base)
            elif base.is_dir():
                archivos += sorted(p for p in base.rglob("*.json") if p.name not in self.excluir)
        return archivos

    def detectar(self) -> bool:
        return bool(self._archivos())

    def describir(self) -> str:
        return contar(len(self._archivos()), "archivo")

    def _prefijos(self) -> list[str]:
        return [c.rstrip("/") for c in self.carpetas]

    def _es_texto(self, cadena: json_cadenas.CadenaJson) -> tuple[bool, bool]:
        """(se traduce, es un componente JSON serializado)."""
        raise NotImplementedError

    def _preparar(self) -> Iterator[_Trabajo]:
        for ruta in self._archivos():
            original = self._original(ruta)
            if original is None:
                continue
            try:
                src = original.decode("utf-8-sig")
                cadenas = json_cadenas.escanear(src)
            except (ValueError, UnicodeDecodeError):
                self.ctx.registro(f"{ruta.name} no es JSON válido: se deja igual")
                continue
            elegidas = [(c, lit) for c in cadenas for ok, lit in [self._es_texto(c)] if ok]
            if not elegidas:
                continue
            piezas = [Pieza(u, f"misión: {c.campo}") for c, lit in elegidas for u in unidades(c.texto, lit)]
            bom = original.startswith(b"\xef\xbb\xbf")

            def generar(
                trad: Mapping[str, str],
                src: str = src,
                cadenas: list[json_cadenas.CadenaJson] = cadenas,
                elegidas: list[tuple[json_cadenas.CadenaJson, bool]] = elegidas,
                bom: bool = bom,
            ) -> tuple[bytes, int, int]:
                nuevos: dict[int, str] = {}
                hechos = faltan = 0
                for c, lit in elegidas:
                    us = unidades(c.texto, lit)
                    hechos += sum(1 for u in us if u in trad)
                    faltan += sum(1 for u in us if u not in trad)
                    nuevos[c.inicio] = aplicar(c.texto, trad, lit)
                texto = json_cadenas.reemplazar(src, cadenas, nuevos)
                return (b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8"), hechos, faltan

            yield _Trabajo([ruta], piezas, generar)


class BetterQuesting(_MisionesJson):
    nombre = "Misiones de BetterQuesting"
    carpetas = ("config/betterquesting/DefaultQuests.json", "config/betterquesting/DefaultQuests")

    def _es_texto(self, cadena: json_cadenas.CadenaJson) -> tuple[bool, bool]:
        return cadena.campo in ("name:8", "desc:8"), False


class HQM(_MisionesJson):
    nombre = "Misiones de Hardcore Questing Mode"
    carpetas = ("config/hqm", "config/hardcorequesting")
    # sets.json enlaza los sets por nombre de archivo; los demás son estado del mundo o configuración
    excluir = frozenset({"sets.json", "state.json", "data.json", "deaths.json", "teams.json", "config.json"})

    def _es_texto(self, cadena: json_cadenas.CadenaJson) -> tuple[bool, bool]:
        return cadena.campo in ("name", "description"), False


class Heracles(_MisionesJson):
    nombre = "Misiones de Heracles"
    carpetas = ("config/heracles/quests", "config/odyssey/quests")

    def _es_texto(self, cadena: json_cadenas.CadenaJson) -> tuple[bool, bool]:
        ruta = cadena.ruta
        if len(ruta) >= 2 and ruta[0] == "display":
            if ruta[1] in ("title", "subtitle"):
                return True, True  # componente serializado (FLAT_CODEC)
            if ruta[1] == "description":
                return True, False
        if len(ruta) == 3 and ruta[0] in ("rewards", "tasks") and ruta[2] == "title":
            return True, False
        return False, False


def todos(ctx: Contexto) -> list[_Base]:
    return [FTBQuests(ctx), BetterQuesting(ctx), HQM(ctx), Heracles(ctx)]

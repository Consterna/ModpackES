"""Compara el inventario del oráculo (`inventario.py`) con lo que la app recoge para traducir: la brecha de cobertura.

Para cada pack:
- **Archivos de idioma:** cada clave en inglés que encontró el oráculo (`assets/<ns>/lang/en_us.*`) cuenta como vista si
  está en la tabla de idiomas que arma la app. Si no, la app no lee ese archivo (un pack inactivo, un shaderpack…).
- **Lo demás:** cada frase del oráculo cuenta como cubierta si la app la recoge (igual, o como trozo de un texto con
  estilos). Lo que queda se agrupa por patrón de ruta, con ejemplos, para revisarlo a mano.

Solo lee: la app recolecta con una memoria temporal y no escribe nada en la instancia.

Uso:
    uv run python scripts/auditoria/comparar_cobertura.py C:/dev/corpus-modpacks/ftb-86 [más packs…] [--java]
    uv run python scripts/auditoria/comparar_cobertura.py --todos
Deja `build/auditoria/<pack>/brecha.json` y, con varios packs, `build/auditoria/brecha_total.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent.parent
#: Con MODPACKES_CODIGO=<carpeta src de otra copia> se mide con ese código (p. ej. el commit base, para el «antes»).
sys.path.insert(0, os.environ.get("MODPACKES_CODIGO") or str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventario import sin_codigos  # noqa: E402

from traductor_es.modulos.cobertura import revisar_cobertura  # noqa: E402
from traductor_es.motores.simulador import Simulador  # noqa: E402
from traductor_es.nucleo.memoria import Memoria  # noqa: E402
from traductor_es.proceso import Proceso  # noqa: E402

SALIDA = RAIZ / "build" / "auditoria"
CORPUS = Path(r"C:\dev\corpus-modpacks")
EJEMPLOS = 4
_ESPACIOS = re.compile(r"\s+")


_BORDES = re.compile(r"^(?:[#>*+\-|]+\s*|\d+\.\s+)+|[\s\"'“”«»]+$")


def normal(texto: str) -> str:
    """Para comparar: sin códigos de formato, sin marcas de markdown al inicio, sin comillas en los bordes, sin
    espacios de más y en minúscula."""
    limpio = _ESPACIOS.sub(" ", sin_codigos(texto)).strip().lower()
    return _BORDES.sub("", limpio).strip(" \"'“”«»")


@dataclass(slots=True)
class LadoApp:
    textos: set[str] = field(default_factory=set[str])  #: lo que la app recoge, normalizado
    por_modulo: dict[str, int] = field(default_factory=dict[str, int])
    claves: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])  #: (espacio, clave) en_us
    cobertura: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    _por_palabra: dict[str, list[str]] = field(default_factory=lambda: defaultdict[str, list[str]](list))

    def indexar(self) -> None:
        for t in self.textos:
            for p in set(re.findall(r"[a-z']{3,}", t)):
                self._por_palabra[p].append(t)

    def cubre(self, texto: str) -> bool:
        """¿La app recoge este texto, entero o como trozo (un componente con estilos se traduce por partes)?"""
        n = normal(texto)
        if not n or n in self.textos:
            return True
        # Candidatos por cualquiera de sus palabras: en un componente JSON la más larga suele ser una clave
        # («underlined», «clickevent»), no el texto
        for palabra in set(re.findall(r"[a-z']{3,}", n)):
            if any(len(t) >= 8 and (t in n or n in t) for t in self._por_palabra.get(palabra, ())):
                return True
        return False


def lado_app(instancia: Path, java: bool) -> LadoApp:
    """Lo que recogería la app al traducir (sin traducir ni escribir nada)."""
    lado = LadoApp()
    with tempfile.TemporaryDirectory(prefix="auditoria-") as tmp, Memoria(Path(tmp) / "memoria.sqlite") as memoria:
        proceso = Proceso(instancia, Simulador(), memoria=memoria, texto_java=java)
        for _grupo, modulo in proceso.modulos():
            piezas = modulo.recolectar()
            lado.por_modulo[modulo.nombre] = lado.por_modulo.get(modulo.nombre, 0) + len(piezas)
            lado.textos.update(normal(p.texto) for p in piezas)
        tabla = proceso.instancia.tabla_idiomas()
        for ns, por_idioma in tabla.datos.items():
            lado.claves.update((ns, k) for k in por_idioma.get("en_us", {}))
        lado.cobertura = [
            {"categoria": h.categoria, "donde": h.donde, "textos": h.cantidad, "ejemplos": list(h.ejemplos)}
            for h in revisar_cobertura(proceso.ctx, java=java)
        ]
    lado.textos.discard("")
    lado.indexar()
    return lado


def _espacio_de_lang(ruta: str) -> str | None:
    """`assets/<ns>/lang/x.json` o `resources/<ns>/lang/x.lang` (ResourceLoader) → `<ns>`; si no, None."""
    partes = PurePosixPath(ruta).parts
    if len(partes) >= 3 and partes[-2] == "lang" and partes[0] in ("assets", "resources") and len(partes) == 4:
        return partes[1]
    return None


def version_de(instancia: Path) -> tuple[int, ...]:
    """La versión de Minecraft del `mmc-pack.json` que arma el descargador (26.x cuenta como más nueva que 1.x)."""
    try:
        datos: dict[str, Any] = json.loads((instancia / "mmc-pack.json").read_text(encoding="utf-8"))
        version = next(str(c["version"]) for c in datos["components"] if c.get("uid") == "net.minecraft")
        return tuple(int(x) for x in version.split(".") if x.isdigit())
    except (OSError, ValueError, StopIteration, KeyError):
        return ()


def lang_que_carga_el_juego(ruta: str, version: tuple[int, ...]) -> bool:
    """Antes de 1.13 el juego lee `.lang`; desde 1.13, `.json`. El otro formato está en el jar pero no se carga."""
    if not version:
        return True
    legacy = version < (1, 13)
    return ruta.lower().endswith(".lang") == legacy


_DIALECTOS = ("es_es", "es_mx", "es_ar", "es_cl", "es_ec", "es_uy", "es_ve")


class Contenedores:
    """Los nombres de archivo de cada jar o zip del corpus, para saber si un libro ya trae su español."""

    def __init__(self, juego: Path) -> None:
        self.juego = juego
        self._nombres: dict[str, set[str]] = {}

    def nombres(self, contenedor: str) -> set[str]:
        if contenedor not in self._nombres:
            ruta = self.juego / contenedor
            try:
                if "!" in contenedor or not ruta.is_file():
                    self._nombres[contenedor] = set[str]()
                else:
                    with zipfile.ZipFile(ruta) as z:
                        self._nombres[contenedor] = set(z.namelist())
            except (OSError, zipfile.BadZipFile):
                self._nombres[contenedor] = set[str]()
        return self._nombres[contenedor]

    def ya_en_espanol(self, contenedor: str, ruta: str) -> bool:
        """¿Hay el mismo archivo en una carpeta de español (`…/en_us/…` → `…/es_mx/…`, o `_es_mx/` en GuideME)?"""
        if "/en_us/" not in f"/{ruta}":
            return False
        nombres = self.nombres(contenedor) if contenedor else set[str]()
        for d in _DIALECTOS:
            otra = f"/{ruta}".replace("/en_us/", f"/{d}/", 1)[1:]
            if otra in nombres or (not contenedor and (self.juego / otra).is_file()):
                return True
        return False


def comparar(instancia: Path, java: bool = False, nombre_salida: str = "brecha") -> dict[str, Any]:
    nombre = instancia.name
    inventario = SALIDA / nombre / "inventario.jsonl"
    if not inventario.is_file():
        raise SystemExit(f"Falta {inventario}: corre antes inventario.py con ese pack")
    app = lado_app(instancia, java)
    version = version_de(instancia)
    contenedores = Contenedores(instancia / "minecraft" if (instancia / "minecraft").is_dir() else instancia)
    ya_espanol = 0
    lang_total = lang_vistas = 0
    lang_no_vistas: dict[str, list[str]] = defaultdict(list)
    brecha: dict[str, dict[str, Any]] = {}
    textos_total = textos_cubiertos = 0
    with inventario.open(encoding="utf-8") as f:
        for linea in f:
            t: dict[str, Any] = json.loads(linea)
            if t["clase"] == "lang":
                if not lang_que_carga_el_juego(t["ruta"], version):
                    continue
                ns = _espacio_de_lang(t["ruta"])
                lang_total += 1
                if ns is not None and (ns, t["campo"]) in app.claves:
                    lang_vistas += 1
                elif ns is None and app.cubre(t["texto"]):
                    lang_vistas += 1  # idioma fuera de assets/ (shaderpacks…) que recoge un módulo propio
                else:
                    lang_no_vistas[f"{t['contenedor'] or 'instancia'}::{t['ruta']}"].append(t["campo"])
                continue
            textos_total += 1
            if app.cubre(t["texto"]):
                textos_cubiertos += 1
                continue
            if contenedores.ya_en_espanol(t["contenedor"], t["ruta"]):
                textos_cubiertos += 1  # el libro ya trae su español: la app lo copia sin traducir
                ya_espanol += 1
                continue
            grupo = brecha.setdefault(t["patron"], {"textos": 0, "archivos": set(), "ejemplos": []})
            grupo["textos"] += 1
            grupo["archivos"].add(f"{t['contenedor']}::{t['ruta']}")
            if len(grupo["ejemplos"]) < EJEMPLOS:
                grupo["ejemplos"].append({"donde": f"{t['contenedor']}::{t['ruta']}", "campo": t["campo"],
                                          "texto": t["texto"][:160]})  # fmt: skip
    resultado: dict[str, Any] = {
        "pack": nombre,
        "lang": {"claves": lang_total, "vistas": lang_vistas,
                 "no_vistas": {k: len(v) for k, v in sorted(lang_no_vistas.items(), key=lambda kv: -len(kv[1]))}},
        "textos": {"total": textos_total, "cubiertos": textos_cubiertos, "ya_en_espanol": ya_espanol},
        "version": ".".join(map(str, version)),
        "por_modulo": app.por_modulo,
        "cobertura_app": app.cobertura,
        "brecha": {p: {"textos": g["textos"], "archivos": len(g["archivos"]), "ejemplos": g["ejemplos"]}
                   for p, g in sorted(brecha.items(), key=lambda kv: -kv[1]["textos"])},
    }  # fmt: skip
    (SALIDA / nombre / f"{nombre_salida}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), "utf-8")
    return resultado


def total(resultados: list[dict[str, Any]]) -> dict[str, Any]:
    """La brecha de todo el corpus por patrón: en cuántos packs sale y cuántos textos suma."""
    por_patron: dict[str, dict[str, Any]] = {}
    for r in resultados:
        for patron, g in r["brecha"].items():
            p = por_patron.setdefault(patron, {"packs": [], "textos": 0, "archivos": 0, "ejemplos": []})
            p["packs"].append(r["pack"])
            p["textos"] += g["textos"]
            p["archivos"] += g["archivos"]
            p["ejemplos"] += g["ejemplos"][: max(0, EJEMPLOS - len(p["ejemplos"]))]
    lang = sum(r["lang"]["claves"] for r in resultados)
    vistas = sum(r["lang"]["vistas"] for r in resultados)
    textos = sum(r["textos"]["total"] for r in resultados)
    cubiertos = sum(r["textos"]["cubiertos"] for r in resultados)
    return {
        "packs": len(resultados),
        "lang": {"claves": lang, "vistas": vistas},
        "textos": {"total": textos, "cubiertos": cubiertos},
        "brecha": dict(sorted(por_patron.items(), key=lambda kv: (-len(kv[1]["packs"]), -kv[1]["textos"]))),
    }


def _linea(r: dict[str, Any]) -> str:
    lang, tx = r["lang"], r["textos"]
    pl = 100 * lang["vistas"] / lang["claves"] if lang["claves"] else 100.0
    pt = 100 * tx["cubiertos"] / tx["total"] if tx["total"] else 100.0
    return (f"{r['pack']:<42} idioma {lang['vistas']:>6}/{lang['claves']:<6} ({pl:5.1f} %)  "
            f"otros {tx['cubiertos']:>5}/{tx['total']:<5} ({pt:5.1f} %)")  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packs", nargs="*", type=Path)
    ap.add_argument("--todos", action="store_true", help=f"todos los packs de {CORPUS} con inventario")
    ap.add_argument("--java", action="store_true", help="incluir el texto del código de los mods (tarda)")
    ap.add_argument("--nombre", default="brecha", help="nombre de los archivos de salida (p. ej. brecha_base)")
    args = ap.parse_args()
    packs: list[Path] = list(args.packs)
    if args.todos:
        packs += [p for p in sorted(CORPUS.iterdir()) if (SALIDA / p.name / "inventario.jsonl").is_file()]
    resultados: list[dict[str, Any]] = []
    for pack in packs:
        try:
            r = comparar(pack, args.java, args.nombre)
        except Exception as e:  # un pack que falla se informa y se sigue con el siguiente
            sys.stdout.buffer.write(f"✗ {pack.name}: {type(e).__name__}: {e}\n".encode())
            continue
        resultados.append(r)
        sys.stdout.buffer.write((_linea(r) + "\n").encode())
    if len(resultados) > 1:
        t = total(resultados)
        (SALIDA / f"{args.nombre}_total.json").write_text(json.dumps(t, ensure_ascii=False, indent=2), "utf-8")
        sys.stdout.buffer.write(f"\nTotal: {_linea({**t, 'pack': f'{t["packs"]} packs'})}\n".encode())
        for patron, g in list(t["brecha"].items())[:40]:
            sys.stdout.buffer.write(f"  {len(g['packs']):>3} packs {g['textos']:>6} textos  {patron}\n".encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Analiza lo que volcó la sonda del juego (`<juego>/modpackes-sonda/`) en una instancia traducida con `--simular`.

Con el simulador, todo lo que la app tradujo empieza con «ES». Así, lo que se ve en inglés salta a la vista:
- **Idioma cargado** (`idioma.json`): claves cuyo valor sigue igual al inglés y es una frase. Se separan las que no
  están en ningún archivo de idioma de la instancia (las crea un mod mientras el juego corre: KubeJS, ARRP…).
- **Texto dibujado** (`textos-dibujados.json`): lo que pasó por la fuente del juego sin «ES» y en inglés, por pantalla.
- **Claves crudas en pantalla** (`a.b.c` dibujado tal cual): una traducción rota o una clave que falta.

Uso:
    uv run python scripts/auditoria/analizar_sonda.py RUTA_DE_LA_INSTANCIA [--salida build/auditoria/juego-<pack>.json]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from descargar_corpus import RAIZ as DESCARGAS
from inventario import es_frase_inglesa, sin_codigos

MARCA = "«ES»"
#: Claves del propio loader (su jar vive en libraries/, fuera de la instancia).
PREFIJOS_LOADER = ("fml.", "neoforge.", "commands.neoforge.", "commands.config.", "forge.", "commands.forge.",
                   "loadwarning.", "fabric.", "modmenu.", "quilt.")  # fmt: skip
VANILLA = DESCARGAS / "vanilla" / "en_us.json"  # copia local del idioma de Minecraft


def claves_del_juego() -> set[str]:
    """Las claves del idioma de Minecraft (copia local de su en_us), o ninguna si no está."""
    try:
        return set(cast(dict[str, Any], json.loads(VANILLA.read_text(encoding="utf-8"))))
    except (OSError, ValueError):
        return set()


_ESPACIOS = re.compile(r"\s+")
_CLAVE_CRUDA = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_\-]+){2,}$")


def _juego(ruta: Path) -> Path:
    for sub in ("minecraft", ".minecraft"):
        if (ruta / sub).is_dir():
            return ruta / sub
    return ruta


def claves_en_archivos(juego: Path) -> set[str]:
    """Todas las claves de los `en_us.json` de los jars, zips y carpetas de la instancia (lo que se ve sin jugar)."""
    claves: set[str] = set()
    patron = re.compile(r"(^|/)assets/[^/]+/lang/en_us\.json$")

    def de_zip(z: zipfile.ZipFile, profundidad: int = 0) -> None:
        for n in z.namelist():
            try:
                if patron.search(n):
                    datos: object = json.loads(z.read(n).decode("utf-8-sig", "replace"))
                    if isinstance(datos, dict):
                        claves.update(cast(dict[str, Any], datos))
                elif n.endswith(".jar") and profundidad < 3:
                    with zipfile.ZipFile(io.BytesIO(z.read(n))) as interno:
                        de_zip(interno, profundidad + 1)
            except (ValueError, zipfile.BadZipFile, OSError):
                continue

    for p in juego.rglob("*"):
        try:
            if p.suffix.lower() in (".jar", ".zip") and p.is_file():
                with zipfile.ZipFile(p) as z:
                    de_zip(z)
            elif p.is_file() and patron.search(p.as_posix()):
                datos = json.loads(p.read_text(encoding="utf-8-sig", errors="replace"))
                if isinstance(datos, dict):
                    claves.update(cast(dict[str, Any], datos))
        except (ValueError, zipfile.BadZipFile, OSError):
            continue
    return claves


def textos_de_la_app(instancia: Path) -> set[str]:
    """Lo que la app recoge para traducir en esa instancia (normalizado): para separar lo que tuvo y el simulador
    rechazó (su respuesta, «ES» + el original, no pasa la regla de «quedó en inglés») de lo que nunca vio."""
    from comparar_cobertura import lado_app  # noqa: PLC0415 (importa la app: solo si se pide)

    return lado_app(instancia, java=False).textos


def analizar(instancia: Path, con_app: bool = False) -> dict[str, Any]:
    juego = _juego(instancia)
    carpeta = juego / "modpackes-sonda"
    idioma: dict[str, Any] = json.loads((carpeta / "idioma.json").read_text(encoding="utf-8"))
    entradas = cast(dict[str, Any], idioma.get("claves") or idioma.get("entradas") or {})
    if isinstance(entradas, list):
        entradas = {str(e.get("clave")): e for e in cast(list[dict[str, Any]], entradas)}
    en_archivos = claves_en_archivos(juego)
    en_ingles: list[dict[str, str]] = []
    de_ejecucion: list[dict[str, str]] = []
    del_juego: list[dict[str, str]] = []
    del_loader: list[dict[str, str]] = []
    vanilla = claves_del_juego()
    rechazadas: list[dict[str, str]] = []
    de_la_app = textos_de_la_app(instancia) if con_app else set[str]()
    traducidas = 0
    for clave, e in entradas.items():
        valor = str(e.get("valor", ""))
        if MARCA in valor or not e.get("igual"):
            traducidas += 1 if MARCA in valor else 0
            continue
        if not es_frase_inglesa(valor, "text"):
            continue
        fila = {"clave": clave, "valor": valor[:160]}
        if de_la_app and _ESPACIOS.sub(" ", sin_codigos(valor)).strip().lower() in de_la_app:
            rechazadas.append(fila)  # la app lo tuvo: lo dejó en inglés la validación (con el simulador)
        elif clave in en_archivos:
            en_ingles.append(fila)
        elif clave in vanilla:
            del_juego.append(fila)  # el español oficial del juego lo deja igual (p. ej. «Badlands» en es_mx)
        elif clave.startswith(PREFIJOS_LOADER):
            del_loader.append(fila)
        else:
            de_ejecucion.append(fila)
    resultado: dict[str, Any] = {
        "idioma_del_juego": idioma.get("idioma"),
        "claves_cargadas": len(entradas),
        "con_marca_de_traduccion": traducidas,
        "en_ingles_de_archivos": len(en_ingles),
        "en_ingles_creadas_al_jugar": len(de_ejecucion),
        "en_ingles_que_la_app_tenia": len(rechazadas),
        "igual_en_el_espanol_del_juego": len(del_juego),
        "en_ingles_del_loader": len(del_loader),
        "ejemplos_del_loader": del_loader[:30],
        "por_espacio_de_archivos": Counter(f["clave"].split(".")[1] if f["clave"].count(".") else "?"
                                           for f in en_ingles).most_common(25),
        "ejemplos_de_archivos": en_ingles[:40],
        "ejemplos_creadas_al_jugar": de_ejecucion[:60],
    }  # fmt: skip
    dibujados = carpeta / "textos-dibujados.json"
    if dibujados.is_file():
        datos: dict[str, Any] = json.loads(dibujados.read_text(encoding="utf-8"))
        lista = cast(list[dict[str, Any]], datos.get("textos") or datos.get("entradas") or [])
        sin_marca: Counter[str] = Counter()
        crudas: Counter[str] = Counter()
        ejemplos: dict[str, list[str]] = {}
        for t in lista:
            texto = sin_codigos(str(t.get("texto", ""))).strip()
            pantallas = cast(list[str], t.get("pantallas") or [t.get("pantalla", "")])
            pantalla = str(pantallas[0]) if pantallas else ""
            if _CLAVE_CRUDA.match(texto):
                crudas[texto] += 1
            elif MARCA not in texto and es_frase_inglesa(texto, "text"):
                sin_marca[pantalla] += 1
                ejemplos.setdefault(pantalla, [])
                if len(ejemplos[pantalla]) < 8:
                    ejemplos[pantalla].append(texto[:120])
        resultado["dibujados"] = {
            "total": len(lista),
            "en_ingles_por_pantalla": sin_marca.most_common(30),
            "ejemplos": ejemplos,
            "claves_crudas": crudas.most_common(40),
        }
    return resultado


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instancia", type=Path)
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--con-app", action="store_true", help="separar lo que la app recogió (tarda: lee la instancia)")
    args = ap.parse_args()
    r = analizar(args.instancia, args.con_app)
    texto = json.dumps(r, ensure_ascii=False, indent=2)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto, encoding="utf-8")
    sys.stdout.buffer.write(texto[:6000].encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Banco de calidad de las fuentes nuevas de la auditoría (shaders, descripciones, Origins, FancyMenu y loader).

Lo usa `medir_calidad.py --banco` para comprobar que lo nuevo se traduce con la misma calidad que lo de antes. Donde hay
traducción humana sirve de referencia:
- el español que traen los shaderpacks (Complementary y Photon lo traducen a mano);
- el `es_es` de NeoForge.

En lo demás no hay referencia: se miden la aceptación y las dudas del control de calidad. Los textos y sus pistas salen
de los módulos de la app (exactamente lo que se mandaría al motor), con una muestra fija (semilla 7) y un tope por
fuente. El grupo de cada texto va en un archivo aparte (`<salida>.grupos.json`) para no tocar la pista.

Uso:
    uv run python scripts/auditoria/banco_fuentes_nuevas.py --salida build/banco_fuentes_nuevas.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from traductor_es.fuentes.instancia import Instancia  # noqa: E402
from traductor_es.modulos import descripciones, fancymenu, loader, origins, shaders  # noqa: E402
from traductor_es.modulos.base import Contexto  # noqa: E402
from traductor_es.salida.copias import Respaldo  # noqa: E402
from traductor_es.salida.resource_pack import PackSalida  # noqa: E402

CORPUS = Path(r"C:\dev\corpus-modpacks")
PRISM = Path(r"C:\dev\proyectos\traducir-modpacks\.herramientas\prism\11.1.1\instances")
TOPE = 30
Caso = dict[str, str]


def _ctx(inst: Instancia) -> Contexto:
    return Contexto(inst, Respaldo(inst.juego), pack=PackSalida(inst))


def _sin_referencia(modulo_cls: Any, packs: list[Path]) -> list[Caso]:
    casos: list[Caso] = []
    vistos: set[str] = set()
    for pack in packs:
        with Instancia(pack) as inst:
            modulo = modulo_cls(_ctx(inst))
            if not modulo.detectar():
                continue
            for p in modulo.recolectar():
                if p.texto not in vistos:
                    vistos.add(p.texto)
                    casos.append({"ambito": "ui", "original": p.texto, "referencia": "", "pista": p.pista})
    return casos


def _shaders_con_referencia(packs: list[Path]) -> list[Caso]:
    """Pares inglés → español humano del menú de los shaderpacks que traen su español (zip o carpeta)."""
    casos: list[Caso] = []
    vistos: set[str] = set()
    for pack in packs:
        carpeta = pack / "minecraft" / "shaderpacks"
        for ruta in sorted(carpeta.iterdir()) if carpeta.is_dir() else []:
            shader = shaders._leer_shader(ruta)  # pyright: ignore[reportPrivateUsage]
            if shader is None:
                continue
            espanol: dict[str, str] = next(
                (t for idioma, t in sorted(shader.idiomas.items()) if idioma.startswith("es_")), dict[str, str]()
            )
            ingles_del_shader: dict[str, str] = shader.idiomas["en_us"] if espanol else {}
            for clave, ingles in ingles_del_shader.items():
                ref = espanol.get(clave, "")
                if ref and ref != ingles and ingles not in vistos and len(ingles) > 3:
                    vistos.add(ingles)
                    pista = shaders.Shaders._pista(clave)  # pyright: ignore[reportPrivateUsage]
                    casos.append({"ambito": "ui", "original": ingles, "referencia": ref, "pista": pista})
    return casos


def _loader_con_referencia(instancia: Path) -> list[Caso]:
    """Pares inglés → español de NeoForge (su es_es, traducido por su comunidad)."""
    with Instancia(instancia) as inst:
        jar = loader.jar_del_loader(loader.buscar_librerias(inst.juego), inst.loader, inst.version.texto)
    if jar is None:
        return []
    casos: list[Caso] = []
    for por_idioma in loader.leer_idiomas(jar).values():
        en, es = por_idioma.get("en_us", {}), por_idioma.get("es_es", {})
        for clave, ingles in en.items():
            ref = es.get(clave, "")
            if ref and ref != ingles and len(ingles) > 3:
                casos.append({"ambito": "ui", "original": ingles, "referencia": ref, "pista": loader.PISTA})
    return casos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True)
    args = ap.parse_args()
    azar = random.Random(7)
    con_shaders = [CORPUS / n for n in ("ftb-125", "modrinth-cobbleverse", "modrinth-legacies",
                                         "modrinth-lost-world-the-broken-script")]  # fmt: skip
    con_fancymenu = [CORPUS / n for n in ("modrinth-prominence-2-fabric", "modrinth-better-mc-forge-bmc4", "ftb-130")]
    con_descripciones = [CORPUS / "modrinth-cobbleverse", CORPUS / "ftb-125"]
    con_origins = [CORPUS / "modrinth-ultimate-origins-modpack", CORPUS / "modrinth-osmp"]
    grupos: dict[str, list[Caso]] = {
        "shaders": _shaders_con_referencia(con_shaders),
        "loader": _loader_con_referencia(PRISM / "audit-modrinth-create.ultimate"),
        "descripciones": _sin_referencia(descripciones.Descripciones, con_descripciones),
        "origins": _sin_referencia(origins.Origins, con_origins),
        "fancymenu": _sin_referencia(fancymenu.FancyMenu, con_fancymenu),
    }
    textos: list[Caso] = []
    grupo_de: dict[str, str] = {}
    for nombre, casos in grupos.items():
        elegidos = azar.sample(casos, min(TOPE, len(casos)))
        textos += elegidos
        grupo_de.update({c["original"]: nombre for c in elegidos})
        sys.stdout.buffer.write(f"{nombre}: {len(elegidos)} de {len(casos)}\n".encode())
    banco: dict[str, Any] = {"descripcion": "Fuentes nuevas de la auditoría de cobertura", "dialecto": "es_mx",
                             "glosario": {}, "textos": textos}  # fmt: skip
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(banco, ensure_ascii=False, indent=1), encoding="utf-8")
    grupos_ruta = args.salida.with_name(args.salida.stem + ".grupos.json")
    grupos_ruta.write_text(json.dumps(grupo_de, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Hoja para que una persona revise ~100 traducciones y marque cuáles están bien (salida SOLO local).

Dos pasos:
  1. `banco`: junta una muestra de .descargas/banco/ui_final.json (interfaz de mods) y .descargas/banco/misiones.json
     en .descargas/banco/hoja.json, para traducirla con `medir_calidad.py --banco ... --n-ejemplos 0`.
  2. `html`: con el resultado de esa medición arma una página (build/hoja_revision.html) donde se marca cada texto como
     «Bien», «Leve» o «Grave». El progreso se guarda en el navegador y el botón «Copiar resultados» deja un resumen
     corto en el portapapeles para pegarlo en el chat.

Los textos son de terceros: ni el banco ni la página van al repositorio (docs/datos-de-terceros.md).

Uso:  uv run python scripts/hoja_revision.py banco [--ui 60] [--misiones 40]
      uv run python scripts/hoja_revision.py html --entrada build/hoja.json
"""

# ruff: noqa: E501  (la plantilla de la página lleva líneas largas de HTML y CSS)
from __future__ import annotations

import argparse
import html
import json
import random
import sys
from pathlib import Path
from typing import Any

import descargar_corpus as dc

RAIZ = Path(__file__).resolve().parent.parent


def _banco(args: argparse.Namespace) -> int:
    azar = random.Random(2026)
    ui: dict[str, Any] = json.loads((dc.RAIZ / "banco" / "ui_final.json").read_text(encoding="utf-8"))
    mis: dict[str, Any] = json.loads((dc.RAIZ / "banco" / "misiones.json").read_text(encoding="utf-8"))
    nombres = [t for t in ui["textos"] if len(t["original"].split()) <= 3]
    frases = [t for t in ui["textos"] if len(t["original"].split()) >= 5]
    mitad = args.ui // 2
    elegidos = azar.sample(nombres, min(mitad, len(nombres))) + azar.sample(frases, min(args.ui - mitad, len(frases)))
    elegidos += azar.sample(mis["textos"], min(args.misiones, len(mis["textos"])))
    azar.shuffle(elegidos)
    banco = {
        "descripcion": "Muestra para revisión humana; solo uso local (no se publica).",
        "dialecto": ui["dialecto"],
        "glosario": ui["glosario"],
        "textos": [{**t, "referencia": ""} for t in elegidos],  # sin referencia: se juzga a mano
    }
    destino = dc.RAIZ / "banco" / "hoja.json"
    destino.write_text(json.dumps(banco, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(elegidos)} textos en {destino}")
    return 0


_PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hoja de revisión</title>
<style>
:root{--fondo:#fafaf7;--tarjeta:#fff;--texto:#1f2328;--suave:#656d76;--borde:#d8dee4;--bien:#1a7f37;--leve:#9a6700;--grave:#cf222e;--acento:#0969da}
@media(prefers-color-scheme:dark){:root{--fondo:#0d1117;--tarjeta:#161b22;--texto:#e6edf3;--suave:#8b949e;--borde:#30363d;--bien:#3fb950;--leve:#d29922;--grave:#f85149;--acento:#58a6ff}}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--texto);font:16px/1.5 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
header{position:sticky;top:0;background:var(--fondo);padding:12px 0;border-bottom:1px solid var(--borde);z-index:2}
h1{font-size:1.2rem;margin:0 0 4px}.sub{color:var(--suave);font-size:.9rem;margin:0 0 8px}
.barra{height:8px;background:var(--borde);border-radius:4px;overflow:hidden}.barra>i{display:block;height:100%;background:var(--acento);width:0}
.resumen{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;font-size:.9rem}
.tarjeta{background:var(--tarjeta);border:1px solid var(--borde);border-radius:10px;padding:14px;margin:14px 0}
.tarjeta.hecha{opacity:.85}.n{color:var(--suave);font-size:.8rem}
.en,.es{margin:6px 0;padding:8px 10px;border-radius:6px;white-space:pre-wrap;word-break:break-word}
.en{background:color-mix(in srgb,var(--borde) 40%,transparent)}.es{border-left:3px solid var(--acento)}
.ctx{color:var(--suave);font-size:.8rem;margin:4px 0}
.botones{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--borde);background:var(--tarjeta);color:var(--texto);cursor:pointer;min-height:40px}
button[data-v=B].on{background:var(--bien);color:#fff;border-color:var(--bien)}
button[data-v=L].on{background:var(--leve);color:#fff;border-color:var(--leve)}
button[data-v=G].on{background:var(--grave);color:#fff;border-color:var(--grave)}
input.nota{width:100%;margin-top:8px;padding:8px;border:1px solid var(--borde);border-radius:6px;background:var(--fondo);color:var(--texto);font:inherit}
.fin{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:18px 0}
.fin .principal{background:var(--acento);color:#fff;border-color:var(--acento)}
</style></head><body><main>
<header><h1>Hoja de revisión</h1>
<p class="sub">Marca cada traducción: <b>Bien</b> (la dejarías tal cual), <b>Leve</b> (se entiende, pero la retocarías) o <b>Grave</b>
(cambia el sentido, está mal o quedó en inglés). Si dudas entre dos, elige la más estricta. Se guarda sola en este navegador.</p>
<div class="barra"><i id="progreso"></i></div><div class="resumen" id="resumen"></div></header>
<div id="lista"></div>
<div class="fin"><button class="principal" id="copiar">Copiar resultados</button><span id="aviso" class="sub"></span></div>
</main>
<script>
const DATOS = __DATOS__;
const CLAVE = "hoja_revision_v1";
let estado = {};
try { estado = JSON.parse(localStorage.getItem(CLAVE) || "{}"); } catch (e) {}
const guardar = () => { try { localStorage.setItem(CLAVE, JSON.stringify(estado)); } catch (e) {} };
const lista = document.getElementById("lista");
DATOS.forEach((d, i) => {
  const t = document.createElement("section"); t.className = "tarjeta"; t.id = "t" + i;
  const h = (s) => s.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  t.innerHTML = `<div class="n">${i + 1} de ${DATOS.length} · ${d.tipo}</div>
    <div class="ctx">${h(d.contexto)}</div>
    <div class="en" lang="en">${h(d.original)}</div>
    <div class="es" lang="es">${h(d.traduccion)}</div>
    <div class="botones">
      <button data-v="B">Bien</button><button data-v="L">Leve</button><button data-v="G">Grave</button>
    </div>
    <input class="nota" placeholder="Nota (opcional): qué debería decir" aria-label="Nota">`;
  const nota = t.querySelector(".nota");
  nota.value = (estado[i] && estado[i].n) || "";
  nota.addEventListener("input", () => { estado[i] = {...(estado[i] || {}), n: nota.value}; guardar(); });
  t.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    estado[i] = {...(estado[i] || {}), v: b.dataset.v}; guardar(); pintar(); }));
  lista.appendChild(t);
});
function pintar() {
  let b = 0, l = 0, g = 0;
  DATOS.forEach((_, i) => {
    const v = (estado[i] || {}).v, t = document.getElementById("t" + i);
    t.classList.toggle("hecha", !!v);
    t.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === v));
    if (v === "B") b++; else if (v === "L") l++; else if (v === "G") g++;
  });
  const hechas = b + l + g;
  document.getElementById("progreso").style.width = (100 * hechas / DATOS.length) + "%";
  document.getElementById("resumen").innerHTML =
    `<span>${hechas} de ${DATOS.length}</span><span style="color:var(--bien)">Bien ${b}</span>` +
    `<span style="color:var(--leve)">Leve ${l}</span><span style="color:var(--grave)">Grave ${g}</span>`;
}
document.getElementById("copiar").addEventListener("click", async () => {
  const filas = DATOS.map((d, i) => {
    const e = estado[i] || {};
    return `${i + 1}:${e.v || "-"}${e.n ? " (" + e.n.replace(/\\s+/g, " ") + ")" : ""}`;
  });
  const texto = "HOJA " + DATOS.length + "\\n" + filas.join("\\n");
  try { await navigator.clipboard.writeText(texto); document.getElementById("aviso").textContent = "Copiado: pégalo en el chat."; }
  catch (e) { window.prompt("Copia este texto y pégalo en el chat:", texto); }
});
pintar();
</script></body></html>
"""


def _html(args: argparse.Namespace) -> int:
    datos: list[dict[str, Any]] = json.loads(args.entrada.read_text(encoding="utf-8"))
    filas = []
    for t in datos[-1]["traducciones"]:
        tipo = "Misión" if t["ambito"] == "mision" else "Interfaz de un mod"
        filas.append(
            {
                "tipo": tipo,
                "contexto": html.unescape(t.get("pista", "")),
                "original": t["original"],
                "traduccion": t["traduccion"],
            }
        )
    pagina = _PLANTILLA.replace("__DATOS__", json.dumps(filas, ensure_ascii=False).replace("</", "<\\/"))
    destino = RAIZ / "build" / "hoja_revision.html"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")
    print(f"{len(filas)} textos en {destino}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="orden", required=True)
    b = sub.add_parser("banco", help="armar la muestra")
    b.add_argument("--ui", type=int, default=60)
    b.add_argument("--misiones", type=int, default=40)
    b.set_defaults(func=_banco)
    h = sub.add_parser("html", help="armar la página de revisión")
    h.add_argument("--entrada", type=Path, default=RAIZ / "build" / "hoja.json")
    h.set_defaults(func=_html)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

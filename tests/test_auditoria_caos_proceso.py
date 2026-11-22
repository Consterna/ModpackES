"""Caos durante una traducción completa: disco lleno en cada escritura y dos traducciones a la vez (H-037).

El disco lleno de verdad necesitaría un disco virtual (permisos de administrador): se simula con el `OSError`
`ENOSPC` que da Windows, en cada escritura posible. Después, con espacio, traducir y restaurar deben devolver los
originales byte a byte.
"""

from __future__ import annotations

import errno
import hashlib
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from traductor_es.fuentes import vanilla
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.memoria import Memoria
from traductor_es.proceso import Proceso

from . import fabrica


@pytest.fixture(autouse=True)
def _sin_juego_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)


def _modpack(base: Path) -> Path:
    juego = fabrica.prism(base, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench"}))
    for n in range(3):
        capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / f"c{n}.snbt"
        capitulo.parent.mkdir(parents=True, exist_ok=True)
        capitulo.write_text(f'{{ title: "Chapter {n}" description: ["Craft tool {n}."] }}', encoding="utf-8")
    script = juego / "kubejs" / "client_scripts" / "t.js"
    script.parent.mkdir(parents=True)
    script.write_text("ItemEvents.tooltip(e => { e.add('m:wrench', 'Rotates blocks') })\n", encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _huellas(juego: Path) -> dict[str, str]:
    """Huella de los archivos del modpack (no de lo que es de la app ni de options.txt, que no se restaura)."""
    return {
        p.relative_to(juego).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in juego.rglob("*")
        if p.is_file()
        and not p.relative_to(juego).as_posix().startswith(("traductor_es/", "resourcepacks/"))
        and p.name != "options.txt"
    }


def _disco_lleno_en(monkeypatch: pytest.MonkeyPatch, n: int) -> Callable[[], int]:
    cuenta = [0]
    originales = {nombre: getattr(Path, nombre) for nombre in ("write_bytes", "write_text")}

    def envolver(nombre: str) -> Callable[..., Any]:
        def nueva(self: Path, *args: Any, **kwargs: Any) -> Any:
            cuenta[0] += 1
            if cuenta[0] == n:
                raise OSError(errno.ENOSPC, "No queda espacio en el disco", str(self))
            return originales[nombre](self, *args, **kwargs)

        return nueva

    for nombre in originales:
        monkeypatch.setattr(Path, nombre, envolver(nombre))
    return lambda: cuenta[0]


def test_disco_lleno_en_cada_escritura_no_corrompe_y_luego_se_recupera(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sonda = _modpack(tmp_path / "sonda")
    contar = _disco_lleno_en(monkeypatch, 10**9)
    with Memoria(":memory:") as m, Proceso(sonda, Simulador(), memoria=m) as p:
        p.ejecutar()
    total = contar()
    monkeypatch.undo()
    monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
    assert total > 5
    for n in range(1, total + 1):
        juego = _modpack(tmp_path / f"corte{n}")
        antes = _huellas(juego)
        _disco_lleno_en(monkeypatch, n)
        try:
            with Memoria(":memory:") as m, Proceso(juego, Simulador(), memoria=m) as p:
                p.ejecutar()
        except OSError as e:
            assert e.errno == errno.ENOSPC or "espacio" in str(e), (n, e)
        monkeypatch.undo()
        monkeypatch.setattr(vanilla, "raices_de_lanzadores", list)
        # Con espacio otra vez: traducir y restaurar dejan cada archivo del modpack como estaba
        with Memoria(":memory:") as m, Proceso(juego, Simulador(), memoria=m) as p:
            p.ejecutar()
            p.restaurar()
        assert _huellas(juego) == antes, f"disco lleno en la escritura {n}"


def test_dos_traducciones_a_la_vez_sobre_la_misma_instancia(tmp_path: Path) -> None:
    """Como abrir la app dos veces y pulsar «Traducir» en las dos: después, restaurar devuelve los originales."""
    juego = _modpack(tmp_path)
    antes = _huellas(juego)
    errores: list[BaseException] = []

    def traducir() -> None:
        try:
            with Memoria(":memory:") as m, Proceso(juego, Simulador(), memoria=m) as p:
                p.ejecutar()
        except BaseException as e:
            errores.append(e)

    hilos = [threading.Thread(target=traducir) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=120)
    # Que una de las dos falle con un error de archivo es aceptable; que se pierda un original, no
    assert all(isinstance(e, OSError) for e in errores), errores
    with Memoria(":memory:") as m, Proceso(juego, Simulador(), memoria=m) as p:
        p.restaurar()
    assert _huellas(juego) == antes

"""Memoria de traducciones en SQLite: lo traducido una vez se reutiliza en cualquier modpack."""

from __future__ import annotations

import sqlite3
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from .mascara import enmascarar


@dataclass(frozen=True, slots=True)
class Coincidencia:
    origen: str
    ambito: str  #: «*» si es una corrección sin traducción previa en la memoria
    traduccion: str
    corregida: bool = False


def codigos_iguales(original: str, traduccion: str) -> bool:
    """Si la traducción conserva todos los códigos del original (%s, §a, $(l), enlaces…), en cualquier orden."""
    return Counter(enmascarar(original).tokens) == Counter(enmascarar(traduccion).tokens)


def _patron_like(texto: str) -> str:
    """Patrón de LIKE que busca el texto tal cual («%» y «_» no son comodines). Se usa con ESCAPE '!'."""
    return "%" + texto.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


class Memoria:
    """Guarda (texto original, dialecto, ámbito) → traducción.

    El ámbito separa el tono: una misión tutea al jugador y un nombre de objeto va en mayúscula inicial,
    así que el mismo texto puede traducirse distinto en cada ámbito.
    """

    def __init__(self, ruta: Path | str) -> None:
        self.ruta = Path(ruta) if str(ruta) != ":memory:" else None
        if self.ruta is not None:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(ruta), check_same_thread=False)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS traducciones (
                   origen TEXT NOT NULL, dialecto TEXT NOT NULL, ambito TEXT NOT NULL,
                   traduccion TEXT NOT NULL, motor TEXT NOT NULL, fecha TEXT NOT NULL,
                   PRIMARY KEY (origen, dialecto, ambito))"""
        )
        # Correcciones del usuario: un texto, una traducción en todos los ámbitos. Mandan sobre todo lo demás.
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS correcciones (
                   origen TEXT NOT NULL, dialecto TEXT NOT NULL, traduccion TEXT NOT NULL, fecha TEXT NOT NULL,
                   PRIMARY KEY (origen, dialecto))"""
        )
        self._db.commit()

    def obtener(self, origen: str, dialecto: str, ambito: str) -> str | None:
        with self._lock:
            fila = self._db.execute(
                "SELECT traduccion FROM traducciones WHERE origen=? AND dialecto=? AND ambito=?",
                (origen, dialecto, ambito),
            ).fetchone()
        return None if fila is None else str(fila[0])

    def guardar(self, pares: dict[str, str], dialecto: str, ambito: str, motor: str) -> None:
        if not pares:
            return
        fecha = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO traducciones VALUES (?, ?, ?, ?, ?, ?)",
                [(o, dialecto, ambito, t, motor, fecha) for o, t in pares.items()],
            )
            self._db.commit()

    def olvidar(self, origen: str, dialecto: str, ambito: str) -> None:
        with self._lock:
            self._db.execute(
                "DELETE FROM traducciones WHERE origen=? AND dialecto=? AND ambito=?", (origen, dialecto, ambito)
            )
            self._db.commit()

    # ------------------------------------------------------------------ correcciones
    def corregir(self, origen: str, dialecto: str, traduccion: str) -> None:
        """Guarda una corrección. Lanza ValueError si está vacía o pierde o cambia códigos del original."""
        traduccion = traduccion.strip()
        if not traduccion:
            raise ValueError("La corrección está vacía.")
        if not codigos_iguales(origen, traduccion):
            raise ValueError(
                "La corrección tiene que conservar todos los códigos del original (%s, §a, $(…), enlaces…)."
            )
        fecha = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO correcciones VALUES (?, ?, ?, ?)", (origen, dialecto, traduccion, fecha)
            )
            self._db.commit()

    def correcciones(self, dialecto: str) -> dict[str, str]:
        """Todas las correcciones de una variante: {original: traducción}."""
        with self._lock:
            filas = self._db.execute(
                "SELECT origen, traduccion FROM correcciones WHERE dialecto=?", (dialecto,)
            ).fetchall()
        return {str(o): str(t) for o, t in filas}

    def correccion(self, origen: str, dialecto: str) -> str | None:
        with self._lock:
            fila = self._db.execute(
                "SELECT traduccion FROM correcciones WHERE origen=? AND dialecto=?", (origen, dialecto)
            ).fetchone()
        return None if fila is None else str(fila[0])

    def quitar_correccion(self, origen: str, dialecto: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM correcciones WHERE origen=? AND dialecto=?", (origen, dialecto))
            self._db.commit()

    def buscar(self, texto: str, dialecto: str, limite: int = 200) -> list[Coincidencia]:
        """Textos cuyo original o traducción contiene `texto` (sin distinguir mayúsculas). Vacío: las correcciones."""
        buscado = texto.strip()
        with self._lock:
            # Las correcciones son pocas (las escribe el usuario): se cargan todas para marcar cada resultado
            corregidas = {
                str(o): str(t)
                for o, t in self._db.execute(
                    "SELECT origen, traduccion FROM correcciones WHERE dialecto=? ORDER BY origen", (dialecto,)
                )
            }
            filas = (
                self._db.execute(
                    "SELECT origen, ambito, traduccion FROM traducciones WHERE dialecto=? "
                    "AND (origen LIKE ? ESCAPE '!' OR traduccion LIKE ? ESCAPE '!') ORDER BY origen, ambito LIMIT ?",
                    (dialecto, _patron_like(buscado), _patron_like(buscado), limite),
                ).fetchall()
                if buscado
                else []
            )
        vistos: set[str] = set()
        salida: list[Coincidencia] = []
        for o, a, t in filas:
            origen = str(o)
            vistos.add(origen)
            corregida = corregidas.get(origen)
            salida.append(Coincidencia(origen, str(a), corregida or str(t), corregida is not None))
        bajo = buscado.casefold()
        salida += [
            Coincidencia(o, "*", t, True)
            for o, t in corregidas.items()
            if o not in vistos and (bajo in o.casefold() or bajo in t.casefold())
        ]
        return salida[:limite]

    def cantidad(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM traducciones").fetchone()[0])

    def cerrar(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, tipo: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.cerrar()

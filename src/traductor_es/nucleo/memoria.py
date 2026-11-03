"""Memoria de traducciones en SQLite: lo traducido una vez se reutiliza en cualquier modpack."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self


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

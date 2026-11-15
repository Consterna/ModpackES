"""Memoria de traducciones en SQLite: lo traducido una vez se reutiliza en el mismo modpack y, si quedó bien, en
cualquier otro."""

from __future__ import annotations

import shutil
import sqlite3
import threading
from collections import Counter
from collections.abc import Iterable, Mapping
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


@dataclass(frozen=True, slots=True)
class Fila:
    """Una traducción de la memoria tal como se comparte en un paquete."""

    origen: str
    ambito: str
    traduccion: str
    motor: str
    calidad: str = "ok"  #: «ok» o por qué se aceptó con dudas


#: Pack de lo que no es de ningún modpack en particular (lo de antes del esquema 2, las pruebas, las mediciones).
SIN_PACK = "*"
#: Calidad de una traducción que pasó todas las reglas.
OK = "ok"
_LARGO_CALIDAD = 200
#: Versión del esquema de la base (PRAGMA user_version).
ESQUEMA = 2


def codigos_iguales(original: str, traduccion: str) -> bool:
    """Si la traducción conserva todos los códigos del original (%s, §a, $(l), enlaces…), en cualquier orden."""
    return Counter(enmascarar(original).tokens) == Counter(enmascarar(traduccion).tokens)


def _patron_like(texto: str) -> str:
    """Patrón de LIKE que busca el texto tal cual («%» y «_» no son comodines). Se usa con ESCAPE '!'."""
    return "%" + texto.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


class Memoria:
    """Guarda (texto original, dialecto, ámbito, pack) → traducción, con su calidad.

    El ámbito separa el tono: una misión tutea al jugador y un nombre de objeto va en mayúscula inicial,
    así que el mismo texto puede traducirse distinto en cada ámbito.

    El pack separa los modpacks: una traducción se reutiliza siempre en el pack que la hizo, y en otro pack solo si
    pasó todas las reglas (calidad «ok»). Lo aceptado con dudas en un pack no se lleva a los demás.
    """

    def __init__(self, ruta: Path | str) -> None:
        self.ruta = Path(ruta) if str(ruta) != ":memory:" else None
        if self.ruta is not None:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(ruta), check_same_thread=False)
        try:
            self._crear_tablas()
        except sqlite3.Error:  # archivo dañado o bloqueado: no se deja la conexión abierta
            self._db.close()
            raise

    def _crear_tablas(self) -> None:
        columnas = [str(c[1]) for c in self._db.execute("PRAGMA table_info(traducciones)")]
        if columnas and "pack" not in columnas:
            self._migrar_a_v2()
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS traducciones (
                   origen TEXT NOT NULL, dialecto TEXT NOT NULL, ambito TEXT NOT NULL, pack TEXT NOT NULL,
                   traduccion TEXT NOT NULL, motor TEXT NOT NULL, fecha TEXT NOT NULL, calidad TEXT NOT NULL,
                   PRIMARY KEY (origen, dialecto, ambito, pack))"""
        )
        self._db.execute(f"PRAGMA user_version = {ESQUEMA}")
        # Correcciones del usuario: un texto, una traducción en todos los ámbitos. Mandan sobre todo lo demás.
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS correcciones (
                   origen TEXT NOT NULL, dialecto TEXT NOT NULL, traduccion TEXT NOT NULL, fecha TEXT NOT NULL,
                   PRIMARY KEY (origen, dialecto))"""
        )
        self._db.commit()

    def _migrar_a_v2(self) -> None:
        """Esquema 1 → 2 sin perder nada: guarda una copia del archivo y pasa cada fila al pack «*» con calidad «ok»
        (no se sabe con qué pack ni con qué dudas se hizo, y así se sigue usando como antes)."""
        if self.ruta is not None and self.ruta.is_file():
            shutil.copy2(self.ruta, self.ruta.with_name(self.ruta.name + ".v1.bak"))
        self._db.execute("BEGIN")  # una sola transacción, también para el ALTER: o se migra todo o nada
        try:
            self._db.execute("ALTER TABLE traducciones RENAME TO traducciones_v1")
            self._db.execute(
                """CREATE TABLE traducciones (
                       origen TEXT NOT NULL, dialecto TEXT NOT NULL, ambito TEXT NOT NULL, pack TEXT NOT NULL,
                       traduccion TEXT NOT NULL, motor TEXT NOT NULL, fecha TEXT NOT NULL, calidad TEXT NOT NULL,
                       PRIMARY KEY (origen, dialecto, ambito, pack))"""
            )
            self._db.execute(
                "INSERT INTO traducciones SELECT origen, dialecto, ambito, ?, traduccion, motor, fecha, ? "
                "FROM traducciones_v1",
                (SIN_PACK, OK),
            )
            self._db.execute("DROP TABLE traducciones_v1")
        except sqlite3.Error:
            self._db.rollback()
            raise
        self._db.commit()

    def fila(self, origen: str, dialecto: str, ambito: str, pack: str = SIN_PACK) -> tuple[str, str] | None:
        """(traducción, calidad) que vale para este pack: la suya; si no tiene, la más reciente de otro que quedó
        «ok». None si no hay ninguna."""
        with self._lock:
            fila = self._db.execute(
                "SELECT traduccion, calidad FROM traducciones WHERE origen=? AND dialecto=? AND ambito=? "
                "AND (pack=? OR calidad=?) ORDER BY pack=? DESC, fecha DESC LIMIT 1",
                (origen, dialecto, ambito, pack, OK, pack),
            ).fetchone()
        return None if fila is None else (str(fila[0]), str(fila[1]))

    def obtener(self, origen: str, dialecto: str, ambito: str, pack: str = SIN_PACK) -> str | None:
        hallada = self.fila(origen, dialecto, ambito, pack)
        return None if hallada is None else hallada[0]

    def guardar(
        self,
        pares: Mapping[str, str],
        dialecto: str,
        ambito: str,
        motor: str,
        pack: str = SIN_PACK,
        dudas: Mapping[str, str] | None = None,
    ) -> None:
        """Guarda traducciones del pack; las que están en `dudas` ({original: motivo}) quedan marcadas con su motivo."""
        if not pares:
            return
        fecha = datetime.now(UTC).isoformat(timespec="seconds")
        dudas = dudas or {}
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO traducciones VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (o, dialecto, ambito, pack, t, motor, fecha, (dudas.get(o) or OK)[:_LARGO_CALIDAD])
                    for o, t in pares.items()
                ],
            )
            self._db.commit()

    def recientes(self, dialecto: str, limite: int = 50_000) -> dict[str, str]:
        """{original: traducción} de lo último traducido en este dialecto; las correcciones mandan."""
        with self._lock:
            filas = self._db.execute(
                "SELECT origen, traduccion FROM traducciones WHERE dialecto=? ORDER BY fecha DESC LIMIT ?",
                (dialecto, limite),
            ).fetchall()
        salida: dict[str, str] = {}
        for o, t in filas:  # de la más nueva a la más vieja: si un texto está en varios packs, gana la última
            salida.setdefault(str(o), str(t))
        salida.update(self.correcciones(dialecto))
        return salida

    def filas(self, buscadas: Iterable[tuple[str, str]], dialecto: str, pack: str = SIN_PACK) -> list[Fila]:
        """Las traducciones que valen para el pack de esos pares (original, ámbito), con el motor y la calidad."""
        salida: list[Fila] = []
        with self._lock:
            for origen, ambito in sorted(set(buscadas)):
                fila = self._db.execute(
                    "SELECT traduccion, motor, calidad FROM traducciones WHERE origen=? AND dialecto=? AND ambito=? "
                    "AND (pack=? OR calidad=?) ORDER BY pack=? DESC, fecha DESC LIMIT 1",
                    (origen, dialecto, ambito, pack, OK, pack),
                ).fetchone()
                if fila is not None:
                    salida.append(Fila(origen, ambito, str(fila[0]), str(fila[1]), str(fila[2])))
        return salida

    def importar(self, filas: Iterable[Fila], dialecto: str, pack: str = SIN_PACK) -> int:
        """Guarda traducciones de otra memoria en el pack (reemplaza las que ya tuviera). Devuelve cuántas guardó."""
        fecha = datetime.now(UTC).isoformat(timespec="seconds")
        lista = [
            (f.origen, dialecto, f.ambito, pack, f.traduccion, f.motor, fecha, (f.calidad or OK)[:_LARGO_CALIDAD])
            for f in filas
        ]
        with self._lock:
            self._db.executemany("INSERT OR REPLACE INTO traducciones VALUES (?, ?, ?, ?, ?, ?, ?, ?)", lista)
            self._db.commit()
        return len(lista)

    def olvidar(self, origen: str, dialecto: str, ambito: str) -> None:
        """Borra ese texto de la memoria en todos los packs."""
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
        pares: set[tuple[str, str]] = set()
        salida: list[Coincidencia] = []
        for o, a, t in filas:
            origen = str(o)
            if (origen, str(a)) in pares:  # el mismo texto en varios packs: se muestra una vez
                continue
            pares.add((origen, str(a)))
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
        """Cuántos textos distintos hay (el mismo texto en varios packs cuenta una vez)."""
        with self._lock:
            return int(
                self._db.execute(
                    "SELECT COUNT(*) FROM (SELECT DISTINCT origen, dialecto, ambito FROM traducciones)"
                ).fetchone()[0]
            )

    def cerrar(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, tipo: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.cerrar()

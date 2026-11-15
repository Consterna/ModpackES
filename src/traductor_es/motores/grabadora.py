"""Grabar y reproducir las respuestas de un motor, para medir cambios del proceso sin el ruido del modelo.

Gemini no responde igual dos veces (en el banco de interfaz, dos corridas coinciden en ~67 % de los textos), así que
al comparar dos versiones del proceso la variación del modelo tapa el efecto del cambio. `MotorGrabado` envuelve a
un motor y guarda en SQLite la respuesta a cada pedido, con la clave del pedido exacto (instrucciones y textos). Si
el pedido se repite, la respuesta sale de la grabación, sin costo y siempre igual. Un cambio que solo toca lo que se
hace después del modelo (controles, arreglos) se mide así contra las mismas respuestas.

Solo es una herramienta de medición: la app no la usa.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, cast

from .base import Lote, Motor
from .instrucciones import sistema, usuario


def clave_del_pedido(motor: str, lote: Lote, repeticion: int = 0) -> str:
    """Huella del pedido: el mismo motor, las mismas instrucciones y los mismos textos dan la misma clave."""
    datos = "\x00".join((str(repeticion), motor, sistema(lote), usuario(lote)))
    return hashlib.sha256(datos.encode("utf-8")).hexdigest()


class MotorGrabado:
    """Un motor cuyas respuestas se graban y se reutilizan.

    `repeticion` separa corridas que deben ser independientes (la 1.ª, la 2.ª…): cada una tiene su propia grabación.
    Con `solo_grabado`, un pedido que no está grabado no va a la API: se devuelve vacío (el texto se rechaza, como si
    el motor no hubiera respondido) y se cuenta en `faltantes`.
    """

    def __init__(self, motor: Motor, ruta: Path, repeticion: int = 0, solo_grabado: bool = False) -> None:
        self.envuelto = motor
        self.repeticion = repeticion
        self.solo_grabado = solo_grabado
        self.aciertos = 0  #: respuestas que salieron de la grabación
        self.pedidos = 0  #: respuestas que se pidieron al motor (y se grabaron)
        self.faltantes = 0  #: pedidos sin grabación con `solo_grabado`
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(ruta, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS respuestas (clave TEXT PRIMARY KEY, salida TEXT NOT NULL)")
        self._db.commit()

    @property
    def nombre(self) -> str:
        return self.envuelto.nombre

    @property
    def uso(self) -> list[int] | None:
        """Tokens de entrada y salida que el motor real facturó (lo grabado no cuenta)."""
        return cast("list[int] | None", getattr(self.envuelto, "uso", None))

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        clave = clave_del_pedido(self.nombre, lote, self.repeticion)
        with self._lock:
            fila = self._db.execute("SELECT salida FROM respuestas WHERE clave=?", (clave,)).fetchone()
        if fila is not None:
            self.aciertos += 1
            datos: Any = json.loads(str(fila[0]))
            return {str(k): str(v) for k, v in cast("dict[str, Any]", datos).items()}
        if self.solo_grabado:
            self.faltantes += 1
            return {}
        salida = self.envuelto.traducir_lote(lote)
        if salida:  # una respuesta vacía (error de red, cuota) no se graba: la próxima vez se vuelve a pedir
            with self._lock:
                self._db.execute(
                    "INSERT OR REPLACE INTO respuestas (clave, salida) VALUES (?, ?)",
                    (clave, json.dumps(salida, ensure_ascii=False)),
                )
                self._db.commit()
        self.pedidos += 1
        return salida

    def cerrar(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> MotorGrabado:
        return self

    def __exit__(self, *_: object) -> None:
        self.cerrar()

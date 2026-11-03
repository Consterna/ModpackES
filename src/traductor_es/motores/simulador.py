"""Motor falso para probar todo sin gastar: antepone «ES» y, si se pide, daña textos a propósito.

Para probar la revisión: marca como «grave» las traducciones de `marcar` y, cuando una pista pide corregir, antepone
«ES*» en vez de «ES».
"""

from __future__ import annotations

import random
import threading

from .base import Lote


class Simulador:
    def __init__(
        self, prefijo: str = "«ES» ", danar: float = 0.0, semilla: int = 0, marcar: frozenset[str] = frozenset()
    ) -> None:
        self.prefijo = prefijo
        self.danar = danar
        self.marcar = marcar
        self._azar = random.Random(semilla)
        self._lock = threading.Lock()
        self.lotes_recibidos: list[Lote] = []

    @property
    def nombre(self) -> str:
        return "simulador"

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        with self._lock:
            self.lotes_recibidos.append(lote)
            if lote.tarea == "revisar":
                return {
                    e.id: "grave|exactitud|marcado por la prueba" if e.traduccion in self.marcar else "OK"
                    for e in lote.entradas
                }
            salida: dict[str, str] = {}
            for e in lote.entradas:
                prefijo = "«ES*» " if "revisión" in e.pista else self.prefijo
                if self.danar and self._azar.random() < self.danar:
                    salida[e.id] = prefijo + e.texto.replace("⟦0⟧", "")  # pierde un marcador
                else:
                    salida[e.id] = prefijo + e.texto
            return salida

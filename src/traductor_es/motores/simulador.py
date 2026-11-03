"""Motor falso para probar todo sin gastar: antepone «ES» y, si se pide, daña textos a propósito."""

from __future__ import annotations

import random
import threading

from .base import Lote


class Simulador:
    def __init__(self, prefijo: str = "«ES» ", danar: float = 0.0, semilla: int = 0) -> None:
        self.prefijo = prefijo
        self.danar = danar
        self._azar = random.Random(semilla)
        self._lock = threading.Lock()
        self.lotes_recibidos: list[Lote] = []

    @property
    def nombre(self) -> str:
        return "simulador"

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        with self._lock:
            self.lotes_recibidos.append(lote)
            salida: dict[str, str] = {}
            for e in lote.entradas:
                if self.danar and self._azar.random() < self.danar:
                    salida[e.id] = self.prefijo + e.texto.replace("⟦0⟧", "")  # pierde un marcador
                else:
                    salida[e.id] = self.prefijo + e.texto
            return salida

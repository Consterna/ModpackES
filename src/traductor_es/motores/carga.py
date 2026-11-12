"""Carga segura para los motores que corren en el PC: pausas entre pedidos y vigilancia de la temperatura de la GPU.

Un modelo local puede dejar la tarjeta gráfica al máximo durante minutos. Esto no cambia ningún ajuste del sistema:
solo hace que la app espere un poco entre pedidos (ciclo de trabajo) y se detenga mientras la GPU esté muy caliente.
La temperatura se lee con `nvidia-smi` (solo lectura); sin una GPU de NVIDIA no se vigila nada y solo valen las pausas.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from collections.abc import Callable

#: Fracción del tiempo que el motor puede trabajar (0,7 = 70 % trabajando y 30 % descansando).
CICLO_POR_DEFECTO = 0.7
TEMPERATURA_MAXIMA = 80
ESPERA_MAXIMA = 180.0
_SONDEO = 5.0


def temperatura_gpu() -> int | None:
    """Temperatura (°C) de la GPU más caliente, o None si no hay `nvidia-smi` o no responde."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        salida = subprocess.run(
            [exe, "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
        return max(int(float(linea)) for linea in salida.split() if linea.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class Enfriador:
    """Pausas entre pedidos y espera si la GPU pasa de `maxima` grados. Seguro para varios hilos."""

    def __init__(
        self,
        ciclo: float = CICLO_POR_DEFECTO,
        maxima: int = TEMPERATURA_MAXIMA,
        espera_maxima: float = ESPERA_MAXIMA,
        leer: Callable[[], int | None] = temperatura_gpu,
        dormir: Callable[[float], None] | None = None,
        aviso: Callable[[str], None] = lambda _m: None,
    ) -> None:
        if not 0.1 <= ciclo <= 1.0:
            raise ValueError("El ciclo de trabajo va de 0,1 a 1.")
        self.ciclo = ciclo
        self.maxima = maxima
        self._espera_maxima = espera_maxima
        self._leer = leer
        self._dormir = dormir
        self._aviso = aviso
        self.pausas = 0.0  #: segundos totales de descanso (para informar)
        #: Si se activa, las pausas terminan enseguida (el motor la comparte con el trabajo en curso)
        self.cancelar: threading.Event | None = None

    def _cancelado(self) -> bool:
        return self.cancelar is not None and self.cancelar.is_set()

    def _pausa(self, segundos: float) -> None:
        if self._dormir is not None:
            self._dormir(segundos)
        elif self.cancelar is not None:
            self.cancelar.wait(segundos)
        else:
            time.sleep(segundos)

    def antes(self) -> None:
        """Espera mientras la GPU esté demasiado caliente, hasta `espera_maxima` segundos."""
        esperado = 0.0
        while esperado < self._espera_maxima and not self._cancelado():
            temperatura = self._leer()
            if temperatura is None or temperatura < self.maxima:
                return
            if esperado == 0.0:
                self._aviso(f"La GPU está a {temperatura} °C: espero a que baje de {self.maxima} °C.")
            self._pausa(_SONDEO)
            esperado += _SONDEO
            self.pausas += _SONDEO

    def despues(self, duracion: float) -> None:
        """Descansa en proporción a lo que duró el pedido para cumplir el ciclo de trabajo."""
        if self.ciclo >= 1.0 or duracion <= 0 or self._cancelado():
            return
        pausa = duracion * (1 - self.ciclo) / self.ciclo
        self._pausa(pausa)
        self.pausas += pausa

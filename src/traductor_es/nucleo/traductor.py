"""Orquestador: deduplica, consulta memoria y glosario, arma lotes, valida y guarda."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import cast

from ..motores.base import Cancelado, Entrada, Lote, Motor, MotorPorLotes
from .dialectos import DIALECTO_POR_DEFECTO, DIALECTOS
from .glosario import Glosario
from .mascara import Enmascarado, desenmascarar, enmascarar, es_traducible, separar_bordes
from .memoria import Memoria

Progreso = Callable[[int, int], None]
Registro = Callable[[str], None]
#: Recibe (original, traducción) y devuelve el motivo del rechazo, o None si es válida.
Validador = Callable[[str, str], str | None]


def _nada(*_: object) -> None:
    return None


@dataclass(slots=True)
class Resultado:
    traducciones: dict[str, str] = field(default_factory=dict[str, str])
    rechazados: dict[str, str] = field(default_factory=dict[str, str])  #: original → motivo
    enviados: int = 0


class Traductor:
    def __init__(
        self,
        motor: Motor,
        memoria: Memoria,
        glosario: Glosario,
        dialecto: str = DIALECTO_POR_DEFECTO,
        hilos: int = 4,
        progreso: Progreso = _nada,
        registro: Registro = _nada,
        cancelar: threading.Event | None = None,
        validador: Validador | None = None,
        limite_caracteres: int = 5000,
        limite_entradas: int = 60,
        usar_lotes: bool = False,
    ) -> None:
        if dialecto not in DIALECTOS:
            raise ValueError(f"Dialecto desconocido: {dialecto}")
        self.motor = motor
        self.memoria = memoria
        self.glosario = glosario
        self.dialecto = dialecto
        self.hilos = max(1, hilos)
        self.progreso = progreso
        self.registro = registro
        self.cancelar = cancelar or threading.Event()
        self.validador = validador
        self.limite_caracteres = limite_caracteres
        self.limite_entradas = limite_entradas
        #: Mandar cada ronda en un solo trabajo de la Batch API (si el motor lo admite): más barato, más lento
        self.usar_lotes = usar_lotes and hasattr(motor, "traducir_varios")
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ consulta
    def _conocida(self, nucleo: str, ambito: str) -> str | None:
        """Lo que el usuario corrigió o fijó manda; después, lo ya traducido; después, los nombres oficiales."""
        return (
            self.memoria.correccion(nucleo, self.dialecto)
            or self.glosario.fijo(nucleo)
            or self.memoria.obtener(nucleo, self.dialecto, ambito)
            or self.glosario.exacto(nucleo)
        )

    def pendientes(self, textos: Iterable[str], ambito: str) -> list[str]:
        """Núcleos únicos que habría que mandar al motor (lo demás sale de memoria o glosario)."""
        vistos: set[str] = set()
        for t in textos:
            if es_traducible(t):
                nucleo = separar_bordes(t)[1]
                if nucleo not in vistos and self._conocida(nucleo, ambito) is None:
                    vistos.add(nucleo)
        return sorted(vistos)

    # ------------------------------------------------------------------ traducción
    def traducir(self, textos: Iterable[str], ambito: str, pistas: Mapping[str, str] | None = None) -> Resultado:
        """Traduce y devuelve {texto original: traducción}. Lo que no se pudo traducir con garantías no aparece."""
        # Las pistas se buscan por el núcleo (sin espacios de borde), igual que la memoria
        pistas = {separar_bordes(k)[1]: v for k, v in (pistas or {}).items()}
        resultado = Resultado()
        unicos = {t for t in textos if es_traducible(t)}
        faltan = self.pendientes(unicos, ambito)
        if faltan:
            nucleos = self._ronda(faltan, ambito, pistas, (self.limite_caracteres, self.limite_entradas), resultado)
            if nucleos and not self.cancelar.is_set():
                self.registro(f"Reintentando {len(nucleos)} textos que volvieron con códigos dañados…")
                resultado.rechazados.clear()
                # Lotes chicos y sin mover la barra de progreso, que ya llegó al total
                # (en modo normal aunque se use la Batch API: son pocos y no vale la pena esperar otro trabajo)
                self._ronda(sorted(nucleos), ambito, pistas, (1500, 5), resultado, informar=False, por_lotes=False)
            if resultado.rechazados:
                n = len(resultado.rechazados)
                self.registro(f"{n} textos se quedan en inglés porque no pasaron la validación.")
        for t in unicos:
            inicio, nucleo, fin = separar_bordes(t)
            hecho = self._conocida(nucleo, ambito)
            if hecho is not None:
                resultado.traducciones[t] = inicio + hecho + fin
        return resultado

    def _lotes(self, nucleos: list[str], lim_chars: int, lim_items: int) -> list[list[str]]:
        lotes: list[list[str]] = []
        actual: list[str] = []
        tam = 0
        for n in nucleos:
            if actual and (tam + len(n) > lim_chars or len(actual) >= lim_items):
                lotes.append(actual)
                actual, tam = [], 0
            actual.append(n)
            tam += len(n)
        if actual:
            lotes.append(actual)
        return lotes

    def _ronda(
        self,
        nucleos: list[str],
        ambito: str,
        pistas: Mapping[str, str],
        limites: tuple[int, int],
        resultado: Resultado,
        informar: bool = True,
        por_lotes: bool = True,
    ) -> set[str]:
        """Traduce una ronda. Devuelve los núcleos que fallaron."""
        fallidos: set[str] = set()
        hechos = 0
        total = len(nucleos)
        progreso = self.progreso if informar else _nada
        progreso(0, total)
        if self.usar_lotes and por_lotes:
            return self._ronda_por_lotes(self._lotes(nucleos, *limites), ambito, pistas, resultado, progreso)
        with ThreadPoolExecutor(self.hilos) as ex:
            futuros: dict[Future[dict[str, str]], list[str]] = {
                ex.submit(self._lote, lote, ambito, pistas, resultado): lote for lote in self._lotes(nucleos, *limites)
            }
            try:
                for fut in as_completed(futuros):
                    if self.cancelar.is_set():
                        raise Cancelado()
                    lote = futuros[fut]
                    buenos = fut.result()
                    self.memoria.guardar(buenos, self.dialecto, ambito, self.motor.nombre)
                    fallidos.update(n for n in lote if n not in buenos)
                    hechos += len(lote)
                    progreso(hechos, total)
            except BaseException:
                self.cancelar.set()
                ex.shutdown(wait=True, cancel_futures=True)
                raise
        return fallidos

    def _ronda_por_lotes(
        self,
        lotes: list[list[str]],
        ambito: str,
        pistas: Mapping[str, str],
        resultado: Resultado,
        progreso: Progreso,
    ) -> set[str]:
        pedidos = [self._pedido(lote, ambito, pistas) for lote in lotes]
        salidas = cast(MotorPorLotes, self.motor).traducir_varios([p for p, _ in pedidos])
        fallidos: set[str] = set()
        hechos = 0
        total = sum(len(lote) for lote in lotes)
        for lote, (_, mascaras), salida in zip(lotes, pedidos, salidas, strict=True):
            buenos = self._procesar(lote, mascaras, salida, resultado)
            self.memoria.guardar(buenos, self.dialecto, ambito, self.motor.nombre)
            fallidos.update(n for n in lote if n not in buenos)
            hechos += len(lote)
            progreso(hechos, total)
        return fallidos

    def _pedido(self, lote: list[str], ambito: str, pistas: Mapping[str, str]) -> tuple[Lote, list[Enmascarado]]:
        mascaras = [enmascarar(n) for n in lote]
        entradas = tuple(
            Entrada(str(i), m.texto, pistas.get(n, "")) for i, (n, m) in enumerate(zip(lote, mascaras, strict=True))
        )
        return Lote(entradas, ambito, DIALECTOS[self.dialecto], self.glosario.relevantes(lote)), mascaras

    def _lote(self, lote: list[str], ambito: str, pistas: Mapping[str, str], resultado: Resultado) -> dict[str, str]:
        if self.cancelar.is_set():
            return {}
        pedido, mascaras = self._pedido(lote, ambito, pistas)
        return self._procesar(lote, mascaras, self.motor.traducir_lote(pedido), resultado)

    def _procesar(
        self, lote: list[str], mascaras: list[Enmascarado], salida: Mapping[str, str], resultado: Resultado
    ) -> dict[str, str]:
        buenos: dict[str, str] = {}
        rechazados: dict[str, str] = {}
        for i, (n, m) in enumerate(zip(lote, mascaras, strict=True)):
            crudo = salida.get(str(i))
            if not isinstance(crudo, str) or not crudo.strip():
                rechazados[n] = "sin respuesta"
                continue
            final = desenmascarar(crudo.strip(), m.tokens)
            if final is None:
                rechazados[n] = "códigos dañados"
                continue
            motivo = self.validador(n, final) if self.validador else None
            if motivo:
                rechazados[n] = motivo
                continue
            buenos[n] = final
        with self._lock:
            resultado.enviados += len(lote)
            resultado.rechazados.update(rechazados)
        return buenos

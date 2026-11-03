"""Contrato común de los motores de traducción."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


class ErrorFatal(Exception):
    """Un error que no se arregla reintentando: clave inválida, modelo inexistente, cuota agotada."""


class Cancelado(Exception):
    """El usuario detuvo el trabajo."""


@dataclass(frozen=True, slots=True)
class Entrada:
    id: str
    texto: str  #: ya enmascarado
    pista: str = ""  #: contexto corto, p. ej. «item.create.wrench» o «misión: título»
    traduccion: str = ""  #: solo para revisar: la traducción que hay que juzgar (también enmascarada)


@dataclass(frozen=True, slots=True)
class Lote:
    entradas: tuple[Entrada, ...]
    ambito: str  #: «ui», «mision», «libro», «script»
    dialecto: str  #: descripción del dialecto destino
    glosario: dict[str, str] = field(default_factory=dict[str, str])
    contexto: str = ""  #: ambientación del modpack que escribe el usuario (tono, términos propios)
    tarea: str = "traducir"  #: «traducir» o «revisar» (juzgar traducciones ya hechas)


class Motor(Protocol):
    @property
    def nombre(self) -> str: ...

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        """Devuelve {id: traducción}. Puede omitir ids; nunca debe lanzar salvo ErrorFatal."""
        ...


class MotorPorLotes(Motor, Protocol):
    def traducir_varios(self, lotes: Sequence[Lote]) -> list[dict[str, str]]:
        """Traduce muchos lotes en un solo trabajo (p. ej. la Batch API). Devuelve una salida por lote."""
        ...

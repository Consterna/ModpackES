"""Contrato común de los motores de traducción."""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class Lote:
    entradas: tuple[Entrada, ...]
    ambito: str  #: «ui», «mision», «libro», «script»
    dialecto: str  #: descripción del dialecto destino
    glosario: dict[str, str] = field(default_factory=dict[str, str])


class Motor(Protocol):
    @property
    def nombre(self) -> str: ...

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        """Devuelve {id: traducción}. Puede omitir ids; nunca debe lanzar salvo ErrorFatal."""
        ...

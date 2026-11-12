"""Qué motores hay y cómo se crea cada uno, para la ventana y la línea de comandos."""

from __future__ import annotations

from .base import ErrorFatal, Motor
from .carga import Enfriador
from .compatible import PERFILES, Compatible
from .gemini import Gemini

GEMINI = "gemini"
#: id → nombre que ve el usuario, en el orden de la lista
MOTORES: dict[str, str] = {GEMINI: "Gemini (Google)", **{p.id: p.nombre for p in PERFILES.values()}}


def necesita_clave(motor: str) -> bool:
    return motor == GEMINI or (motor in PERFILES and PERFILES[motor].necesita_clave)


def es_local(motor: str) -> bool:
    return motor in PERFILES and PERFILES[motor].local


def direccion_por_defecto(motor: str) -> str:
    return PERFILES[motor].direccion if motor in PERFILES else ""


#: (caracteres, textos) por pedido. Un modelo local pequeño se equivoca más con pedidos largos.
LIMITES_NORMALES = (5000, 60)
LIMITES_LOCALES = (1800, 12)


def limites_de_lote(motor: Motor) -> tuple[int, int]:
    """Tamaño de los pedidos que conviene mandarle a este motor."""
    return LIMITES_LOCALES if isinstance(motor, Compatible) and motor.es_local else LIMITES_NORMALES


def crear(motor: str, clave: str | None, modelo: str, direccion: str = "", enfriador: Enfriador | None = None) -> Motor:
    """El motor elegido. Lanza ErrorFatal si falta algo para usarlo (clave, modelo o dirección)."""
    if motor == GEMINI:
        if not clave:
            raise ErrorFatal("Falta la clave de Gemini: guárdala con «Guardar clave…».")
        return Gemini(clave, modelo)
    if motor not in PERFILES:
        raise ErrorFatal(f"Motor desconocido: {motor}")
    perfil = PERFILES[motor]
    if perfil.necesita_clave and not clave:
        raise ErrorFatal(f"Falta la clave de {perfil.nombre}: guárdala con «Guardar clave…».")
    return Compatible(perfil, modelo, clave, direccion or None, enfriador=enfriador)

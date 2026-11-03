"""Preferencias y clave de API. La clave va al almacén de credenciales del sistema (en Windows, el
Administrador de credenciales), nunca a un archivo de texto.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any, cast

import keyring
import platformdirs
from keyring.errors import KeyringError

from . import registro

# Nombres internos de la v2.0 (antes de llamarse ModpackES): cambiarlos perdería la clave y la memoria guardadas.
SERVICIO = "traductor-es"
USUARIO_CLAVE = "gemini"


def carpeta_datos() -> Path:
    """Memoria, glosario y preferencias. TRADUCTOR_ES_DATOS la cambia (p. ej. para pruebas o modo portátil)."""
    if os.environ.get("TRADUCTOR_ES_DATOS"):
        return Path(os.environ["TRADUCTOR_ES_DATOS"])
    return platformdirs.user_data_path("traductor-es", appauthor=False)


def ruta_memoria() -> Path:
    return carpeta_datos() / "memoria.db"


def ruta_glosario_usuario() -> Path:
    """Términos del usuario: {"inglés": "traducción"} que mandan sobre todo lo demás."""
    return carpeta_datos() / "glosario.json"


def _usuario_de(motor: str) -> str:
    """Nombre de la clave en el almacén: la de Gemini conserva el de la v2.0 para no perderla."""
    return USUARIO_CLAVE if motor == "gemini" else f"motor:{motor}"


def variable_de_entorno(motor: str) -> str:
    return "GEMINI_API_KEY" if motor == "gemini" else f"MODPACKES_CLAVE_{motor.upper()}"


def leer_clave(motor: str = "gemini") -> str | None:
    """La variable de entorno (GEMINI_API_KEY, MODPACKES_CLAVE_<MOTOR>) tiene prioridad; si no, la guardada."""
    variable = variable_de_entorno(motor)
    if os.environ.get(variable):
        clave: str | None = os.environ[variable].strip()
    else:
        try:
            clave = keyring.get_password(SERVICIO, _usuario_de(motor))
        except KeyringError:
            return None
    registro.ocultar(clave)
    return clave


def guardar_clave(clave: str, motor: str = "gemini") -> None:
    registro.ocultar(clave)
    keyring.set_password(SERVICIO, _usuario_de(motor), clave.strip())


def olvidar_clave(motor: str = "gemini") -> None:
    with contextlib.suppress(KeyringError):
        keyring.delete_password(SERVICIO, _usuario_de(motor))


def leer_preferencias() -> dict[str, Any]:
    try:
        datos: Any = json.loads((carpeta_datos() / "preferencias.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cast(dict[str, Any], datos) if isinstance(datos, dict) else {}


def guardar_preferencias(datos: dict[str, Any]) -> None:
    ruta = carpeta_datos() / "preferencias.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos.pop("clave", None)  # por si acaso: la clave nunca va a un archivo
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def leer_glosario_usuario() -> dict[str, str]:
    try:
        datos: Any = json.loads(ruta_glosario_usuario().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {str(k): str(v) for k, v in cast(dict[str, Any], datos).items() if isinstance(v, str)}

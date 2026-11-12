"""Motor para cualquier servidor compatible con la API de OpenAI: OpenRouter, DeepSeek, LM Studio, Ollama…

Usa `POST {dirección}/chat/completions` con las mismas instrucciones que Gemini y pide la respuesta como JSON
con esquema (`response_format: json_schema`). Si el servidor no admite el esquema, pasa solo a JSON simple
(`json_object`): el validador de marcadores y de calidad revisa igual cada traducción.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from .base import Cancelado, ErrorFatal, Lote
from .carga import Enfriador
from .instrucciones import interpretar, sistema, usuario

_ESPERA_INICIAL, _ESPERA_MAXIMA = 2.0, 60.0


@dataclass(frozen=True, slots=True)
class Perfil:
    id: str
    nombre: str
    direccion: str
    necesita_clave: bool = True
    local: bool = False  #: corre en el PC: no cuesta nada y no hace falta clave
    modo_json: str = "esquema"  #: «esquema» (json_schema) u «objeto» (json_object)
    extra: Mapping[str, Any] = field(default_factory=dict[str, Any])  #: campos propios del proveedor


PERFILES: dict[str, Perfil] = {
    p.id: p
    for p in (
        # require_parameters: OpenRouter solo usa proveedores que respetan el esquema JSON
        Perfil(
            "openrouter", "OpenRouter", "https://openrouter.ai/api/v1", extra={"provider": {"require_parameters": True}}
        ),
        Perfil("deepseek", "DeepSeek", "https://api.deepseek.com", modo_json="objeto"),
        Perfil("lmstudio", "LM Studio (en tu PC)", "http://localhost:1234/v1", necesita_clave=False, local=True),
        Perfil("ollama", "Ollama (en tu PC)", "http://localhost:11434/v1", necesita_clave=False, local=True),
        Perfil("personalizado", "Otro compatible con OpenAI", "", necesita_clave=False),
    )
}


def _esquema(lote: Lote) -> dict[str, Any]:
    ids = [e.id for e in lote.entradas]
    return {
        "type": "object",
        "properties": {i: {"type": "string"} for i in ids},
        "required": ids,
        "additionalProperties": False,
    }


def _mensaje_de_error(respuesta: httpx.Response) -> str:
    try:
        datos: Any = respuesta.json()
    except ValueError:
        return respuesta.text[:300]
    error: Any = cast(dict[str, Any], datos).get("error") if isinstance(datos, dict) else None
    if isinstance(error, dict):
        return str(cast(dict[str, Any], error).get("message", ""))[:300]
    return str(cast(object, error or datos))[:300]


def _culpa_del_formato(mensaje: str) -> bool:
    """Si un 400 se debe a que el servidor o el modelo no admite la salida con esquema."""
    bajo = mensaje.lower()
    return any(p in bajo for p in ("response_format", "json_schema", "structured", "schema"))


class Compatible:
    def __init__(
        self,
        perfil: Perfil,
        modelo: str,
        clave: str | None = None,
        direccion: str | None = None,
        cliente: httpx.Client | None = None,
        esperar: Callable[[float], None] | None = None,
        reintentos: int = 6,
        temperatura: float = 0.2,
        enfriador: Enfriador | None = None,
    ) -> None:
        self.perfil = perfil
        self.modelo = modelo.strip()
        self.direccion = (direccion or perfil.direccion).strip().rstrip("/")
        if not self.direccion.startswith(("http://", "https://")):
            raise ErrorFatal("Falta la dirección del servidor (por ejemplo http://localhost:1234/v1).")
        if not self.modelo:
            raise ErrorFatal(f"Elige un modelo para {perfil.nombre}. «Probar conexión» muestra los disponibles.")
        cabeceras = {"Authorization": f"Bearer {clave.strip()}"} if clave and clave.strip() else {}
        self._cliente = cliente or httpx.Client(timeout=httpx.Timeout(240.0, connect=10.0), headers=cabeceras)
        if cliente is not None:
            self._cliente.headers.update(cabeceras)
        self._esperar = esperar
        self._reintentos = reintentos
        self._temperatura = temperatura
        self._modo_json = perfil.modo_json
        #: Pausas y vigilancia de la GPU para motores que corren en el PC (ver `carga.py`)
        self.enfriador = enfriador
        #: Si se activa, se deja de reintentar y se corta el trabajo.
        self.cancelar: threading.Event | None = None

    @property
    def nombre(self) -> str:
        return f"{self.perfil.id}:{self.modelo}"

    def _dormir(self, segundos: float) -> None:
        """Espera antes de reintentar; si el usuario cancela mientras tanto, despierta enseguida."""
        if self._esperar is not None:
            self._esperar(segundos)
        elif self.cancelar is not None:
            self.cancelar.wait(segundos)
        else:
            time.sleep(segundos)

    @property
    def es_local(self) -> bool:
        """Corre en este PC: un perfil local o cualquier servidor en localhost o 127.0.0.1."""
        return self.perfil.local or self.direccion.split("//", 1)[-1].startswith(("localhost", "127.0.0.1"))

    def _formato(self, lote: Lote) -> dict[str, Any]:
        if self._modo_json == "objeto":
            return {"type": "json_object"}
        esquema = {"name": "traducciones", "strict": True, "schema": _esquema(lote)}
        return {"type": "json_schema", "json_schema": esquema}

    def _cuerpo(self, lote: Lote) -> dict[str, Any]:
        return {
            **self.perfil.extra,
            "model": self.modelo,
            "temperature": self._temperatura,
            "messages": [{"role": "system", "content": sistema(lote)}, {"role": "user", "content": usuario(lote)}],
            "response_format": self._formato(lote),
        }

    def _fatal(self, respuesta: httpx.Response) -> str | None:
        """Mensaje para el usuario si reintentar no sirve; None si conviene reintentar."""
        codigo = respuesta.status_code
        if codigo in (401, 403):
            return f"{self.perfil.nombre} rechazó la clave ({codigo}): revísala con «Guardar clave…»."
        if codigo == 402:
            return f"{self.perfil.nombre} dice que no hay saldo o crédito en la cuenta (402)."
        if codigo == 404:
            return (
                f"{self.perfil.nombre} no encuentra el modelo «{self.modelo}» o la dirección {self.direccion} (404). "
                "«Probar conexión» muestra los modelos disponibles."
            )
        return None

    def _antes_del_pedido(self) -> None:
        if self.enfriador is not None:
            self.enfriador.cancelar = self.cancelar  # cancelar también corta la espera a que se enfríe la GPU
            self.enfriador.antes()
        if self.cancelar is not None and self.cancelar.is_set():
            raise Cancelado()

    def _despues_del_pedido(self, inicio: float) -> None:
        if self.enfriador is not None:
            self.enfriador.despues(time.monotonic() - inicio)

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        espera = _ESPERA_INICIAL
        for intento in range(self._reintentos):
            if self.cancelar is not None and self.cancelar.is_set():
                raise Cancelado()
            ultimo = intento == self._reintentos - 1
            self._antes_del_pedido()
            inicio = time.monotonic()
            try:
                respuesta = self._cliente.post(f"{self.direccion}/chat/completions", json=self._cuerpo(lote))
            except httpx.ConnectError as e:
                if self.perfil.local or ultimo:
                    raise ErrorFatal(
                        f"No pude conectar con {self.direccion}. ¿Está abierto {self.perfil.nombre} con el servidor "
                        "encendido?"
                    ) from e
            except httpx.HTTPError:
                if ultimo:
                    return {}
            else:
                if respuesta.is_success:
                    self._despues_del_pedido(inicio)
                    return self._leer(respuesta)
                fatal = self._fatal(respuesta)
                if fatal:
                    raise ErrorFatal(fatal)
                if respuesta.status_code in (400, 422):
                    if self._modo_json == "esquema" and _culpa_del_formato(_mensaje_de_error(respuesta)):
                        self._modo_json = "objeto"  # el servidor no admite json_schema: JSON simple
                        continue
                    return {}  # pedido rechazado (p. ej. demasiado grande): el lote se reintenta más chico
                if ultimo:
                    if respuesta.status_code == 429:
                        raise ErrorFatal(
                            f"{self.perfil.nombre} sigue limitando las peticiones (429). Espera un rato o baja las "
                            "peticiones a la vez; lo ya traducido no se pierde."
                        )
                    return {}
                espera = max(espera, self._retry_after(respuesta))
            self._dormir(min(espera, _ESPERA_MAXIMA))
            espera = min(espera * 2, _ESPERA_MAXIMA)
        return {}

    @staticmethod
    def _retry_after(respuesta: httpx.Response) -> float:
        try:
            return float(respuesta.headers.get("retry-after", "0"))
        except ValueError:
            return 0.0

    @staticmethod
    def _leer(respuesta: httpx.Response) -> dict[str, str]:
        try:
            datos: Any = respuesta.json()
            contenido: Any = datos["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return {}
        return interpretar(contenido if isinstance(contenido, str) else None)

    def listar_modelos(self) -> list[str]:
        try:
            respuesta = self._cliente.get(f"{self.direccion}/models")
        except httpx.HTTPError as e:
            raise ErrorFatal(f"No pude conectar con {self.direccion}: {e}") from e
        if not respuesta.is_success:
            raise ErrorFatal(
                self._fatal(respuesta)
                or f"No pude listar los modelos ({respuesta.status_code}): {_mensaje_de_error(respuesta)}"
            )
        try:
            datos: Any = respuesta.json()
        except ValueError as e:
            raise ErrorFatal("El servidor respondió algo que no es la lista de modelos.") from e
        lista: Any = cast(dict[str, Any], datos).get("data", []) if isinstance(datos, dict) else []
        if not isinstance(lista, list):
            return []
        return sorted(
            str(cast(dict[str, Any], m)["id"]) for m in cast(list[Any], lista) if isinstance(m, dict) and "id" in m
        )

    def cerrar(self) -> None:
        self._cliente.close()

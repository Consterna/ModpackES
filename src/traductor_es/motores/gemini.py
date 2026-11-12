"""Motor de traducción con la API de Gemini (SDK oficial google-genai).

- Respuesta con esquema JSON exacto: el modelo debe devolver una clave por cada texto recibido.
- Razonamiento («thinking») al mínimo que admite el modelo: para traducir no hace falta y se paga.
- Reintentos con espera ante cuota (429) y fallos del servidor; errores claros para la clave o el modelo.
- Modo por lotes (Batch API): la mitad de precio, a cambio de esperar a que Google lo procese.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, cast

import httpx
from google import genai
from google.genai import errors, types

from .base import Cancelado, ErrorFatal, Lote
from .instrucciones import interpretar, sistema, usuario

MODELO_POR_DEFECTO = "gemini-3.8-flash"
#: Precios de pago en US$ por millón de tokens (entrada, salida), según la página de precios de Google
#: en noviembre de 2026. Solo sirven para estimar: Google puede cambiarlos.
PRECIOS: dict[str, tuple[float, float]] = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}
#: Nivel de razonamiento más bajo que acepta cada familia (3.8 Flash no admite «minimal»).
_RAZONAMIENTO_MINIMO = {"gemini-3.8-flash": "LOW"}
_ESPERA_INICIAL, _ESPERA_MAXIMA, _SONDEO_LOTES = 4.0, 90.0, 30.0
_MAXIMO_POR_TRABAJO = 15 * 1024 * 1024  #: margen bajo el límite de 20 MB de la Batch API


def _esquema(lote: Lote) -> dict[str, Any]:
    ids = [e.id for e in lote.entradas]
    return {
        "type": "OBJECT",
        "properties": {i: {"type": "STRING"} for i in ids},
        "required": ids,
        "property_ordering": ids,
    }


def explicar(error: errors.APIError) -> str | None:
    """Mensaje para el usuario si el error no se arregla reintentando; None si vale la pena reintentar."""
    codigo = error.code or 0
    mensaje = f"{error.message or ''} {error.status or ''}"
    if "API_KEY_INVALID" in mensaje or "API key not valid" in mensaje or codigo in (401, 403):
        return "La clave de Gemini no es válida o no tiene permiso. Revísala en aistudio.google.com/apikey."
    if codigo == 404:
        return "Ese modelo no existe para tu clave. Usa «Probar clave» para ver los disponibles."
    if codigo == 429 and ("limit: 0" in mensaje or "per day" in mensaje.lower() or "PerDay" in mensaje):
        return "Se agotó la cuota diaria de Gemini. Vuelve a intentarlo más tarde: lo ya traducido no se pierde."
    return None


class Gemini:
    def __init__(
        self,
        clave: str,
        modelo: str = MODELO_POR_DEFECTO,
        cliente: Any = None,
        esperar: Callable[[float], None] | None = None,
        reintentos: int = 7,
        temperatura: float = 0.2,
    ) -> None:
        self.modelo = modelo.strip()
        self._cliente: Any = cliente or genai.Client(
            api_key=clave.strip(), http_options=types.HttpOptions(timeout=240_000)
        )
        self._esperar = esperar
        self._reintentos = reintentos
        self._temperatura = temperatura
        self._con_razonamiento = True
        #: Para el modo por lotes: se llama con el estado del trabajo mientras se espera.
        self.al_esperar: Callable[[str], None] = lambda _estado: None
        #: Si se activa mientras se espera un trabajo por lotes, se cancela en Google y se deja de esperar.
        self.cancelar: threading.Event | None = None

    @property
    def nombre(self) -> str:
        return f"gemini:{self.modelo}"

    def _cancelado(self) -> bool:
        return self.cancelar is not None and self.cancelar.is_set()

    def _dormir(self, segundos: float) -> None:
        """Espera antes de reintentar; si el usuario cancela mientras tanto, despierta enseguida."""
        if self._esperar is not None:
            self._esperar(segundos)
        elif self.cancelar is not None:
            self.cancelar.wait(segundos)
        else:
            time.sleep(segundos)

    def listar_modelos(self) -> list[str]:
        try:
            modelos = list(self._cliente.models.list())
        except errors.APIError as e:
            raise ErrorFatal(explicar(e) or f"No pude listar los modelos: {e.message}") from e
        nombres: list[str] = []
        for m in modelos:
            acciones = cast(list[str], getattr(m, "supported_actions", None) or [])
            nombre = str(getattr(m, "name", "")).removeprefix("models/")
            if "generateContent" in acciones and nombre.startswith("gemini"):
                nombres.append(nombre)
        return sorted(nombres)

    def _config(self, lote: Lote) -> types.GenerateContentConfig:
        razonamiento = None
        if self._con_razonamiento:
            nivel = _RAZONAMIENTO_MINIMO.get(self.modelo, "MINIMAL")
            razonamiento = types.ThinkingConfig(thinking_level=types.ThinkingLevel(nivel))
        return types.GenerateContentConfig(
            system_instruction=sistema(lote),
            temperature=self._temperatura,
            response_mime_type="application/json",
            response_schema=_esquema(lote),
            thinking_config=razonamiento,
        )

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        espera = _ESPERA_INICIAL
        for intento in range(self._reintentos):
            if self._cancelado():  # sin esto, cancelar esperaría a que se agoten los reintentos (minutos)
                raise Cancelado()
            try:
                respuesta = self._cliente.models.generate_content(
                    model=self.modelo, contents=usuario(lote), config=self._config(lote)
                )
                return interpretar(getattr(respuesta, "text", None))
            except errors.APIError as e:
                fatal = explicar(e)
                if fatal:
                    raise ErrorFatal(fatal) from e
                if (e.code or 0) == 400 and self._con_razonamiento and "think" in (e.message or "").lower():
                    self._con_razonamiento = False  # el modelo no acepta ese nivel: se pide sin configurarlo
                    continue
                if (e.code or 0) == 400:
                    return {}  # petición rechazada (p. ej. demasiado grande): el lote se reintenta más chico
                if intento == self._reintentos - 1:
                    if (e.code or 0) == 429:
                        raise ErrorFatal(
                            "Gemini sigue limitando las peticiones (429). Espera un rato o baja las peticiones a la "
                            "vez; lo ya traducido no se pierde."
                        ) from e
                    return {}
            except (OSError, TimeoutError, ValueError, httpx.HTTPError):  # cortes de red: se reintenta
                if intento == self._reintentos - 1:
                    return {}
            self._dormir(espera)
            espera = min(espera * 2, _ESPERA_MAXIMA)
        return {}

    # ------------------------------------------------------------------ Batch API
    def traducir_varios(self, lotes: Sequence[Lote]) -> list[dict[str, str]]:
        """Manda todos los lotes en un solo trabajo de la Batch API y espera el resultado (mitad de precio)."""
        if not lotes:
            return []
        # Google acepta hasta 20 MB por trabajo: si hay más, se mandan varios trabajos seguidos
        grupos: list[list[Lote]] = [[]]
        tamano = 0
        for lote in lotes:
            peso = len(usuario(lote).encode("utf-8")) + len(sistema(lote).encode("utf-8")) + 2000
            if grupos[-1] and tamano + peso > _MAXIMO_POR_TRABAJO:
                grupos.append([])
                tamano = 0
            grupos[-1].append(lote)
            tamano += peso
        return [salida for grupo in grupos for salida in self._un_trabajo(grupo)]

    def _un_trabajo(self, lotes: Sequence[Lote]) -> list[dict[str, str]]:
        pedidos = [{"contents": usuario(lote), "config": self._config(lote)} for lote in lotes]
        try:
            trabajo = self._cliente.batches.create(model=self.modelo, src=pedidos, config={"display_name": "modpackes"})
            terminados = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
            while (estado := str(getattr(trabajo.state, "name", trabajo.state))) not in terminados:
                if self._cancelado():
                    with contextlib.suppress(errors.APIError):
                        self._cliente.batches.cancel(name=trabajo.name)  # que Google no lo siga procesando
                    raise Cancelado()
                self.al_esperar(estado)
                self._dormir(_SONDEO_LOTES)
                if self._cancelado():
                    continue  # se cancela el trabajo arriba, sin volver a consultar
                trabajo = self._cliente.batches.get(name=trabajo.name)
        except errors.APIError as e:
            raise ErrorFatal(explicar(e) or f"La Batch API de Gemini falló: {e.message}") from e
        if estado != "JOB_STATE_SUCCEEDED":
            raise ErrorFatal(f"El trabajo por lotes terminó como {estado}. Vuelve a intentarlo o usa el modo normal.")
        respuestas = list(getattr(trabajo.dest, "inlined_responses", None) or [])
        salida: list[dict[str, str]] = []
        for i in range(len(lotes)):
            r = respuestas[i] if i < len(respuestas) else None
            texto = getattr(getattr(r, "response", None), "text", None) if r is not None else None
            salida.append(interpretar(texto))
        return salida

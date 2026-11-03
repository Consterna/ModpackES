"""El motor Gemini con un cliente falso que imita al SDK (sin red ni clave)."""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors, types

from traductor_es.motores.base import Entrada, ErrorFatal, Lote
from traductor_es.motores.gemini import Gemini, _esquema, _sistema, _usuario  # pyright: ignore[reportPrivateUsage]


def lote(*textos: str, ambito: str = "mision", glosario: dict[str, str] | None = None) -> Lote:
    return Lote(tuple(Entrada(str(i), t, "pista") for i, t in enumerate(textos)), ambito, "español", glosario or {})


def error(codigo: int, mensaje: str, estado: str = "") -> errors.APIError:
    return errors.APIError(codigo, {"error": {"code": codigo, "message": mensaje, "status": estado}})


@dataclass
class Modelos:
    respuestas: list[Any]
    llamadas: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])

    def generate_content(self, model: str, contents: str, config: types.GenerateContentConfig) -> Any:
        self.llamadas.append({"model": model, "contents": contents, "config": config})
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(text=r)

    def list(self) -> list[Any]:
        return [
            SimpleNamespace(name="models/gemini-3.8-flash", supported_actions=["generateContent", "countTokens"]),
            SimpleNamespace(name="models/text-embedding-004", supported_actions=["embedContent"]),
            SimpleNamespace(name="models/gemini-3.5-flash-lite", supported_actions=["generateContent"]),
        ]


def motor(*respuestas: Any) -> tuple[Gemini, Modelos, list[float]]:
    esperas: list[float] = []
    modelos = Modelos(list(respuestas))
    g = Gemini("clave", cliente=SimpleNamespace(models=modelos), esperar=esperas.append)
    return g, modelos, esperas


def test_traduce_con_esquema_y_razonamiento_minimo() -> None:
    g, modelos, _ = motor(json.dumps({"0": "Hola", "1": "Adiós"}))
    assert g.traducir_lote(lote("Hello", "Bye", glosario={"Oak": "Roble"})) == {"0": "Hola", "1": "Adiós"}
    config = modelos.llamadas[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema["required"] == ["0", "1"]
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW  # 3.8 Flash no admite «minimal»
    enviado = json.loads(modelos.llamadas[0]["contents"])
    assert enviado == {"glosario": {"Oak": "Roble"}, "textos": {"0": {"texto": "Hello", "contexto": "pista"},
                                                                "1": {"texto": "Bye", "contexto": "pista"}}}  # fmt: skip
    assert g.nombre == "gemini:gemini-3.8-flash"


def test_prompt_por_ambito_y_dialecto() -> None:
    assert "tutea" in _sistema(lote("x", ambito="mision")) and "⟦0⟧" in _sistema(lote("x"))
    assert "breves" in _sistema(lote("x", ambito="ui"))
    assert _esquema(lote("a", "b"))["properties"] == {"0": {"type": "STRING"}, "1": {"type": "STRING"}}
    assert "glosario" not in json.loads(_usuario(lote("a")))


def test_errores_fatales() -> None:
    for e, palabra in [
        (error(400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT"), "clave"),
        (error(403, "Permission denied"), "clave"),
        (error(404, "models/x is not found"), "modelo"),
        (error(429, "Quota exceeded for metric ... limit: 0", "RESOURCE_EXHAUSTED"), "cuota"),
    ]:
        g, _, _ = motor(e)
        with pytest.raises(ErrorFatal, match=palabra):
            g.traducir_lote(lote("Hello"))


def test_reintenta_429_temporal_y_5xx() -> None:
    g, modelos, esperas = motor(error(429, "Too many requests"), error(503, "Unavailable"), '{"0": "Hola"}')
    assert g.traducir_lote(lote("Hello")) == {"0": "Hola"}
    assert len(modelos.llamadas) == 3 and esperas == [4.0, 8.0]


def test_429_persistente_termina_en_error_claro() -> None:
    g, _, _ = motor(*[error(429, "Too many requests")] * 7)
    with pytest.raises(ErrorFatal, match="429"):
        g.traducir_lote(lote("Hello"))


def test_si_no_acepta_el_razonamiento_lo_quita() -> None:
    g, modelos, _ = motor(error(400, "thinking_level is not supported for this model"), '{"0": "Hola"}')
    assert g.traducir_lote(lote("Hello")) == {"0": "Hola"}
    assert modelos.llamadas[1]["config"].thinking_config is None


def test_respuestas_raras_no_rompen() -> None:
    for r in [None, "no es json", "[1, 2]", '```json\n{"0": "Hola", "1": 5}\n```']:
        g, _, _ = motor(r)
        salida = g.traducir_lote(lote("Hello", "x"))
        assert salida in ({}, {"0": "Hola"})
    g, _, _ = motor(error(400, "Request payload size exceeds the limit"))
    assert g.traducir_lote(lote("Hello")) == {}  # el traductor lo reintenta en lotes más chicos


def test_listar_modelos() -> None:
    g, _, _ = motor()
    assert g.listar_modelos() == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]


@dataclass
class Lotes:
    estados: list[str]
    respuestas: list[Any]
    creados: list[Any] = field(default_factory=list[Any])

    def create(self, model: str, src: list[Any], config: dict[str, Any]) -> Any:
        self.creados.append(src)
        return self.get("trabajo")

    def get(self, name: str) -> Any:
        estado = self.estados.pop(0)
        dest = SimpleNamespace(
            inlined_responses=[SimpleNamespace(response=SimpleNamespace(text=t)) for t in self.respuestas]
        )
        return SimpleNamespace(name=name, state=SimpleNamespace(name=estado), dest=dest)


def test_batch_api() -> None:
    lotes = Lotes(["JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_SUCCEEDED"], ['{"0": "Uno"}', '{"0": "Dos"}'])
    esperas: list[float] = []
    g = Gemini("clave", cliente=SimpleNamespace(batches=lotes, models=None), esperar=esperas.append)
    vistos: list[str] = []
    g.al_esperar = vistos.append
    assert g.traducir_varios([lote("One"), lote("Two")]) == [{"0": "Uno"}, {"0": "Dos"}]
    assert vistos == ["JOB_STATE_PENDING", "JOB_STATE_RUNNING"] and esperas == [30.0, 30.0]
    assert len(lotes.creados[0]) == 2 and lotes.creados[0][0]["config"].response_mime_type == "application/json"
    fallido = Lotes(["JOB_STATE_FAILED"], [])
    g = Gemini("clave", cliente=SimpleNamespace(batches=fallido, models=None), esperar=esperas.append)
    with pytest.raises(ErrorFatal, match="FAILED"):
        g.traducir_varios([lote("One")])


def test_corte_de_red_se_reintenta() -> None:
    import httpx

    g, modelos, esperas = motor(httpx.ConnectError("sin conexión"), '{"0": "Hola"}')
    assert g.traducir_lote(lote("Hello")) == {"0": "Hola"}
    assert len(modelos.llamadas) == 2 and esperas == [4.0]


def test_batch_reparte_en_varios_trabajos(monkeypatch: pytest.MonkeyPatch) -> None:
    import traductor_es.motores.gemini as gem

    monkeypatch.setattr(gem, "_MAXIMO_POR_TRABAJO", 5000)  # cada lote pesa unos 3 KB: uno por trabajo
    lotes = Lotes(["JOB_STATE_SUCCEEDED"] * 3, ['{"0": "X"}'])
    g = Gemini("clave", cliente=SimpleNamespace(batches=lotes, models=None), esperar=lambda _s: None)
    assert g.traducir_varios([lote("One"), lote("Two"), lote("Three")]) == [{"0": "X"}] * 3
    assert [len(c) for c in lotes.creados] == [1, 1, 1]


def test_cancelar_durante_la_espera_del_lote() -> None:
    import threading

    from traductor_es.motores.base import Cancelado

    class Cancelables(Lotes):
        def __init__(self) -> None:
            super().__init__(["JOB_STATE_PENDING"] * 5, [])
            self.cancelados: list[str] = []

        def cancel(self, name: str) -> None:
            self.cancelados.append(name)

    lotes = Cancelables()
    evento = threading.Event()
    g = Gemini("clave", cliente=SimpleNamespace(batches=lotes, models=None), esperar=lambda _s: evento.set())
    g.cancelar = evento
    with pytest.raises(Cancelado):
        g.traducir_varios([lote("One")])
    assert lotes.cancelados == ["trabajo"]

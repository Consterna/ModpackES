"""Máquinas de estado (Hypothesis): secuencias al azar de operaciones contra un modelo simple de lo que debe pasar.

- Copias de seguridad: traducir, actualizar el modpack, borrar, restaurar, reabrir, dañar el registro y podar.
  Nunca se pierde el inglés, y «restaurar» devuelve justo lo que había antes de la última traducción, salvo lo que
  cambió después: eso no se toca.
- Memoria de traducciones: guardar, corregir, quitar la corrección y olvidar, en dos packs.
- `options.txt`: activar el pack muchas veces entre ediciones del jugador. El pack queda una sola vez y arriba; las
  demás líneas no cambian; activar dos veces seguidas no cambia nada.

Para una corrida larga: `MODPACKES_ESTADOS=2000 uv run pytest tests/test_auditoria_estados.py`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from traductor_es.nucleo.memoria import Memoria
from traductor_es.salida import opciones
from traductor_es.salida.copias import Respaldo

_AJUSTES = settings(
    max_examples=int(os.environ.get("MODPACKES_ESTADOS", "40")),
    stateful_step_count=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

ARCHIVOS = ("a.snbt", "sub/b.json", "sub/c/d.lang")
_TEXTO = st.binary(min_size=0, max_size=24)


# --- copias de seguridad -----------------------------------------------------------------------------------------------


class MaquinaRespaldo(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self._tmp = Path(tempfile.mkdtemp(prefix="estados_"))
        self.juego = self._tmp / "juego"
        self.juego.mkdir()
        self.r = Respaldo(self.juego)
        #: lo que escribió la app y sigue en el disco: (lo escrito, el inglés que había antes o None si no existía)
        self.escrito: dict[str, tuple[bytes, bytes | None] | None] = dict.fromkeys(ARCHIVOS)
        #: archivos que creó la app y que quedaron vacíos («neutros») al restaurar: no son un original del modpack
        self.neutro: set[str] = set()

    def teardown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _ruta(self, f: str) -> Path:
        return self.juego / f

    def _disco(self, f: str) -> bytes | None:
        ruta = self._ruta(f)
        return ruta.read_bytes() if ruta.is_file() else None

    def _original_esperado(self, f: str) -> bytes | None:
        disco = self._disco(f)
        vivo = self.escrito[f]
        if vivo is not None and disco == vivo[0]:
            return vivo[1]
        if f in self.neutro and disco == b"":
            return None
        return disco

    @rule(f=st.sampled_from(ARCHIVOS), datos=_TEXTO)
    def traducir(self, f: str, datos: bytes) -> None:
        datos = b"ES:" + datos  # una traducción nunca es igual a un inglés del modelo
        ingles = self._original_esperado(f)
        self.r.escribir(self._ruta(f), datos)
        self.escrito[f] = (datos, ingles)
        self.neutro.discard(f)

    @rule(f=st.sampled_from(ARCHIVOS), datos=_TEXTO)
    def actualizar_el_modpack(self, f: str, datos: bytes) -> None:
        ruta = self._ruta(f)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"EN:" + datos)
        # La app lo nota al restaurar (no lo pisa). Si después el jugador lo borra, ya no lo puede notar: lo trata
        # como un archivo traducido que se borró y lo recrea con su copia en inglés.
        self.neutro.discard(f)

    @rule(f=st.sampled_from(ARCHIVOS))
    def borrar(self, f: str) -> None:
        self._ruta(f).unlink(missing_ok=True)
        self.neutro.discard(f)

    @rule()
    def restaurar(self) -> None:
        esperado: dict[str, bytes | None] = {}
        for f in ARCHIVOS:
            disco = self._disco(f)
            vivo = self.escrito[f]
            if vivo is None:
                esperado[f] = disco
            elif disco == vivo[0]:
                esperado[f] = vivo[1] if vivo[1] is not None else b""  # lo que creó la app queda vacío
                if vivo[1] is None:
                    self.neutro.add(f)
            elif disco is None:
                esperado[f] = vivo[1]  # lo borró el jugador: se recrea si había un original
            else:
                esperado[f] = disco
        self.r.restaurar("")
        for f in ARCHIVOS:
            assert self._disco(f) == esperado[f], f
            self.escrito[f] = None

    @rule()
    def reabrir(self) -> None:
        self.r = Respaldo(self.juego)

    @rule()
    def danar_el_registro(self) -> None:
        if self.r.registro.is_file():
            self.r.registro.write_bytes(b"{ roto")
        self.r = Respaldo(self.juego)

    @rule()
    def podar_anteriores(self) -> None:
        self.r.podar_anteriores(conservar=1, dias=0)

    @invariant()
    def el_original_es_el_ingles(self) -> None:
        for f in ARCHIVOS:
            assert self.r.original(self._ruta(f)) == self._original_esperado(f), f


TestRespaldo = MaquinaRespaldo.TestCase
TestRespaldo.settings = _AJUSTES


# --- memoria de traducciones --------------------------------------------------------------------------------------------

TEXTOS = ("Iron Plate", "Copper Wire", "Gear")
PACKS = ("pack-a", "pack-b")


class MaquinaMemoria(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.m = Memoria(":memory:")
        #: (texto, pack) → (traducción, ok); el orden de guardado decide «la más reciente»
        self.guardadas: dict[tuple[str, str], tuple[str, bool]] = {}
        self.orden: list[tuple[str, str]] = []
        self.correcciones: dict[str, str] = {}

    def teardown(self) -> None:
        self.m.cerrar()

    @rule(texto=st.sampled_from(TEXTOS), pack=st.sampled_from(PACKS), n=st.integers(0, 9), dudosa=st.booleans())
    def guardar(self, texto: str, pack: str, n: int, dudosa: bool) -> None:
        traduccion = f"{texto} es {n}"
        self.m.guardar({texto: traduccion}, "es_mx", "ui", "simulador", pack, {texto: "duda"} if dudosa else None)
        self.guardadas[(texto, pack)] = (traduccion, not dudosa)
        if (texto, pack) in self.orden:
            self.orden.remove((texto, pack))
        self.orden.append((texto, pack))

    @rule(texto=st.sampled_from(TEXTOS), n=st.integers(0, 9))
    def corregir(self, texto: str, n: int) -> None:
        self.m.corregir(texto, "es_mx", f"{texto} corregido {n}")
        self.correcciones[texto] = f"{texto} corregido {n}"

    @rule(texto=st.sampled_from(TEXTOS))
    def quitar_correccion(self, texto: str) -> None:
        self.m.quitar_correccion(texto, "es_mx")
        self.correcciones.pop(texto, None)

    @rule(texto=st.sampled_from(TEXTOS))
    def olvidar(self, texto: str) -> None:
        self.m.olvidar(texto, "es_mx", "ui")
        for pack in PACKS:
            self.guardadas.pop((texto, pack), None)
            if (texto, pack) in self.orden:
                self.orden.remove((texto, pack))

    @invariant()
    def lo_que_se_lee_coincide_con_el_modelo(self) -> None:
        for texto in TEXTOS:
            assert self.m.correccion(texto, "es_mx") == self.correcciones.get(texto)
            for pack in PACKS:
                propia = self.guardadas.get((texto, pack))
                if propia is not None:
                    esperada: str | None = propia[0]
                else:  # de otro pack, solo si quedó «ok»
                    otras = [self.guardadas[k][0] for k in self.orden if k[0] == texto and self.guardadas[k][1]]
                    esperada = otras[-1] if otras else None
                obtenida = self.m.obtener(texto, "es_mx", "ui", pack)
                # «la más reciente» se decide por fecha con segundos: dos guardados en el mismo segundo empatan
                validas = {esperada} if propia is not None or esperada is None else {
                    self.guardadas[k][0] for k in self.orden if k[0] == texto and self.guardadas[k][1]
                }  # fmt: skip
                assert obtenida in validas, (texto, pack, obtenida, validas)
        assert self.m.correcciones("es_mx") == self.correcciones


TestMemoria = MaquinaMemoria.TestCase
TestMemoria.settings = _AJUSTES


# --- options.txt ------------------------------------------------------------------------------------------------------

_CLAVE = st.sampled_from(["fov", "gamma", "lang", "resourcePacks", "incompatibleResourcePacks", "key_key.jump", "x"])
_VALOR = st.text(st.characters(codec="utf-8", exclude_characters="\r\n"), max_size=12)
_LISTA = st.lists(
    st.sampled_from(["vanilla", "file/Otro.zip", "file/Traduccion_ES", "fabric", "Traduccion_ES"]), max_size=4
)


class MaquinaOpciones(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self._tmp = Path(tempfile.mkdtemp(prefix="opciones_"))
        self.ruta = self._tmp / "options.txt"
        self.ruta.write_bytes(b'version:3465\nfov:0.0\nresourcePacks:["vanilla"]\nlang:en_us\n')

    def teardown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    @rule(clave=_CLAVE, valor=_VALOR, crlf=st.booleans())
    def el_jugador_agrega_una_linea(self, clave: str, valor: str, crlf: bool) -> None:
        if clave in ("resourcePacks", "incompatibleResourcePacks"):
            return  # las listas se cambian con su propia regla, siempre bien formadas
        with self.ruta.open("ab") as f:
            f.write(f"{clave}:{valor}{'\r\n' if crlf else '\n'}".encode("utf-8", errors="surrogateescape"))

    @rule(packs=_LISTA)
    def el_jugador_cambia_los_packs(self, packs: list[str]) -> None:
        import json

        lineas = self.ruta.read_bytes().decode("utf-8", errors="surrogateescape").splitlines(keepends=True)
        nueva = f"resourcePacks:{json.dumps(packs)}\n"
        lineas = [nueva if linea.startswith("resourcePacks:") else linea for linea in lineas]
        self.ruta.write_bytes("".join(lineas).encode("utf-8", errors="surrogateescape"))

    @rule(idioma=st.sampled_from(["es_mx", "es_es", None]))
    def activar(self, idioma: str | None) -> None:
        import json

        antes = self.ruta.read_bytes().decode("utf-8", errors="surrogateescape").splitlines()
        opciones.activar(self._tmp, "Traduccion_ES", idioma, con_prefijo=True)
        despues_bytes = self.ruta.read_bytes()
        despues = despues_bytes.decode("utf-8", errors="surrogateescape").splitlines()
        tocadas = ("resourcePacks:", "incompatibleResourcePacks:") + (("lang:",) if idioma else ())
        assert [x for x in antes if not x.startswith(tocadas)] == [x for x in despues if not x.startswith(tocadas)]
        for linea in despues:
            if linea.startswith("resourcePacks:"):
                packs = json.loads(linea.split(":", 1)[1])
                assert packs.count("file/Traduccion_ES") == 1 and packs[-1] == "file/Traduccion_ES"
            if idioma and linea.startswith("lang:"):
                assert linea == f"lang:{idioma}"
        opciones.activar(self._tmp, "Traduccion_ES", idioma, con_prefijo=True)
        assert self.ruta.read_bytes() == despues_bytes  # dos veces seguidas: no cambia nada


TestOpciones = MaquinaOpciones.TestCase
TestOpciones.settings = _AJUSTES

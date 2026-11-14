"""Orquestador: une la instancia, el glosario, la memoria, el motor y los módulos de contenido."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self, cast

from . import configuracion
from .fuentes.instancia import Instancia
from .modulos import datos, libros, misiones, mods, runtime, scripts
from .modulos.base import Contexto, Modulo, Pieza, Resumen, reunir_pistas
from .modulos.cambios import Cambios, Lugar, comparar, indice_de, leer_indice, mezclar, para_la_marca, sin_indice
from .modulos.cobertura import Hallazgo, hallazgos_de_comandos, hallazgos_de_scripts, revisar_cobertura
from .modulos.mods import es_nombre
from .motores import fabrica
from .motores.base import ErrorFatal, Motor
from .motores.compatible import Compatible
from .motores.gemini import PRECIOS, Gemini
from .nucleo.dialectos import DIALECTO_POR_DEFECTO, VARIANTES, nombre_archivo_lang
from .nucleo.ejemplos import CANTIDAD_EN_LA_APP, Ejemplos
from .nucleo.glosario import Glosario
from .nucleo.mascara import separar_bordes
from .nucleo.memoria import Memoria
from .nucleo.traductor import Resultado, Traductor
from .salida import opciones as opciones_salida
from .salida.copias import Respaldo
from .salida.resource_pack import NOMBRE, PackSalida
from .validacion import revision
from .validacion.calidad import Revision, revisar_glosario, validar

GRUPOS = ("mods", "libros", "misiones", "scripts")
#: Grupos que pasan por la revisión automática: textos largos donde un error se nota y cambia el sentido.
GRUPOS_REVISADOS = ("misiones", "libros")
_ESTADOS = {"JOB_STATE_PENDING": "en cola", "JOB_STATE_RUNNING": "procesando"}
#: Tokens por carácter y sobrecarga por lote, medidos a ojo con textos de mods: solo para estimar.
_CARACTERES_POR_TOKEN, _TOKENS_POR_LOTE = 3.5, 450
#: Motores que no se anotan en los créditos del pack: no traducen de verdad.
_SIN_CREDITO = frozenset({"simulador"})


@dataclass(slots=True)
class InformeModulo:
    grupo: str
    nombre: str
    descripcion: str
    textos: int  #: textos distintos encontrados
    a_traducir: int  #: los que irían al motor (lo demás sale de memoria, glosario o de otra variante)
    caracteres: int
    resumen: Resumen | None = None


@dataclass(slots=True)
class Informe:
    modulos: list[InformeModulo] = field(default_factory=list[InformeModulo])
    avisos: list[str] = field(default_factory=list[str])
    revision: Revision | None = None
    revision_automatica: revision.ResumenRevision | None = None
    pack_activado: list[str] = field(default_factory=list[str])
    fallidos: list[str] = field(default_factory=list[str])  #: grupos que el análisis no pudo leer
    #: Lo que queda en inglés aunque se traduzca todo, y por qué (ver `modulos/cobertura.py`)
    cobertura: list[Hallazgo] = field(default_factory=list[Hallazgo])
    #: Qué cambió en el inglés desde la última traducción (ver `modulos/cambios.py`); solo al analizar
    cambios: Cambios | None = None
    #: Por módulo, lo que costaría traducir solo lo nuevo y lo cambiado
    modulos_cambios: list[InformeModulo] = field(default_factory=list[InformeModulo])

    @property
    def diferencia(self) -> Informe:
        """Un informe con solo lo nuevo y lo cambiado, para estimar su costo con `costo`."""
        return Informe(modulos=list(self.modulos_cambios))

    @property
    def a_traducir(self) -> int:
        return sum(m.a_traducir for m in self.modulos)

    @property
    def caracteres(self) -> int:
        return sum(m.caracteres for m in self.modulos)

    def costo(self, modelo: str, por_lotes: bool, motor: str = fabrica.GEMINI, revisar: bool = False) -> float | None:
        """Costo estimado en US$: 0 con un motor en el PC; None si no se conoce el precio del modelo."""
        if fabrica.es_local(motor):
            return 0.0
        precio = PRECIOS.get(modelo) if motor == fabrica.GEMINI else None
        if precio is None:
            return None
        total = _costo_traduccion(self.caracteres, self.a_traducir, precio)
        total = total / 2 if por_lotes else total
        if revisar:  # la revisión va en modo normal aunque la traducción vaya por lotes
            revisados = [m for m in self.modulos if m.grupo in GRUPOS_REVISADOS]
            caracteres = sum(m.caracteres for m in revisados)
            textos = sum(m.a_traducir for m in revisados)
            tokens = caracteres / _CARACTERES_POR_TOKEN
            # leer original y traducción, contestar unas palabras por texto y rehacer más o menos 1 de cada 7
            total += (tokens * 2.4 * precio[0] + textos * 12 * precio[1]) / 1e6
            total += 0.15 * _costo_traduccion(caracteres, textos, precio)
        return total


def _grupo_del_indice(grupo: str, modulo: Modulo) -> str:
    """El grupo con que el módulo va al índice. El texto del código de los mods es opcional (`--java`): va aparte,
    para que una ejecución sin `--java` no lo borre del índice ni lo cuente como borrado."""
    return "java" if isinstance(modulo, runtime.TextoDeJava) else grupo


def _textos(lugar: Lugar) -> list[str]:
    return list(lugar.textos.values()) if isinstance(lugar.textos, Mapping) else list(lugar.textos)


def _costo_traduccion(caracteres: int, textos: int, precio: tuple[float, float]) -> float:
    if not caracteres:
        return 0.0
    tokens = caracteres / _CARACTERES_POR_TOKEN
    lotes = max(1, textos // 50)
    entrada = tokens * 1.6 + lotes * _TOKENS_POR_LOTE
    salida = tokens * 1.4  # traducción (el español es algo más largo) más algo de razonamiento
    return (entrada * precio[0] + salida * precio[1]) / 1e6


def lugares_de(modulo: Modulo, piezas: list[Pieza]) -> list[Lugar]:
    """Los lugares del módulo (tras `recolectar`). Un módulo sin `lugares` cuenta como un solo lugar en orden."""
    propios = getattr(modulo, "lugares", None)
    if callable(propios):
        return cast(list[Lugar], propios())
    return [Lugar(modulo.nombre, [p.texto for p in piezas])]


class Proceso:
    def __init__(
        self,
        carpeta: Path | str,
        motor: Motor,
        dialecto: str = DIALECTO_POR_DEFECTO,
        grupos: Sequence[str] = GRUPOS,
        memoria: Memoria | None = None,
        registro: Callable[[str], None] = lambda _m: None,
        progreso: Callable[[int, int], None] = lambda _h, _t: None,
        cancelar: threading.Event | None = None,
        hilos: int = 4,
        usar_lotes: bool = False,
        contexto: str = "",
        revisar: bool = False,
        texto_java: bool = False,
        scripts_exhaustivo: bool = False,
    ) -> None:
        self.instancia = Instancia(carpeta)
        self.revisar = revisar
        self.texto_java = texto_java
        self.scripts_exhaustivo = scripts_exhaustivo
        self.registro = registro
        self.grupos = [g for g in GRUPOS if g in grupos]
        self._memoria_propia = memoria is None
        self.memoria = memoria or self._abrir_memoria()
        self.glosario = Glosario()
        self.ejemplos = Ejemplos(cantidad=CANTIDAD_EN_LA_APP)
        self.ctx = Contexto(
            self.instancia, Respaldo(self.instancia.juego), dialecto, VARIANTES, registro, PackSalida(self.instancia)
        )
        limites = fabrica.limites_de_lote(motor)
        self.traductor = Traductor(
            motor, self.memoria, self.glosario, dialecto, hilos, progreso, registro, cancelar, validar,
            usar_lotes=usar_lotes, contexto=contexto, ejemplos=self.ejemplos,
            limite_caracteres=limites[0], limite_entradas=limites[1],
        )  # fmt: skip
        self.motor = motor
        if isinstance(motor, Compatible):
            motor.cancelar = self.traductor.cancelar
        if isinstance(motor, Gemini):
            motor.cancelar = self.traductor.cancelar
            motor.al_esperar = lambda estado: registro(
                f"Esperando a Google (Batch API): {_ESTADOS.get(estado, estado)}"
            )
        self._glosario_listo = False

    # ------------------------------------------------------------------ preparación
    def _preparar_glosario(self) -> None:
        if self._glosario_listo:
            return
        self.glosario.fijar(configuracion.leer_glosario_usuario())
        tabla = self.instancia.tabla_idiomas()
        orden = [self.ctx.dialecto, *(v for v in ("es_mx", "es_es", *VARIANTES) if v != self.ctx.dialecto)]
        for ns in ["minecraft", *sorted(n for n in tabla.datos if n != "minecraft")]:
            ingles = {k: v for k, v in tabla.textos(ns, "en_us").items() if es_nombre(k)}
            todo_ingles = tabla.textos(ns, "en_us")
            for variante in dict.fromkeys(orden):
                self.glosario.agregar_pares(ingles, tabla.textos(ns, variante), fuente=ns, oficial=ns == "minecraft")
                self.ejemplos.agregar(todo_ingles, tabla.textos(ns, variante))
        self.ejemplos.agregar_pares(self.memoria.recientes(self.ctx.dialecto))
        self._glosario_listo = True
        self.registro(f"Glosario: {len(self.glosario)} términos oficiales")
        if len(self.ejemplos):
            self.registro(f"Ejemplos para guiar al motor: {len(self.ejemplos)} textos ya traducidos")

    def modulos(self) -> list[tuple[str, Modulo]]:
        """Módulos elegidos, en el orden en que se traducen (mods primero: sus nombres alimentan el glosario)."""
        lista: list[tuple[str, Modulo]] = []
        if "mods" in self.grupos:
            lista.append(("mods", mods.Mods(self.ctx)))
            if self.texto_java:  # texto escrito en el código de los mods: lo muestra el mod de apoyo
                lista.append(("mods", runtime.TextoDeJava(self.ctx)))
        if "libros" in self.grupos:
            lista.append(("libros", libros.Libros(self.ctx)))
        if "misiones" in self.grupos:
            lista += [("misiones", m) for m in misiones.todos(self.ctx)]
        if "scripts" in self.grupos:
            lista += [
                ("scripts", scripts.ScriptsKubeJS(self.ctx, self.scripts_exhaustivo)),
                ("scripts", datos.Datos(self.ctx)),
            ]
        return [(g, m) for g, m in lista if m.detectar()]

    # ------------------------------------------------------------------ acciones
    def _abrir_memoria(self) -> Memoria:
        """La memoria de traducciones del usuario. Si el archivo está dañado, dice cuál es y no falla a medias."""
        ruta = configuracion.ruta_memoria()
        try:
            return Memoria(ruta)
        except sqlite3.Error as e:
            self.instancia.cerrar()
            raise ErrorFatal(
                f"La memoria de traducciones está dañada ({e}). Muévela o bórrala y vuelve a intentarlo: {ruta}"
            ) from e

    def que_queda(self, java: bool = False, progreso: Callable[[int, int], None] | None = None) -> list[Hallazgo]:
        """Lo que quedaría en inglés. Solo lee. `java`: también el texto escrito en el código de los mods (tarda)."""
        return revisar_cobertura(self.ctx, java, progreso or (lambda _a, _b: None))

    def analizar(self) -> Informe:
        """Cuenta lo que hay que traducir. Solo lee: no escribe nada en la instancia."""
        self._preparar_glosario()
        informe = Informe()
        scripts_leidos: list[scripts.ScriptsKubeJS] = []
        leidos: list[tuple[str, Modulo, list[Lugar]]] = []
        for grupo, modulo in self.modulos():
            try:
                piezas = modulo.recolectar()
            except (ValueError, OSError) as e:  # se deja fuera ese grupo y se avisa: el resto se puede traducir
                informe.avisos.append(f"{modulo.nombre}: no se pudo leer ({e}). Queda fuera de la traducción.")
                if grupo not in informe.fallidos:
                    informe.fallidos.append(grupo)
                continue
            if isinstance(modulo, scripts.ScriptsKubeJS):
                scripts_leidos.append(modulo)
            leidos.append((grupo, modulo, lugares_de(modulo, piezas)))
            pendientes = self.traductor.pendientes([p.texto for p in piezas], modulo.ambito)
            informe.modulos.append(
                InformeModulo(grupo, modulo.nombre, modulo.describir(), len({p.texto for p in piezas}),
                              len(pendientes), sum(len(t) for t in pendientes))
            )  # fmt: skip
        informe.avisos.extend(self._avisos_de_cobertura(informe, scripts_leidos))
        self._comparar_con_la_ultima(informe, leidos)
        return informe

    def _comparar_con_la_ultima(self, informe: Informe, leidos: list[tuple[str, Modulo, list[Lugar]]]) -> None:
        """Llena `informe.cambios`: qué cambió desde la última traducción y cuánto cuesta traducir solo eso.

        Compara con el índice guardado en la marca del pack. Si no hay índice (nunca se tradujo, o se tradujo con
        una versión anterior de la app), cuenta como nuevo lo que no está en la memoria ni en el glosario.
        """
        actuales = [(_grupo_del_indice(g, m), m.nombre, lugares) for g, m, lugares in leidos]
        previo = leer_indice(self.ctx.pack.leer_marca()) if self.ctx.pack is not None else None
        if previo is not None:
            indice, fecha = previo
            # Solo se compara lo que se leyó: lo demás no se miró y no por eso se borró
            indice = {n: e for n, e in indice.items() if e.get("grupo") in self._alcance()}
            informe.cambios = Cambios(comparar(indice, actuales), "indice", fecha)
        else:
            pendientes = {
                m.nombre: set(self.traductor.pendientes([t for lugar in lugares for t in _textos(lugar)], m.ambito))
                for _g, m, lugares in leidos
            }
            informe.cambios = Cambios(
                sin_indice(actuales, lambda nombre, t: separar_bordes(t)[1] in pendientes[nombre]),
                "memoria",
            )
        for grupo, modulo, _lugares in leidos:
            textos = [t for c in informe.cambios.lugares if c.modulo == modulo.nombre for t in c.textos]
            if not textos:
                continue
            pendientes_mod = self.traductor.pendientes(textos, modulo.ambito)
            informe.modulos_cambios.append(
                InformeModulo(grupo, modulo.nombre, modulo.describir(), len(set(textos)), len(pendientes_mod),
                              sum(len(t) for t in pendientes_mod))
            )  # fmt: skip

    def _avisos_de_cobertura(self, informe: Informe, scripts_leidos: list[scripts.ScriptsKubeJS]) -> list[str]:
        """Lo barato de saber antes de traducir: frases de scripts que parecen texto y no se tocan.

        Se apoya en lo que el análisis ya leyó y nunca lo detiene.
        """
        for s in scripts_leidos:
            informe.cobertura += hallazgos_de_scripts(self.instancia.juego, s.sin_elegir)
            informe.cobertura += hallazgos_de_comandos(self.instancia.juego, s.comandos_ajenos)
        if not informe.cobertura:
            return []
        return [
            f"{sum(h.cantidad for h in informe.cobertura)} frases de {len(informe.cobertura)} lugares de los scripts "
            "no se traducen (parecen texto pero puede ser lógica, o van dentro de un comando de otro mod). "
            "Detalle con «modpackes cobertura»."
        ]

    def ejecutar(self, activar: bool = True, poner_idioma: bool = True, solo_memoria: bool = False) -> Informe:
        """Traduce y escribe. Con `solo_memoria` no se llama al motor: se escribe lo que ya está en la memoria,
        las correcciones y el glosario (así se aplica un paquete importado), y lo demás queda en inglés."""
        self._preparar_glosario()
        informe = Informe()
        todas: dict[str, str] = {}
        tradujo_el_motor = False
        traducidos: list[tuple[str, str, list[Lugar]]] = []
        for grupo, modulo in self.modulos():
            self.registro(f"▶ {modulo.nombre}: {modulo.describir()}")
            piezas = modulo.recolectar()
            traducidos.append((_grupo_del_indice(grupo, modulo), modulo.nombre, lugares_de(modulo, piezas)))
            textos = [p.texto for p in piezas]
            pendientes = self.traductor.pendientes(textos, modulo.ambito)
            pistas = reunir_pistas(piezas)  # un texto que sale con varias claves lleva el contexto de todas
            if solo_memoria:
                resultado = Resultado(traducciones=self.traductor.conocidas(textos, modulo.ambito))
            else:
                resultado = self.traductor.traducir(textos, modulo.ambito, pistas)
                tradujo_el_motor = tradujo_el_motor or bool(resultado.nuevas)
            if self.revisar and grupo in GRUPOS_REVISADOS and resultado.nuevas:
                self.registro(f"   Revisando {len(resultado.nuevas)} traducciones nuevas…")
                por_nucleo = {separar_bordes(k)[1]: v for k, v in pistas.items()}
                hecha = revision.revisar_y_corregir(self.traductor, resultado.nuevas, modulo.ambito, por_nucleo)
                self.registro(f"   {hecha}")
                if informe.revision_automatica is None:
                    informe.revision_automatica = revision.ResumenRevision()
                informe.revision_automatica.sumar(hecha)
                if hecha.corregidos:  # lo rehecho ya está en la memoria: se vuelve a juntar sin pedir nada
                    resultado.traducciones = self.traductor.conocidas(textos, modulo.ambito)
            resumen = modulo.escribir(resultado.traducciones)
            self.registro(f"   {resumen}")
            informe.modulos.append(
                InformeModulo(grupo, modulo.nombre, modulo.describir(), len(set(textos)), len(pendientes),
                              sum(len(t) for t in pendientes), resumen)
            )  # fmt: skip
            if grupo != "mods":  # la revisión del glosario mira textos largos (misiones, libros, scripts)
                todas.update(resultado.traducciones)
            if isinstance(modulo, mods.Mods):
                # Los nombres recién traducidos pasan al glosario: libros, misiones y scripts los usarán igual
                nuevos = modulo.nombres(resultado.traducciones)
                self.glosario.agregar_pares({en: en for en in nuevos}, nuevos)
        if tradujo_el_motor and self.motor.nombre not in _SIN_CREDITO and self.ctx.pack is not None:
            self.ctx.pack.anotar_motores([self.motor.nombre])
        relevantes = self.glosario.relevantes(todas, maximo=500)
        informe.revision = revisar_glosario(todas, relevantes, relevantes)
        informe.avisos.extend(self._avisos())
        self._guardar_indice(traducidos, informe)
        if activar and (self.ctx.pack is not None and (self.ctx.pack.raiz / "pack.mcmeta").is_file()):
            try:
                informe.pack_activado = opciones_salida.activar(
                    self.instancia.juego, NOMBRE, self._idioma_del_juego() if poner_idioma else None,
                    con_prefijo=not self.instancia.legacy,  # «file/Nombre» desde 1.13
                )  # fmt: skip
            except ValueError as e:
                informe.avisos.append(str(e))
        return informe

    def _alcance(self) -> list[str]:
        """Los grupos del índice que esta ejecución lee: los elegidos, y «java» solo si se pidió el texto del código."""
        return [*self.grupos, *(["java"] if self.texto_java and "mods" in self.grupos else [])]

    def _guardar_indice(self, traducidos: list[tuple[str, str, list[Lugar]]], informe: Informe) -> None:
        """Guarda en la marca del pack qué textos en inglés había, para comparar en el próximo análisis."""
        pack = self.ctx.pack or PackSalida(self.instancia)
        previo = leer_indice(pack.leer_marca())
        indice = mezclar(previo[0] if previo else None, indice_de(traducidos), self._alcance())
        try:
            pack.guardar_indice(para_la_marca(indice, datetime.now(UTC).isoformat(timespec="seconds")))
        except (OSError, ValueError) as e:  # la traducción ya está escrita: solo se pierde el informe de cambios
            informe.avisos.append(f"No pude guardar el índice para el informe de cambios: {e}")

    def _idioma_del_juego(self) -> str | None:
        """Idioma a poner en options.txt: ninguno si el jugador ya usa una variante de español (se respeta),
        y con el formato de su versión (es_MX en 1.10 y anteriores)."""
        if (self.instancia.opciones.idioma or "") in VARIANTES:
            return None
        return nombre_archivo_lang(self.ctx.dialecto, self.instancia.version.partes)

    def restaurar(self) -> list[Path]:
        """Devuelve misiones, scripts y libros propios del modpack a su versión original."""
        return self.ctx.respaldo.restaurar("")

    def _avisos(self) -> list[str]:
        avisos: list[str] = []
        opciones = self.instancia.opciones
        sospechosos = [p for p in opciones.packs if "localizer" in p.lower() or "translat" in p.lower()]
        if sospechosos:
            avisos.append(
                "Hay otros packs de traducción activos que pueden tapar a este: " + ", ".join(sospechosos)
                + ". Si alguno está roto, desactívalo en el juego."
            )  # fmt: skip
        return avisos

    # ------------------------------------------------------------------ ciclo de vida
    def cerrar(self) -> None:
        if isinstance(self.motor, Compatible):
            self.motor.cerrar()
        self.instancia.cerrar()
        if self._memoria_propia:
            self.memoria.cerrar()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, tipo: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.cerrar()

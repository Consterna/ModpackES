"""Orquestador: deduplica, consulta memoria y glosario, arma lotes, valida y guarda."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import cast

from ..motores.base import Cancelado, Entrada, Lote, Motor, MotorPorLotes
from ..validacion.calidad import (
    ajustar_mayusculas,
    palabra_repetida,
    reemplazar_en_ingles,
    sin_traducir,
    terminos_faltantes,
)
from . import terminos
from .dialectos import DIALECTO_POR_DEFECTO, DIALECTOS
from .ejemplos import Ejemplos
from .glosario import Glosario
from .mascara import Enmascarado, desenmascarar, enmascarar, es_traducible, separar_bordes
from .memoria import Memoria

Progreso = Callable[[int, int], None]
Registro = Callable[[str], None]
#: Recibe (original, traducción) y devuelve el motivo del rechazo, o None si es válida.
Validador = Callable[[str, str], str | None]
#: Largo máximo del contexto del modpack que va en cada pedido: más que esto encarece sin mejorar.
LARGO_CONTEXTO = 400
#: Lo que se le dice al motor cuando devolvió igual un nombre que sí se traduce.
AVISO_SIN_TRADUCIR = (
    "La primera vez lo devolviste igual al original: tradúcelo al español (solo es igual un nombre propio)."
)
#: Prefijo del motivo de rechazo cuando falta un término del glosario; lo que sigue es «inglés=español; …».
MOTIVO_TERMINOLOGIA = "terminología: "
#: Prefijo del motivo de rechazo cuando la traducción repite una palabra que el original no repite.
MOTIVO_REPETIDA = "palabra repetida: "
AVISO_TERMINO = "Término que se repite en los nombres de este modpack: tradúcelo suelto, como se diría de un objeto."
#: Lo que se le dice al motor de un nombre propio que se repite en las misiones o los libros.
AVISO_NOMBRE = (
    "Nombre propio que se repite en los textos de este modpack: decide una sola traducción para todos. El nombre "
    "de un jefe, una criatura única, una dimensión o un mod se deja igual; un lugar, objeto o grupo con nombre "
    "común (mazmorras, llaves…) se traduce."
)
#: Ámbitos de frases largas donde se buscan nombres propios que se repiten.
_AMBITOS_CON_NOMBRES = frozenset({"mision", "libro"})


def _nada(*_: object) -> None:
    return None


@dataclass(slots=True)
class Resultado:
    traducciones: dict[str, str] = field(default_factory=dict[str, str])
    rechazados: dict[str, str] = field(default_factory=dict[str, str])  #: original → motivo
    enviados: int = 0
    #: Lo que el motor tradujo en esta ejecución (núcleo → traducción), sin lo que salió de la memoria
    nuevas: dict[str, str] = field(default_factory=dict[str, str])
    #: Primera traducción de lo rechazado por términos o repeticiones (núcleo → borrador): el reintento la corrige
    borradores: dict[str, str] = field(default_factory=dict[str, str])
    #: Lo que se aceptó en el reintento sin cumplir todas las reglas (núcleo → motivo): conviene revisarlo
    dudosos: dict[str, str] = field(default_factory=dict[str, str])


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
        contexto: str = "",
        ejemplos: Ejemplos | None = None,
        glosario_estricto: bool = True,
        controles_de_forma: bool = True,
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
        self.contexto = " ".join(contexto.split())[:LARGO_CONTEXTO]
        #: Traducciones ya hechas de textos parecidos; crece con lo que se traduce en esta ejecución
        self.ejemplos = ejemplos if ejemplos is not None else Ejemplos()
        #: Rechazar (y reintentar con aviso) una traducción a la que le falta un término del glosario
        self.glosario_estricto = glosario_estricto
        #: Mayúsculas del glosario, nombres que no se traducen, palabras repetidas y reparación del reintento.
        #: Solo se apaga para medir cuánto aportan.
        self.controles_de_forma = controles_de_forma
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ consulta
    def _conocida(self, nucleo: str, ambito: str, correcciones: Mapping[str, str]) -> str | None:
        """Lo que el usuario corrigió o fijó manda; después, lo ya traducido; después, los nombres oficiales.

        `correcciones` se lee una vez por llamada pública (son pocas): así no se consulta la base por cada texto.
        """
        return (
            correcciones.get(nucleo)
            or self.glosario.fijo(nucleo)
            or self.memoria.obtener(nucleo, self.dialecto, ambito)
            or self.glosario.exacto(nucleo)
        )

    def pendientes(self, textos: Iterable[str], ambito: str) -> list[str]:
        """Núcleos únicos que habría que mandar al motor (lo demás sale de memoria o glosario)."""
        correcciones = self.memoria.correcciones(self.dialecto)
        vistos: set[str] = set()
        for t in textos:
            if es_traducible(t):
                nucleo = separar_bordes(t)[1]
                if nucleo not in vistos and self._conocida(nucleo, ambito, correcciones) is None:
                    vistos.add(nucleo)
        return sorted(vistos)

    def conocidas(self, textos: Iterable[str], ambito: str) -> dict[str, str]:
        """{texto: traducción} de lo que ya se sabe (corrección, glosario o memoria), sin pedir nada al motor."""
        correcciones = self.memoria.correcciones(self.dialecto)
        salida: dict[str, str] = {}
        for t in {t for t in textos if es_traducible(t)}:
            inicio, nucleo, fin = separar_bordes(t)
            hecho = self._conocida(nucleo, ambito, correcciones)
            if hecho is not None:
                salida[t] = inicio + hecho + fin
        return salida

    # ------------------------------------------------------------------ traducción
    def traducir(self, textos: Iterable[str], ambito: str, pistas: Mapping[str, str] | None = None) -> Resultado:
        """Traduce y devuelve {texto original: traducción}. Lo que no se pudo traducir con garantías no aparece."""
        # Las pistas se buscan por el núcleo (sin espacios de borde), igual que la memoria
        pistas = {separar_bordes(k)[1]: v for k, v in (pistas or {}).items()}
        resultado = Resultado()
        unicos = {t for t in textos if es_traducible(t)}
        faltan = self.pendientes(unicos, ambito)
        if faltan and ambito == "ui" and self._unificar_terminos(faltan, ambito):
            faltan = self.pendientes(unicos, ambito)
        elif faltan and ambito in _AMBITOS_CON_NOMBRES and self.controles_de_forma:
            self._unificar_nombres(faltan, ambito)
        if faltan:
            nucleos = self._ronda(faltan, ambito, pistas, (self.limite_caracteres, self.limite_entradas), resultado)
            if nucleos and not self.cancelar.is_set():
                self.registro(f"Reintentando {len(nucleos)} textos que no pasaron la validación…")
                # A los que volvieron iguales al original se les avisa; si siguen iguales se aceptan (nombres propios)
                reintento = dict(pistas)
                for n in nucleos:
                    aviso = self._aviso_de_reintento(resultado.rechazados.get(n, ""), resultado.borradores.get(n))
                    if aviso:
                        reintento[n] = f"{pistas[n]} · {aviso}" if pistas.get(n) else aviso
                resultado.rechazados.clear()
                resultado.borradores.clear()
                # Lotes chicos y sin mover la barra de progreso, que ya llegó al total
                # (en modo normal aunque se use la Batch API: son pocos y no vale la pena esperar otro trabajo)
                self._ronda(
                    sorted(nucleos), ambito, reintento, (1500, 5), resultado,
                    informar=False, por_lotes=False, tolerante=True,
                )  # fmt: skip
            if resultado.rechazados:
                n = len(resultado.rechazados)
                self.registro(f"{n} textos se quedan en inglés porque no pasaron la validación.")
            if resultado.dudosos:
                self.registro(f"{len(resultado.dudosos)} textos se aceptaron con dudas (términos o repeticiones).")
        resultado.traducciones = self.conocidas(unicos, ambito)
        return resultado

    @staticmethod
    def _aviso_de_reintento(motivo: str, borrador: str | None = None) -> str:
        """Qué decirle al motor en el segundo intento según por qué se rechazó el primero.

        Si hay un borrador, se le pide que corrija solo lo que falló y deje el resto igual: rehacer todo el texto
        cambia cosas que estaban bien.
        """
        if motivo == "sin traducir":
            return AVISO_SIN_TRADUCIR
        if motivo.startswith(MOTIVO_TERMINOLOGIA):
            regla = f"usa exactamente estos términos del glosario: {motivo.removeprefix(MOTIVO_TERMINOLOGIA)}"
        elif motivo.startswith(MOTIVO_REPETIDA):
            regla = f"no repitas «{motivo.removeprefix(MOTIVO_REPETIDA)}»: el original no repite esa palabra"
        else:
            return ""
        if borrador:
            return f"Tu primera traducción fue «{borrador}». Corrige solo esto y deja lo demás igual: {regla}."
        return regla[0].upper() + regla[1:] + "."

    def _unificar_terminos(self, faltan: list[str], ambito: str) -> bool:
        """Traduce primero los términos que se repiten en los nombres y los fija en el glosario del pack.

        Devuelve True si fijó alguno (y entonces hay que volver a calcular qué falta).
        """
        correcciones = self.memoria.correcciones(self.dialecto)
        candidatos = [t for t in terminos.repetidos(faltan) if self._conocida(t, ambito, correcciones) is None]
        if not candidatos or self.cancelar.is_set():
            return False
        parcial = Resultado()
        pistas = dict.fromkeys(candidatos, AVISO_TERMINO)
        self._ronda(candidatos, ambito, pistas, (1500, 40), parcial, informar=False, por_lotes=False)
        hallados = {t: parcial.nuevas[t] for t in candidatos if t in parcial.nuevas}
        if hallados:
            self.glosario.descubrir(hallados)
            self.registro(f"{len(hallados)} términos que se repiten se tradujeron primero, para que todo use el mismo")
        return bool(hallados)

    def _unificar_nombres(self, faltan: list[str], ambito: str) -> None:
        """Decide una vez cómo se escribe cada nombre propio que se repite en las frases y lo fija en el glosario.

        Sin esto, el modelo deja «Arachnarch» en un texto y escribe «Aracnarca» en otro. Los nombres que ya están en
        el glosario (del juego, de los mods o del usuario) no se vuelven a pedir.
        """
        conocidos = self.glosario.todos()
        candidatos = [n for n in terminos.nombres_propios(faltan) if n not in conocidos]
        if not candidatos or self.cancelar.is_set():
            return
        parcial = Resultado()
        pistas = dict.fromkeys(candidatos, AVISO_NOMBRE)
        self._ronda(candidatos, ambito, pistas, (1500, 40), parcial, informar=False, por_lotes=False, tolerante=True)
        hallados = {n: parcial.nuevas[n] for n in candidatos if n in parcial.nuevas}
        if hallados:
            self.glosario.descubrir(hallados)
            iguales = sum(1 for en, es in hallados.items() if en == es)
            self.registro(
                f"{len(hallados)} nombres propios que se repiten se decidieron primero "
                f"({iguales} quedan sin traducir), para que todos los textos los escriban igual"
            )

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
        tolerante: bool = False,
    ) -> set[str]:
        """Traduce una ronda. Devuelve los núcleos que fallaron."""
        fallidos: set[str] = set()
        hechos = 0
        total = len(nucleos)
        progreso = self.progreso if informar else _nada
        progreso(0, total)
        if self.usar_lotes and por_lotes:
            return self._ronda_por_lotes(self._lotes(nucleos, *limites), ambito, pistas, resultado, progreso, tolerante)
        with ThreadPoolExecutor(self.hilos) as ex:
            futuros: dict[Future[dict[str, str]], list[str]] = {
                ex.submit(self._lote, lote, ambito, pistas, resultado, tolerante): lote
                for lote in self._lotes(nucleos, *limites)
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
        tolerante: bool = False,
    ) -> set[str]:
        pedidos = [self._pedido(lote, ambito, pistas) for lote in lotes]
        salidas = cast(MotorPorLotes, self.motor).traducir_varios([p for p, _ in pedidos])
        fallidos: set[str] = set()
        hechos = 0
        total = sum(len(lote) for lote in lotes)
        for lote, (pedido, mascaras), salida in zip(lotes, pedidos, salidas, strict=True):
            buenos = self._procesar(lote, mascaras, salida, resultado, tolerante, pedido.glosario)
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
        lote_motor = Lote(
            entradas, ambito, DIALECTOS[self.dialecto], self.glosario.relevantes(lote), self.contexto,
            ejemplos=self.ejemplos.parecidos(lote),
        )  # fmt: skip
        return lote_motor, mascaras

    def _lote(
        self, lote: list[str], ambito: str, pistas: Mapping[str, str], resultado: Resultado, tolerante: bool = False
    ) -> dict[str, str]:
        if self.cancelar.is_set():
            return {}
        pedido, mascaras = self._pedido(lote, ambito, pistas)
        return self._procesar(lote, mascaras, self.motor.traducir_lote(pedido), resultado, tolerante, pedido.glosario)

    def _procesar(
        self,
        lote: list[str],
        mascaras: list[Enmascarado],
        salida: Mapping[str, str],
        resultado: Resultado,
        tolerante: bool = False,
        glosario: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        buenos: dict[str, str] = {}
        rechazados: dict[str, str] = {}
        borradores: dict[str, str] = {}
        dudosos: dict[str, str] = {}
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
            if self.controles_de_forma:  # determinista: palabras que no son del juego («inframundita»)
                final = self.glosario.corregir(final)
            if glosario and self.controles_de_forma:  # determinista: mayúsculas de los nombres propios del glosario
                final = ajustar_mayusculas(n, final, self._con_mayusculas(glosario))
            motivo = self._motivo_de_forma(n, final, glosario)
            if motivo and tolerante:  # segundo intento: se arregla lo que se pueda y se acepta, marcado
                if self.controles_de_forma:
                    final, motivo = self._reparar(n, final, glosario, motivo)
                    if motivo:
                        dudosos[n] = motivo
            elif motivo:
                rechazados[n] = motivo
                borradores[n] = final
                continue
            buenos[n] = final
        self.ejemplos.agregar_pares(buenos)  # lo que ya se tradujo guía a los lotes que faltan
        with self._lock:
            resultado.enviados += len(lote)
            resultado.rechazados.update(rechazados)
            resultado.borradores.update(borradores)
            resultado.dudosos.update(dudosos)
            resultado.nuevas.update(buenos)
        return buenos

    def _motivo_de_forma(self, original: str, final: str, glosario: Mapping[str, str] | None) -> str | None:
        """Reglas que un reintento puede arreglar: sin traducir, términos del glosario y palabras repetidas."""
        if sin_traducir(original, final):
            return "sin traducir"
        if glosario and self.glosario_estricto:
            exigidos = glosario if self.controles_de_forma else {en: es for en, es in glosario.items() if en != es}
            faltan = terminos_faltantes(original, final, exigidos)
            if faltan:
                return MOTIVO_TERMINOLOGIA + "; ".join(f"«{en}» = «{es}»" for en, es in faltan.items())
        repetida = palabra_repetida(original, final) if self.controles_de_forma else None
        return MOTIVO_REPETIDA + repetida if repetida else None

    def _con_mayusculas(self, glosario: Mapping[str, str]) -> dict[str, str]:
        """Términos cuyas mayúsculas se respetan: los del pack y del usuario. Los del juego («Cofre») no: en medio
        de una frase en español los objetos del juego van en minúscula."""
        return {en: es for en, es in glosario.items() if not self.glosario.del_juego(en)}

    def _reparar(
        self, original: str, final: str, glosario: Mapping[str, str] | None, motivo: str
    ) -> tuple[str, str | None]:
        """Arreglo determinista en el reintento: un término del glosario que quedó en inglés se cambia por el suyo.

        Devuelve la traducción y el motivo que sigue sin resolverse (None si quedó bien). Lo que vuelve igual al
        original en el reintento se acepta sin marcar: es un nombre propio.
        """
        if motivo == "sin traducir":
            return final, None
        if motivo.startswith(MOTIVO_TERMINOLOGIA) and glosario:
            faltan = terminos_faltantes(original, final, glosario)
            final, siguen = reemplazar_en_ingles(final, faltan, original)
            final = ajustar_mayusculas(original, final, self._con_mayusculas(glosario))
            if not siguen:
                return final, None
            return final, MOTIVO_TERMINOLOGIA + "; ".join(f"«{en}» = «{es}»" for en, es in siguen.items())
        return final, motivo

    # ------------------------------------------------------------------ revisión
    def rehacer(self, motivos: Mapping[str, tuple[str, str]], ambito: str, pistas: Mapping[str, str]) -> dict[str, str]:
        """Vuelve a traducir núcleos que una revisión marcó, aunque estén en la memoria.

        `motivos` es {núcleo: (traducción anterior, motivo)}. La nueva traducción reemplaza a la anterior en la
        memoria solo si pasa las mismas reglas; si no, queda la anterior. Devuelve las que cambiaron.
        """
        if not motivos:
            return {}
        pistas_nuevas: dict[str, str] = {}
        for n, (anterior, motivo) in motivos.items():
            aviso = f"Una revisión marcó la traducción anterior («{anterior}»): {motivo}. Corrígela."
            pistas_nuevas[n] = f"{pistas[n]} · {aviso}" if pistas.get(n) else aviso
        resultado = Resultado()
        self._ronda(sorted(motivos), ambito, pistas_nuevas, (1500, 10), resultado, informar=False, por_lotes=False)
        return {n: t for n, t in resultado.nuevas.items() if t != motivos[n][0]}

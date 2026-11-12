"""Ejemplos: traducciones ya hechas de textos parecidos, para que el modelo siga los mismos términos y estilo.

Se alimenta con el español que ya traen los mods del modpack, con la memoria de traducciones y con lo que se
va traduciendo en esta misma ejecución. Para cada lote se buscan los pares cuyo original comparte más palabras
poco comunes con los textos del lote (como una búsqueda por relevancia, sin servicios externos).
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping

from .mascara import enmascarar, es_traducible

_PALABRA = re.compile(r"[^\W\d_]{3,}")
_MIN_LARGO = 8
_MAX_LARGO = 160
#: Palabras tan comunes que no dicen nada sobre el parecido de dos textos.
_COMUNES = frozenset({
    "the", "and", "for", "with", "your", "you", "this", "that", "from", "are", "will", "can", "not", "has", "have",
    "when", "into", "its", "all", "any", "per", "out", "use", "used", "uses",
})  # fmt: skip
#: Una palabra que sale en más de esta parte de los pares no sirve para buscar.
_FRECUENCIA_MAXIMA = 0.2
#: Cuántos ejemplos se mandan por lote en la aplicación. Cero: con Gemini y referencias limpias, mandar ejemplos
#: de otros mods bajó el chrF (docs/calidad.md); queda para probar con modelos locales (`--n-ejemplos`).
CANTIDAD_EN_LA_APP = 0


def _palabras(texto: str) -> set[str]:
    return {p for p in (m.lower() for m in _PALABRA.findall(texto)) if p not in _COMUNES}


class Ejemplos:
    """Pares (inglés → español) con índice de palabras. Seguro para varios hilos."""

    def __init__(self, maximo: int = 200_000, cantidad: int = 8) -> None:
        self._maximo = maximo
        self.cantidad = cantidad
        self._pares: dict[str, str] = {}
        self._indice: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._pares)

    def _valido(self, ingles: str, espanol: str) -> bool:
        en, es = ingles.strip(), espanol.strip()
        if not (_MIN_LARGO <= len(en) <= _MAX_LARGO and es and en != es and es_traducible(en)):
            return False
        # Un ejemplo con códigos (§a, %s, <b>…) confundiría las reglas de los marcadores ⟦0⟧
        return not enmascarar(en).tokens

    def agregar_pares(self, pares: Mapping[str, str]) -> None:
        """Agrega {inglés: español}. Lo primero que entra tiene prioridad sobre lo que llega después."""
        with self._lock:
            for en, es in pares.items():
                if len(self._pares) >= self._maximo:
                    return
                clave = en.strip()
                if clave in self._pares or not self._valido(en, es):
                    continue
                self._pares[clave] = es.strip()
                for palabra in _palabras(clave):
                    self._indice.setdefault(palabra, []).append(clave)

    def agregar(self, ingles: Mapping[str, object], traducido: Mapping[str, object]) -> None:
        """Agrega las claves que existen en los dos idiomas (como los archivos de idioma de un mod)."""
        self.agregar_pares(
            {
                en: es
                for clave, en in ingles.items()
                if isinstance(en, str) and isinstance(es := traducido.get(clave), str)
            }
        )

    def parecidos(self, textos: Iterable[str], cantidad: int | None = None, largo_total: int = 700) -> dict[str, str]:
        """Los pares más relevantes para estos textos, sin los textos mismos."""
        cantidad = self.cantidad if cantidad is None else cantidad
        propios = {t.strip() for t in textos}
        buscadas = Counter(p for t in propios for p in _palabras(t))
        with self._lock:
            total = max(len(self._pares), 1)
            puntaje: defaultdict[str, float] = defaultdict(float)
            for palabra in buscadas:
                candidatos = self._indice.get(palabra, ())
                if not candidatos or (len(candidatos) > _FRECUENCIA_MAXIMA * total and total > 50):
                    continue
                peso = math.log(1 + total / len(candidatos))
                for c in candidatos:
                    puntaje[c] += peso
            elegidos: dict[str, str] = {}
            usado = 0
            # Se prefieren los textos cortos con el mismo puntaje: son los que más se parecen a un nombre
            ranking = sorted(
                (c for c in puntaje if c not in propios),
                key=lambda c: (-puntaje[c] / math.sqrt(len(_palabras(c)) or 1), len(c)),
            )
            for c in ranking:
                es = self._pares[c]
                if usado + len(c) + len(es) > largo_total:
                    continue
                elegidos[c] = es
                usado += len(c) + len(es)
                if len(elegidos) >= cantidad:
                    break
        return elegidos

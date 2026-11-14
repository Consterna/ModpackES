"""Glosario: nombres oficiales (Minecraft y mods ya traducidos) para que todo use los mismos términos."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .mascara import es_traducible

_MAX_LARGO = 48
#: Un nombre propio que no se traduce tiene pocas palabras, y todas las largas empiezan con mayúscula.
_MAX_PALABRAS_NOMBRE = 3


def _parece_nombre_propio(texto: str) -> bool:
    palabras = texto.split()
    if not palabras or len(palabras) > _MAX_PALABRAS_NOMBRE or not any(c.isalpha() for c in texto):
        return False
    return all(p[0].isupper() or len(p) <= 3 for p in palabras) and palabras[0][0].isupper()


class Glosario:
    def __init__(self) -> None:
        self._terminos: dict[str, str] = {}
        self._fijos: dict[str, str] = {}
        self._orden: list[tuple[str, str, re.Pattern[str]]] | None = None
        self._fuente: dict[str, str] = {}  #: de quién salió cada término (un mod, el juego…)
        self._oficiales: set[str] = set()  #: términos del propio juego: no se discuten
        self._en_conflicto: set[str] = set()  #: dos mods lo traducen distinto: no se usa ninguno

    def __len__(self) -> int:
        return len(self._terminos) + len(self._fijos)

    def agregar_pares(
        self,
        ingles: Mapping[str, object],
        traducido: Mapping[str, object],
        fuente: str = "",
        oficial: bool = False,
        proteger_iguales: bool = False,
    ) -> None:
        """Toma las claves que existen en ambos idiomas.

        Dentro de una misma `fuente` (un mod, y sus variantes de español) lo primero que se agrega manda.
        Entre fuentes distintas: lo `oficial` (el propio juego) gana a un mod, y si dos mods traducen
        distinto el mismo término, no se usa ninguno de los dos: una traducción ajena que no encaja
        (el «Cow» de un mod que lo llama «Acechador de medianoche») se impondría a todo el modpack.

        Un nombre que queda igual en los dos idiomas («Creeper», «Redstone») solo entra con `proteger_iguales`:
        sirve para fuentes de fiar (el juego, lo ya traducido en esta ejecución). En el español de un mod, un
        texto igual al inglés suele ser una traducción a medias, y protegerlo dejaría ese texto en inglés.
        """
        for clave, valor_en in ingles.items():
            valor_es = traducido.get(clave)
            if not isinstance(valor_en, str) or not isinstance(valor_es, str):
                continue
            en, es = valor_en.strip(), valor_es.strip()
            if not (3 <= len(en) <= _MAX_LARGO and es and es_traducible(en) and "%" not in en):
                continue
            if en != es or (proteger_iguales and _parece_nombre_propio(en)):
                self._agregar(en, es, fuente, oficial)
        self._orden = None

    def _agregar(self, en: str, es: str, fuente: str, oficial: bool) -> None:
        if en in self._en_conflicto:
            return
        actual = self._terminos.get(en)
        if actual is None:
            self._terminos[en], self._fuente[en] = es, fuente
            if oficial:
                self._oficiales.add(en)
        elif actual == es or self._fuente[en] == fuente or en in self._oficiales:
            return
        elif oficial:  # lo del juego reemplaza a lo que dijo un mod
            self._terminos[en], self._fuente[en] = es, fuente
            self._oficiales.add(en)
        else:  # dos mods dicen cosas distintas: ninguno es de fiar
            del self._terminos[en]
            del self._fuente[en]
            self._en_conflicto.add(en)

    def todos(self) -> dict[str, str]:
        """Todos los términos que se mandarían al motor ({inglés: español}); los del usuario mandan."""
        return {**self._terminos, **self._fijos}

    @property
    def en_conflicto(self) -> frozenset[str]:
        """Términos que dos mods traducen distinto y que por eso no están en el glosario."""
        return frozenset(self._en_conflicto)

    def descubrir(self, terminos: Mapping[str, str]) -> None:
        """Términos hallados en esta ejecución (los que se repiten en el modpack): no pisan a los oficiales."""
        for en, es in terminos.items():
            if en.strip() and es.strip():
                self._terminos.setdefault(en.strip(), es.strip())
        self._orden = None

    def fijar(self, terminos: Mapping[str, str]) -> None:
        """Términos del usuario: mandan sobre todo lo demás."""
        self._fijos.update({k.strip(): v.strip() for k, v in terminos.items() if k.strip() and v.strip()})
        self._orden = None

    def del_juego(self, termino: str) -> bool:
        """¿El término sale del propio juego (y el usuario no lo cambió)?"""
        return termino in self._oficiales and termino not in self._fijos

    def exacto(self, texto: str) -> str | None:
        t = texto.strip()
        return self._fijos.get(t) or self._terminos.get(t)

    def fijo(self, texto: str) -> str | None:
        """Solo los términos del usuario: mandan incluso sobre lo que ya está en la memoria."""
        return self._fijos.get(texto.strip())

    def _ordenados(self) -> list[tuple[str, str, re.Pattern[str]]]:
        orden = self._orden
        if orden is None:
            todos = {**self._terminos, **self._fijos}
            # Cada patrón se compila una sola vez; luego se reutiliza en todos los lotes.
            orden = [
                (k.lower(), k, re.compile(r"(?<![^\W_])" + re.escape(k.lower()) + r"(?![^\W_])"))
                for k in sorted(todos, key=len, reverse=True)
            ]
            self._orden = orden
        return orden

    def relevantes(self, textos: Iterable[str], maximo: int = 60) -> dict[str, str]:
        """Términos que aparecen como palabra completa en los textos, priorizando los más largos."""
        bloque = "\n".join(textos).lower()
        elegidos: dict[str, str] = {}
        for bajo, original, patron in self._ordenados():
            if bajo in bloque and patron.search(bloque):
                elegidos[original] = self._fijos.get(original) or self._terminos[original]
                if len(elegidos) >= maximo:
                    break
        return elegidos

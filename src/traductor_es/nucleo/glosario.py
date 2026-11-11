"""Glosario: nombres oficiales (Minecraft y mods ya traducidos) para que todo use los mismos términos."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .mascara import es_traducible

_MAX_LARGO = 48


class Glosario:
    def __init__(self) -> None:
        self._terminos: dict[str, str] = {}
        self._fijos: dict[str, str] = {}
        self._orden: list[tuple[str, str, re.Pattern[str]]] | None = None

    def __len__(self) -> int:
        return len(self._terminos) + len(self._fijos)

    def agregar_pares(self, ingles: Mapping[str, object], traducido: Mapping[str, object]) -> None:
        """Toma las claves que existen en ambos idiomas. Lo primero que se agrega tiene prioridad."""
        for clave, valor_en in ingles.items():
            valor_es = traducido.get(clave)
            if not isinstance(valor_en, str) or not isinstance(valor_es, str):
                continue
            en, es = valor_en.strip(), valor_es.strip()
            if 3 <= len(en) <= _MAX_LARGO and en != es and es and es_traducible(en) and "%" not in en:
                self._terminos.setdefault(en, es)
        self._orden = None

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

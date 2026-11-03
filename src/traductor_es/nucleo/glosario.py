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
        self._orden: list[tuple[str, str]] | None = None

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

    def fijar(self, terminos: Mapping[str, str]) -> None:
        """Términos del usuario: mandan sobre todo lo demás."""
        self._fijos.update({k.strip(): v.strip() for k, v in terminos.items() if k.strip()})
        self._orden = None

    def exacto(self, texto: str) -> str | None:
        t = texto.strip()
        return self._fijos.get(t) or self._terminos.get(t)

    def relevantes(self, textos: Iterable[str], maximo: int = 60) -> dict[str, str]:
        """Términos que aparecen como palabra completa en los textos, priorizando los más largos."""
        if self._orden is None:
            todos = {**self._terminos, **self._fijos}
            self._orden = sorted(((k.lower(), k) for k in todos), key=lambda par: len(par[0]), reverse=True)
        bloque = "\n".join(textos).lower()
        elegidos: dict[str, str] = {}
        for bajo, original in self._orden:
            if bajo in bloque and re.search(r"(?<![^\W_])" + re.escape(bajo) + r"(?![^\W_])", bloque):
                elegidos[original] = self._fijos.get(original) or self._terminos[original]
                if len(elegidos) >= maximo:
                    break
        return elegidos

"""Glosario: nombres oficiales (Minecraft y mods ya traducidos) para que todo use los mismos términos."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from ..validacion.calidad import PALABRA, sale_el_termino, uso_como_nombre
from .mascara import es_traducible, sin_formato

_MAX_LARGO = 48
#: Un nombre propio que no se traduce tiene pocas palabras, y todas las largas empiezan con mayúscula.
_MAX_PALABRAS_NOMBRE = 3
#: Textos en español que se guardan por cada palabra inglesa en minúscula, para ver cómo se traduce.
_MAX_USOS = 30
#: Hace falta ver una palabra en minúscula al menos estas veces para decir que tiene otro sentido.
_MIN_USOS = 2


def parece_nombre_propio(texto: str) -> bool:
    """Pocas palabras, la primera con mayúscula y las largas también («Arachnarch», «Bronze Dungeons»)."""
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
        #: Palabras del español que se cambian en lo que traen el juego y los mods («ítems» → «objetos»);
        #: el glosario del usuario no se toca
        self._sustituciones: list[tuple[re.Pattern[str], str]] = []
        self._descubiertos: dict[str, str] = {}  #: lo que se decidió en esta ejecución (términos y nombres)
        #: Palabra inglesa en minúscula → textos en español donde sale (del juego y los mods ya traducidos)
        self._usos: dict[str, list[str]] = {}
        self._palabras_es: set[str] = set()  #: palabras del español de esos textos (sin mayúsculas)
        self._ambiguos: dict[tuple[str, str], bool] = {}
        self._marcas: set[str] = set()  #: nombres de mods («create»): no son inglés a medio traducir

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
            if en != es or (proteger_iguales and parece_nombre_propio(en)):
                self._agregar(en, es, fuente, oficial)
        self._orden = None

    def aprender_usos(self, ingles: Mapping[str, object], traducido: Mapping[str, object]) -> None:
        """Aprende de un archivo en inglés y su traducción cómo se usan las palabras en minúscula.

        Sirve para saber cuándo un término de una palabra tiene otro sentido: «lead» en «lead the way» no es la
        «Rienda» del juego. Si en estos textos la palabra en minúscula casi nunca sale traducida con el término, en
        minúscula se trata como palabra común (ver `ambiguo`).
        """
        for clave, valor_en in ingles.items():
            valor_es = traducido.get(clave)
            if not isinstance(valor_en, str) or not isinstance(valor_es, str) or valor_en.strip() == valor_es.strip():
                continue
            limpio = sin_formato(valor_es)
            self._palabras_es.update(p.casefold() for p in PALABRA.findall(limpio))
            for palabra in {p for p in PALABRA.findall(sin_formato(valor_en)) if p.islower() and len(p) >= 3}:
                usos = self._usos.setdefault(palabra, [])
                if len(usos) < _MAX_USOS:
                    usos.append(limpio)
        self._ambiguos.clear()
        self._orden = None

    def ambiguo(self, termino: str) -> bool:
        """¿Un término de una palabra que, escrito en minúscula, suele tener otro sentido?

        Se mira en los textos aprendidos con `aprender_usos`: si la palabra sale en minúscula al menos dos veces y
        en menos de la mitad la traducción usa el término, es una palabra común («string», «lead»). Las del usuario
        nunca son ambiguas: mandan siempre.
        """
        if termino in self._fijos or " " in termino.strip():
            return False
        traduccion = self._terminos.get(termino)
        usos = self._usos.get(termino.casefold())
        if not traduccion or not usos or len(usos) < _MIN_USOS:
            return False
        clave = (termino, traduccion)
        if clave not in self._ambiguos:
            aciertos = sum(1 for es in usos if sale_el_termino(traduccion, es))
            self._ambiguos[clave] = aciertos < len(usos) / 2
        return self._ambiguos[clave]

    def ambiguos(self, terminos: Iterable[str]) -> frozenset[str]:
        """Los términos de una palabra que en minúscula tienen otro sentido (ver `ambiguo`)."""
        return frozenset(t for t in terminos if self.ambiguo(t))

    def proteger_nombres(self, nombres: Iterable[str]) -> None:
        """Nombres de mods y marcas («create», «mekanism»): que salgan en español no es una traducción a medias."""
        self._marcas.update(n.casefold() for n in nombres)
        self._orden = None

    def _a_medias(self, en: str, es: str) -> bool:
        """¿Una traducción de un mod a medio hacer («Iron Gear» → «Engranaje de Iron»)?

        Lo es si comparte con el inglés una palabra de 4 letras o más que en inglés se escribe en minúscula y que no
        sale en ningún texto en español aprendido. «Redstone» sí sale en el español del juego, así que «Motor de
        redstone» vale; «iron» no.
        """
        if not self._usos or en == es:
            return False
        ingles = {p.casefold() for p in PALABRA.findall(en) if len(p) >= 4}
        return any(
            p.casefold() in ingles
            and p.casefold() in self._usos
            and p.casefold() not in self._palabras_es
            and p.casefold() not in self._marcas
            for p in PALABRA.findall(es)
        )

    def sustituir(self, palabras: Mapping[str, str]) -> None:
        """Cambia esas palabras (sin distinguir mayúsculas) en lo que se agregue después, salvo lo del usuario."""
        for vieja, nueva in palabras.items():
            self._sustituciones.append((re.compile(r"(?<![^\W_])" + re.escape(vieja) + r"(?![^\W_])", re.I), nueva))

    def corregir(self, texto: str) -> str:
        """Cambia en una traducción las palabras que no son del juego («inframundita» → «netherita»)."""
        return self._normalizar(texto)

    def _normalizar(self, es: str) -> str:
        for patron, nueva in self._sustituciones:
            es = patron.sub(lambda m, n=nueva: n[0].upper() + n[1:] if m.group(0)[0].isupper() else n, es)
        return es

    def _agregar(self, en: str, es: str, fuente: str, oficial: bool) -> None:
        es = self._normalizar(es)
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

    def _validos(self) -> dict[str, str]:
        """Los términos de los mods sin los que quedaron a medio traducir; los del juego y del usuario, todos."""
        return {en: es for en, es in self._terminos.items() if en in self._oficiales or not self._a_medias(en, es)}

    def todos(self) -> dict[str, str]:
        """Todos los términos que se mandarían al motor ({inglés: español}); los del usuario mandan."""
        return {**self._validos(), **self._fijos}

    @property
    def en_conflicto(self) -> frozenset[str]:
        """Términos que dos mods traducen distinto y que por eso no están en el glosario."""
        return frozenset(self._en_conflicto)

    def descubrir(self, terminos: Mapping[str, str]) -> None:
        """Términos hallados en esta ejecución (los que se repiten en el modpack): no pisan a los oficiales."""
        for en, es in terminos.items():
            if en.strip() and es.strip():
                self._terminos.setdefault(en.strip(), es.strip())
                self._descubiertos.setdefault(en.strip(), self._terminos[en.strip()])
        self._orden = None

    def descubiertos(self) -> dict[str, str]:
        """Lo que se decidió en esta ejecución con `descubrir` ({inglés: español})."""
        return dict(self._descubiertos)

    def fijar(self, terminos: Mapping[str, str]) -> None:
        """Términos del usuario: mandan sobre todo lo demás."""
        self._fijos.update({k.strip(): v.strip() for k, v in terminos.items() if k.strip() and v.strip()})
        self._orden = None

    def del_juego(self, termino: str) -> bool:
        """¿El término sale del propio juego (y el usuario no lo cambió)?"""
        return termino in self._oficiales and termino not in self._fijos

    def exacto(self, texto: str) -> str | None:
        t = texto.strip()
        if t in self._fijos:
            return self._fijos[t]
        es = self._terminos.get(t)
        return es if es is not None and (t in self._oficiales or not self._a_medias(t, es)) else None

    def fijo(self, texto: str) -> str | None:
        """Solo los términos del usuario: mandan incluso sobre lo que ya está en la memoria."""
        return self._fijos.get(texto.strip())

    def _ordenados(self) -> list[tuple[str, str, re.Pattern[str]]]:
        orden = self._orden
        if orden is None:
            todos = {**self._validos(), **self._fijos}
            # Cada patrón se compila una sola vez; luego se reutiliza en todos los lotes.
            orden = [
                (k.lower(), k, re.compile(r"(?<![^\W_])" + re.escape(k.lower()) + r"(?![^\W_])"))
                for k in sorted(todos, key=len, reverse=True)
            ]
            self._orden = orden
        return orden

    def relevantes(self, textos: Iterable[str], maximo: int = 60) -> dict[str, str]:
        """Términos que aparecen como palabra completa en los textos, priorizando los más largos.

        Un término de una palabra con otro sentido en minúscula («lead the way») solo cuenta si algún texto lo
        usa como nombre (ver `ambiguo`).
        """
        lista = list(textos)
        bloque = sin_formato("\n".join(lista)).lower()  # «&4Arachnarch» también cuenta
        elegidos: dict[str, str] = {}
        for bajo, original, patron in self._ordenados():
            if bajo in bloque and patron.search(bloque):
                if self.ambiguo(original) and not any(uso_como_nombre(original, t) for t in lista):
                    continue
                elegidos[original] = self._fijos.get(original) or self._terminos[original]
                if len(elegidos) >= maximo:
                    break
        return elegidos

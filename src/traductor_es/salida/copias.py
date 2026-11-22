"""Copias de seguridad de lo que se traduce dentro de la instancia (misiones, scripts) y su restauración.

- Los originales se guardan en `<instancia>/traductor_es/respaldo/` con la misma ruta relativa.
- Se registra la huella (SHA-1) de cada archivo escrito. Si al volver el archivo ya no coincide (p. ej. se
  actualizó el modpack), se toma como nuevo original y se renueva la copia. La copia vieja nunca se pisa: se aparta
  en `traductor_es/anteriores/<fecha>/`.
- Una copia del registro, `registro.copia.json`, se actualiza tras cada escritura terminada: si `registro.json`
  se daña o se borra, se usa esa.
- Restaurar devuelve cada original a su sitio, pero solo si el archivo sigue como lo dejó la app; lo que cambió
  después (una actualización del modpack, una edición a mano) se deja y se avisa. Los archivos que la app creó y
  que no existían se dejan con contenido neutro (no se borra nada).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

CARPETA = "traductor_es"
#: Copias que se renovaron (el modpack cambió): se apartan aquí en vez de pisarlas.
ANTERIORES = "anteriores"
#: Copia del registro que se actualiza tras cada escritura terminada (por si se daña o se borra el registro).
REGISTRO_COPIA = "registro.copia.json"


def _huella(datos: bytes) -> str:
    return hashlib.sha1(datos).hexdigest()


def _clave_segura(clave: object) -> bool:
    """Una ruta relativa que no sale de la instancia: sin «..», sin unidad, sin barra inicial ni barras invertidas.

    El registro vive dentro de la instancia y un modpack puede traer uno fabricado: lo que no cumpla esto se ignora.
    """
    if not isinstance(clave, str) or not clave or "\\" in clave or ":" in clave or clave.startswith("/"):
        return False
    return all(parte not in ("", ".", "..") for parte in clave.split("/"))


def _leer_registro(ruta: Path) -> dict[str, dict[str, Any]] | None:
    """Las entradas válidas de un registro, o None si no existe o no se puede leer."""
    try:
        datos: Any = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(datos, dict):
        return None
    entradas = cast(dict[object, object], datos)
    return {
        cast(str, k): cast(dict[str, Any], v) for k, v in entradas.items() if _clave_segura(k) and isinstance(v, dict)
    }


def _escribir_entero(ruta: Path, datos: bytes) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".traductor.tmp")
    temporal.write_bytes(datos)
    try:
        temporal.replace(ruta)
    except OSError:  # p. ej. el archivo está abierto en otro programa: el temporal no se queda
        temporal.unlink(missing_ok=True)
        raise


class Respaldo:
    def __init__(self, juego: Path) -> None:
        self.juego = juego
        self.base = juego / CARPETA / "respaldo"
        self.registro = juego / CARPETA / "registro.json"
        self.copia_registro = juego / CARPETA / REGISTRO_COPIA
        #: Lo que el último `restaurar` dejó como estaba porque cambió después de traducir.
        self.cambiados: list[str] = []
        self._datos: dict[str, dict[str, Any]] = self._cargar()

    def _cargar(self) -> dict[str, dict[str, Any]]:
        for ruta in (self.registro, self.copia_registro):
            datos = _leer_registro(ruta)
            if datos is not None:
                return datos
        return {}

    def _dentro(self, ruta: Path) -> bool:
        """La ruta (siguiendo enlaces y uniones) sigue dentro de la instancia."""
        return ruta.resolve().is_relative_to(self.juego.resolve())

    def _exigir_dentro(self, ruta: Path) -> None:
        if not self._dentro(ruta):
            raise OSError(
                f"{ruta} apunta fuera de la instancia (¿un enlace o una unión en {CARPETA}?): no escribo ahí. "
                f"Mueve o borra la carpeta {self.juego / CARPETA} y vuelve a intentarlo."
            )

    def _guardar(self, con_copia: bool = True) -> None:
        """Guarda el registro y, si se pide, también su copia (no en la anotación previa a cada escritura)."""
        texto = json.dumps(self._datos, indent=1, ensure_ascii=False, sort_keys=True).encode("utf-8")
        for destino in [self.registro, self.copia_registro] if con_copia else [self.registro]:
            self._exigir_dentro(destino)
            _escribir_entero(destino, texto)

    def _clave(self, ruta: Path) -> str:
        return ruta.resolve().relative_to(self.juego.resolve()).as_posix()

    def _nuestro(self, clave: str, entrada: dict[str, Any] | None, actual: bytes | None) -> bool:
        """El archivo sigue como lo dejó la app y, si existía antes, su copia sigue ahí.

        También cuenta un archivo que creó la app y que quedó con su contenido neutro al restaurar: ese contenido
        no es un original del modpack (si lo fuera, un libro restaurado no se volvería a traducir).
        """
        if entrada is None or actual is None:
            return False
        huella = _huella(actual)
        # «pendiente»: la app iba a escribir eso y el proceso se cortó antes de terminar de anotarlo
        if huella in (entrada.get("escrito"), entrada.get("pendiente")):
            return not entrada.get("existia") or (self.base / clave).is_file()
        neutro = entrada.get("neutro")
        return (
            entrada.get("escrito") is None
            and not entrada.get("existia")
            and isinstance(neutro, str)
            and actual == neutro.encode("utf-8")
        )

    def original(self, ruta: Path) -> bytes | None:
        """Contenido original (en inglés) del archivo. Solo lee: la copia se guarda al escribir.

        None si el archivo no existe o si lo creó la app.
        """
        clave = self._clave(ruta)
        actual = ruta.read_bytes() if ruta.is_file() else None
        entrada = self._datos.get(clave)
        if entrada is not None and self._nuestro(clave, entrada, actual):
            # El archivo sigue como lo dejó la app: el original es la copia (o no existía).
            return (self.base / clave).read_bytes() if entrada.get("existia") else None
        # Primera vez, el archivo cambió por fuera (p. ej. se actualizó el modpack) o se borró su copia:
        # lo de ahora es el original
        return actual

    def _apartar(self, clave: str) -> None:
        """Mueve la copia que había a `anteriores/<fecha>/`: un original nunca se pierde por renovar la copia."""
        copia = self.base / clave
        if not copia.is_file():
            return
        sello = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        carpeta = self.juego / CARPETA / ANTERIORES / sello
        destino, n = carpeta / clave, 1
        while destino.exists():
            n += 1
            destino = carpeta.with_name(f"{sello}-{n}") / clave
        self._exigir_dentro(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        copia.replace(destino)

    def escribir(self, ruta: Path, datos: bytes, neutro: bytes = b"") -> None:
        """Escribe un archivo traducido y lo registra. `neutro` es lo que queda si se restaura y no existía."""
        clave = self._clave(ruta)
        entrada: dict[str, Any] | None = self._datos.get(clave)
        actual = ruta.read_bytes() if ruta.is_file() else None
        if not self._nuestro(clave, entrada, actual):
            # El archivo no está como lo dejó la app: lo que hay ahora es el original.
            if actual is None:
                entrada = {"existia": False}
            else:
                copia = self.base / clave
                self._exigir_dentro(copia)
                if not (copia.is_file() and copia.read_bytes() == actual):
                    self._apartar(clave)
                    _escribir_entero(copia, actual)
                entrada = {"existia": True}
            self._datos[clave] = entrada
        assert entrada is not None
        # Primero se anota lo que se va a escribir y después se escribe: si el proceso se corta o el registro no se
        # puede guardar en medio, el archivo nuevo se sigue reconociendo como de la app y la copia no se pisa.
        entrada["pendiente"] = _huella(datos)
        entrada["neutro"] = neutro.decode("utf-8", errors="replace") if not entrada.get("existia") else None
        entrada["fecha"] = datetime.now(UTC).isoformat(timespec="seconds")
        self._guardar(con_copia=False)
        _escribir_entero(ruta, datos)
        entrada["escrito"] = entrada.pop("pendiente")
        self._guardar()

    def restaurar(self, prefijo: str = "") -> list[Path]:
        """Devuelve a su estado original los archivos registrados cuya ruta empieza por `prefijo`.

        Solo los que siguen como los dejó la app: si un archivo cambió después de traducir (se actualizó el modpack,
        se editó a mano, se borró), se deja como está y queda en `cambiados` para avisar.

        Si falta la copia de algún archivo (p. ej. se borró `traductor_es/respaldo`), restaura los demás, guarda lo
        hecho y después lanza OSError con los que no pudo devolver (siguen registrados, por si vuelve la copia).
        """
        hechos: list[Path] = []
        sin_copia: list[str] = []
        self.cambiados = []
        for clave, entrada in sorted(self._datos.items()):
            if not clave.startswith(prefijo) or (entrada.get("escrito") is None and entrada.get("pendiente") is None):
                continue
            ruta = self.juego / clave
            copia = self.base / clave
            if not (self._dentro(ruta) and self._dentro(copia)):
                continue  # un enlace o una unión dentro de la instancia que apunta afuera: no se sigue
            sobrante = ruta.with_name(ruta.name + ".traductor.tmp")
            if sobrante.is_file():  # lo dejó una escritura cortada: es de la app y no sirve para nada
                sobrante.unlink()
            actual = ruta.read_bytes() if ruta.is_file() else None
            cambiado = actual is not None and _huella(actual) not in (entrada.get("escrito"), entrada.get("pendiente"))
            if cambiado or (actual is None and entrada.get("escrito") is None):
                # No es lo que escribió la app. Con «escrito», cambió después de traducir: no se pisa y se avisa.
                # Con solo «pendiente», fue una escritura cortada que no llegó a hacerse: no hay nada que devolver.
                if cambiado and entrada.get("escrito") is not None:
                    self.cambiados.append(clave)
                entrada["escrito"] = None
                entrada.pop("pendiente", None)
                continue
            if entrada.get("existia"):  # también si el usuario lo borró: recrearlo no pisa nada
                if not copia.is_file():
                    sin_copia.append(clave)
                    continue
                _escribir_entero(ruta, copia.read_bytes())
            elif actual is not None:
                _escribir_entero(ruta, str(entrada.get("neutro") or "").encode("utf-8"))
            entrada["escrito"] = None
            entrada.pop("pendiente", None)
            hechos.append(ruta)
        self._guardar()
        if sin_copia:
            lista = ", ".join(sin_copia[:5]) + (f" y {len(sin_copia) - 5} más" if len(sin_copia) > 5 else "")
            raise OSError(
                f"Restauré {len(hechos)} archivos, pero falta la copia de seguridad de {len(sin_copia)}: {lista}. "
                f"Estaba en {self.base}; para esos, vuelve a instalar los archivos originales del modpack."
            )
        return hechos

    def aviso_cambiados(self) -> str | None:
        """Mensaje para el usuario si el último `restaurar` dejó archivos sin tocar porque cambiaron."""
        if not self.cambiados:
            return None
        lista = ", ".join(self.cambiados[:5]) + (f" y {len(self.cambiados) - 5} más" if len(self.cambiados) > 5 else "")
        return (
            f"No restauré {len(self.cambiados)} archivos porque cambiaron después de traducirlos (una actualización "
            f"del modpack o una edición a mano): {lista}. Quedan como están ahora; las copias viejas siguen en "
            f"{self.base}."
        )

    def registrados(self, prefijo: str = "") -> list[str]:
        return sorted(
            k for k, e in self._datos.items() if k.startswith(prefijo) and (e.get("escrito") or e.get("pendiente"))
        )

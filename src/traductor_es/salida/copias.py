"""Copias de seguridad de lo que se traduce dentro de la instancia (misiones, scripts) y su restauración.

- Los originales se guardan en `<instancia>/traductor_es/respaldo/` con la misma ruta relativa.
- Se registra la huella (SHA-1) de cada archivo escrito. Si al volver el archivo ya no coincide (p. ej. se
  actualizó el modpack), se toma como nuevo original y se renueva la copia.
- Restaurar devuelve cada original a su sitio. Los archivos que la app creó y que no existían se dejan con
  contenido neutro (no se borra nada).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

CARPETA = "traductor_es"


def _huella(datos: bytes) -> str:
    return hashlib.sha1(datos).hexdigest()


def _clave_segura(clave: object) -> bool:
    """Una ruta relativa que no sale de la instancia: sin «..», sin unidad, sin barra inicial ni barras invertidas.

    El registro vive dentro de la instancia y un modpack puede traer uno fabricado: lo que no cumpla esto se ignora.
    """
    if not isinstance(clave, str) or not clave or "\\" in clave or ":" in clave or clave.startswith("/"):
        return False
    return all(parte not in ("", ".", "..") for parte in clave.split("/"))


class Respaldo:
    def __init__(self, juego: Path) -> None:
        self.juego = juego
        self.base = juego / CARPETA / "respaldo"
        self.registro = juego / CARPETA / "registro.json"
        self._datos: dict[str, dict[str, Any]] = self._cargar()

    def _cargar(self) -> dict[str, dict[str, Any]]:
        try:
            datos: Any = json.loads(self.registro.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(datos, dict):
            return {}
        entradas = cast(dict[object, object], datos)
        return {
            cast(str, k): cast(dict[str, Any], v)
            for k, v in entradas.items()
            if _clave_segura(k) and isinstance(v, dict)
        }

    def _dentro(self, ruta: Path) -> bool:
        """La ruta (siguiendo enlaces y uniones) sigue dentro de la instancia."""
        return ruta.resolve().is_relative_to(self.juego.resolve())

    def _guardar(self) -> None:
        self.registro.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.registro.with_name("registro.json.tmp")
        temporal.write_text(json.dumps(self._datos, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temporal.replace(self.registro)

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
                if not (copia.is_file() and copia.read_bytes() == actual):
                    copia.parent.mkdir(parents=True, exist_ok=True)
                    copia.write_bytes(actual)
                entrada = {"existia": True}
            self._datos[clave] = entrada
        assert entrada is not None
        # Primero se anota lo que se va a escribir y después se escribe: si el proceso se corta o el registro no se
        # puede guardar en medio, el archivo nuevo se sigue reconociendo como de la app y la copia no se pisa.
        entrada["pendiente"] = _huella(datos)
        entrada["neutro"] = neutro.decode("utf-8", errors="replace") if not entrada.get("existia") else None
        entrada["fecha"] = datetime.now(UTC).isoformat(timespec="seconds")
        self._guardar()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(ruta.name + ".traductor.tmp")
        temporal.write_bytes(datos)
        temporal.replace(ruta)
        entrada["escrito"] = entrada.pop("pendiente")
        self._guardar()

    def restaurar(self, prefijo: str = "") -> list[Path]:
        """Devuelve a su estado original los archivos registrados cuya ruta empieza por `prefijo`.

        Si falta la copia de algún archivo (p. ej. se borró `traductor_es/respaldo`), restaura los demás, guarda lo
        hecho y después lanza OSError con los que no pudo devolver (siguen registrados, por si vuelve la copia).
        """
        hechos: list[Path] = []
        sin_copia: list[str] = []
        for clave, entrada in sorted(self._datos.items()):
            if not clave.startswith(prefijo) or (entrada.get("escrito") is None and entrada.get("pendiente") is None):
                continue
            ruta = self.juego / clave
            copia = self.base / clave
            if not (self._dentro(ruta) and self._dentro(copia)):
                continue  # un enlace o una unión dentro de la instancia que apunta afuera: no se sigue
            if entrada.get("existia"):
                if not copia.is_file():
                    sin_copia.append(clave)
                    continue
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(copia.read_bytes())
            elif ruta.is_file():
                ruta.write_bytes(str(entrada.get("neutro") or "").encode("utf-8"))
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

    def registrados(self, prefijo: str = "") -> list[str]:
        return sorted(
            k for k, e in self._datos.items() if k.startswith(prefijo) and (e.get("escrito") or e.get("pendiente"))
        )

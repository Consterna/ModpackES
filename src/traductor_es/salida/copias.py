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
        return cast(dict[str, dict[str, Any]], datos) if isinstance(datos, dict) else {}

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
        if entrada.get("escrito") == _huella(actual):
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
        entrada["escrito"] = _huella(datos)
        entrada["neutro"] = neutro.decode("utf-8", errors="replace") if not entrada.get("existia") else None
        entrada["fecha"] = datetime.now(UTC).isoformat(timespec="seconds")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(ruta.name + ".traductor.tmp")
        temporal.write_bytes(datos)
        temporal.replace(ruta)
        self._guardar()

    def restaurar(self, prefijo: str = "") -> list[Path]:
        """Devuelve a su estado original los archivos registrados cuya ruta empieza por `prefijo`.

        Si falta la copia de algún archivo (p. ej. se borró `traductor_es/respaldo`), restaura los demás, guarda lo
        hecho y después lanza OSError con los que no pudo devolver (siguen registrados, por si vuelve la copia).
        """
        hechos: list[Path] = []
        sin_copia: list[str] = []
        for clave, entrada in sorted(self._datos.items()):
            if not clave.startswith(prefijo) or entrada.get("escrito") is None:
                continue
            ruta = self.juego / clave
            if entrada.get("existia"):
                copia = self.base / clave
                if not copia.is_file():
                    sin_copia.append(clave)
                    continue
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(copia.read_bytes())
            elif ruta.is_file():
                ruta.write_bytes(str(entrada.get("neutro") or "").encode("utf-8"))
            entrada["escrito"] = None
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
        return sorted(k for k, e in self._datos.items() if k.startswith(prefijo) and e.get("escrito"))

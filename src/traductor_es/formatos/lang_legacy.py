"""Archivos de idioma antiguos (Minecraft 1.12 y anteriores): `clave=valor` por línea."""

from __future__ import annotations

import re

BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"
# Como BufferedReader.readLine de Java: solo CR, LF y CRLF cortan línea (no U+2028 ni otros separadores).
_FIN_DE_LINEA = re.compile(r"\r\n|\r|\n")


def leer(datos: bytes | str) -> dict[str, str]:
    texto = datos.decode("utf-8-sig", errors="replace") if isinstance(datos, bytes) else datos.lstrip(BOM)
    textos: dict[str, str] = {}
    for linea in _FIN_DE_LINEA.split(texto):
        if not linea or linea.startswith("#") or "=" not in linea:  # igual que LanguageMap de 1.12
            continue
        clave, valor = linea.split("=", 1)
        textos[clave] = valor
    return textos


def escribir(textos: dict[str, str]) -> bytes:
    lineas: list[str] = []
    for clave, valor in textos.items():
        if _FIN_DE_LINEA.search(clave) or "=" in clave or _FIN_DE_LINEA.search(valor):
            raise ValueError(f"Texto con salto de línea real no se puede guardar en .lang: {clave!r}")
        lineas.append(f"{clave}={valor}")
    return ("\n".join(lineas) + "\n").encode("utf-8")

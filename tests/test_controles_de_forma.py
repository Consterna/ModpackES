"""Controles deterministas de forma: mayúsculas del glosario, nombres que no se traducen y palabras repetidas.

Los casos salen de la revisión humana de 100 traducciones (los «Leve»): «Caballeros de la Muerte» y «Anillo Cuántico»
con mayúsculas, «Arachnarch» sin traducir y «Mejora de Salud» sin repetir la palabra.
"""

from __future__ import annotations

import json

from traductor_es.motores.base import Lote
from traductor_es.motores.simulador import Simulador
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.terminos import nombres_propios
from traductor_es.nucleo.traductor import MOTIVO_REPETIDA, MOTIVO_TERMINOLOGIA, Traductor
from traductor_es.nucleo.vocabulario import agregar_vocabulario, preparar_sustituciones
from traductor_es.proceso import aviso_de_dudosos
from traductor_es.validacion.calidad import (
    ajustar_mayusculas,
    es_nombre_propio_en,
    palabra_repetida,
    reemplazar_en_ingles,
    revisar_glosario,
    terminos_faltantes,
)

# ------------------------------------------------------------------ mayúsculas


def test_respeta_las_mayusculas_de_un_nombre_propio_del_glosario() -> None:
    glosario = {"Death Knights": "Caballeros de la Muerte", "Quantum Ring": "Anillo Cuántico"}
    original = "Defeat the Death Knights and craft a Quantum Ring."
    traduccion = "Derrota a los caballeros de la muerte y fabrica un anillo cuántico."
    assert ajustar_mayusculas(original, traduccion, glosario) == (
        "Derrota a los Caballeros de la Muerte y fabrica un Anillo Cuántico."
    )


def test_una_palabra_del_pack_con_mayuscula_en_el_original() -> None:
    assert ajustar_mayusculas("Grow some Fluix crystals", "Cultiva cristales de fluix", {"Fluix": "Fluix"}) == (
        "Cultiva cristales de Fluix"
    )


def test_no_toca_lo_que_el_original_escribe_en_minuscula() -> None:
    glosario = {"Quantum Ring": "Anillo Cuántico"}
    assert ajustar_mayusculas("a quantum ring", "un anillo cuántico", glosario) == "un anillo cuántico"


def test_no_toca_terminos_en_el_estilo_del_juego() -> None:
    # «Lingote de hierro» lleva solo la primera en mayúscula: en medio de la frase va en minúscula
    glosario = {"Iron Ingot": "Lingote de hierro"}
    assert ajustar_mayusculas("Use an Iron Ingot", "Usa un lingote de hierro", glosario) == "Usa un lingote de hierro"


def test_no_toca_lo_que_esta_todo_en_mayusculas() -> None:
    glosario = {"Quantum Ring": "Anillo Cuántico"}
    assert ajustar_mayusculas("Get the Quantum Ring", "CONSIGUE EL ANILLO CUÁNTICO", glosario) == (
        "CONSIGUE EL ANILLO CUÁNTICO"
    )


def test_nombre_propio_al_empezar_la_frase() -> None:
    assert es_nombre_propio_en("Quantum Ring", "Quantum Ring is very strong")  # dos palabras en mayúscula
    assert not es_nombre_propio_en("Ring", "Ring the bell loudly")  # una sola palabra al empezar: no se sabe
    assert es_nombre_propio_en("Ring", "Wear the Ring every night")
    assert not es_nombre_propio_en("Ring", "wear the ring every night")


def test_en_un_nombre_con_todo_en_mayuscula_no_hay_nombre_propio() -> None:
    # Los nombres de objetos en inglés ponen mayúscula a cada palabra: no dice nada de «Upgrade»
    assert not es_nombre_propio_en("Upgrade", "Speed Upgrade Module (Tier VIII)")
    glosario = {"Upgrade": "Mejora"}
    original = "Speed Upgrade Module (Tier VIII)"
    assert ajustar_mayusculas(original, "Módulo de mejora de velocidad (nivel VIII)", glosario) == (
        "Módulo de mejora de velocidad (nivel VIII)"
    )


# ------------------------------------------------------------------ nombres que no se traducen


def test_el_juego_protege_sus_nombres_que_no_se_traducen() -> None:
    glosario = Glosario()
    glosario.agregar_pares(
        {"a": "Creeper", "b": "Cobblestone", "c": "the end of it"},
        {"a": "Creeper", "b": "Piedra labrada", "c": "the end of it"},
        fuente="minecraft",
        oficial=True,
        proteger_iguales=True,
    )
    assert glosario.todos() == {"Creeper": "Creeper", "Cobblestone": "Piedra labrada"}
    assert glosario.del_juego("Creeper")


def test_lo_igual_en_el_espanol_de_un_mod_no_se_protege() -> None:
    # En el es_es de un mod, un texto igual al inglés suele ser una traducción a medias
    glosario = Glosario()
    glosario.agregar_pares({"a": "Iron Gear"}, {"a": "Iron Gear"}, fuente="unmod")
    assert glosario.todos() == {}


def test_un_nombre_propio_que_desaparece_se_detecta() -> None:
    glosario = {"Arachnarch": "Arachnarch"}
    original = "Defeat the Arachnarch in its lair."
    assert terminos_faltantes(original, "Derrota al Aracnarca en su guarida.", glosario) == glosario
    assert terminos_faltantes(original, "Derrota al Arachnarch en su guarida.", glosario) == {}


# ------------------------------------------------------------------ repeticiones


def test_detecta_la_palabra_repetida() -> None:
    assert palabra_repetida("Health Boost Augment", "Mejora de Salud mejorada") == "mejora"
    assert palabra_repetida("Health Boost Augment", "Mejora de Salud") is None


def test_si_el_original_repite_no_se_marca() -> None:
    assert palabra_repetida("Stone of stones", "Piedra de piedras") is None


def test_en_una_frase_larga_repetir_es_normal() -> None:
    texto = "Coloca la piedra junto a otra piedra para formar un muro"
    assert palabra_repetida("Place the stone next to another one to build a wall", texto) is None


# ------------------------------------------------------------------ reparación


def test_reemplaza_el_termino_que_quedo_en_ingles() -> None:
    final, siguen = reemplazar_en_ingles(
        "Pon el Iron Ingot en la caja", {"Iron Ingot": "Lingote de hierro", "Chest": "Cofre"}
    )
    assert final == "Pon el Lingote de hierro en la caja"
    assert siguen == {"Chest": "Cofre"}


def test_revisar_glosario_tolera_plurales_y_tildes() -> None:
    glosario = {"Iron Ingot": "Lingote de hierro"}
    traducciones = {"Two Iron Ingot": "Dos lingotes de hierro", "An Iron Ingot": "Una barra de hierro"}
    assert revisar_glosario(traducciones, glosario, glosario).inconsistentes == {"Iron Ingot": 1}


class _Guion:
    """Devuelve en cada pedido la siguiente respuesta de la lista y guarda las pistas que recibió."""

    nombre = "guion"

    def __init__(self, *respuestas: str) -> None:
        self.respuestas = list(respuestas)
        self.pistas: list[str] = []

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        self.pistas.extend(e.pista for e in lote.entradas)
        respuesta = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        return {e.id: respuesta for e in lote.entradas}


def _traducir(motor: _Guion, glosario: Glosario, texto: str) -> tuple[dict[str, str], dict[str, str]]:
    with Memoria(":memory:") as mem:
        r = Traductor(motor, mem, glosario).traducir([texto], "ui")
    return r.traducciones, r.dudosos


def test_el_reintento_pide_corregir_solo_lo_que_fallo() -> None:
    glosario = Glosario()
    glosario.fijar({"Health Boost": "Mejora de Salud"})
    motor = _Guion("Mejora de Salud mejorada", "Mejora de Salud")
    traducciones, dudosos = _traducir(motor, glosario, "Health Boost Augment")
    assert traducciones == {"Health Boost Augment": "Mejora de Salud"} and not dudosos
    assert "Tu primera traducción fue «Mejora de Salud mejorada»" in motor.pistas[-1]
    assert "no repitas «mejora»" in motor.pistas[-1]


def test_si_el_termino_sigue_en_ingles_se_cambia_sin_preguntar() -> None:
    glosario = Glosario()
    glosario.fijar({"Quantum Ring": "Anillo Cuántico"})
    motor = _Guion("Fabrica el Quantum Ring ahora")
    traducciones, dudosos = _traducir(motor, glosario, "Craft the Quantum Ring now")
    assert traducciones == {"Craft the Quantum Ring now": "Fabrica el Anillo Cuántico ahora"}
    assert not dudosos


def test_lo_que_no_se_puede_arreglar_se_acepta_marcado() -> None:
    glosario = Glosario()
    glosario.fijar({"Quantum Ring": "Anillo Cuántico"})
    motor = _Guion("Fabrica el aro mágico ahora")
    traducciones, dudosos = _traducir(motor, glosario, "Craft the Quantum Ring now")
    assert traducciones == {"Craft the Quantum Ring now": "Fabrica el aro mágico ahora"}
    assert dudosos["Craft the Quantum Ring now"].startswith(MOTIVO_TERMINOLOGIA)


def test_sin_controles_se_comporta_como_antes() -> None:
    glosario = Glosario()
    glosario.fijar({"Quantum Ring": "Anillo Cuántico"})
    with Memoria(":memory:") as mem:
        motor = _Guion("Fabrica el anillo cuántico y el anillo cuántico")
        r = Traductor(motor, mem, glosario, controles_de_forma=False).traducir(["Craft the Quantum Ring now"], "ui")
    assert r.traducciones == {"Craft the Quantum Ring now": "Fabrica el anillo cuántico y el anillo cuántico"}
    assert not r.dudosos


def test_del_juego_no_cambia_mayusculas() -> None:
    glosario = Glosario()
    glosario.agregar_pares({"a": "Chest"}, {"a": "Cofre"}, fuente="minecraft", oficial=True)
    motor = _Guion("Abre el cofre")
    traducciones, _ = _traducir(motor, glosario, "Open the Chest")
    assert traducciones == {"Open the Chest": "Abre el cofre"}


def test_la_repeticion_que_persiste_se_acepta_marcada() -> None:
    motor = _Guion("Mejora de Salud mejorada")
    traducciones, dudosos = _traducir(motor, Glosario(), "Health Boost Augment")
    assert traducciones == {"Health Boost Augment": "Mejora de Salud mejorada"}
    assert dudosos == {"Health Boost Augment": MOTIVO_REPETIDA + "mejora"}


# ------------------------------------------------------------------ vocabulario base y solapamientos


def test_un_termino_corto_dentro_de_uno_largo_no_se_exige_aparte() -> None:
    glosario = {"Item Frame": "Marco", "Item": "Objeto"}
    assert terminos_faltantes("Place an Item Frame on the wall", "Pon un marco en la pared", glosario) == {}
    # Fuera del término largo, el corto sí se exige
    faltan = terminos_faltantes("Put the item in an Item Frame", "Pon el ítem en un marco", glosario)
    assert faltan == {"Item": "Objeto"}


def test_lo_que_traduce_el_juego_manda_sobre_el_vocabulario() -> None:
    # es_mx dice «Ítem»: se respeta. El vocabulario solo completa lo que el juego no trae suelto
    glosario = Glosario()
    preparar_sustituciones(glosario)
    glosario.agregar_pares(
        {"k": "Item", "n": "Netherite"}, {"k": "Ítem", "n": "Netherite"}, fuente="minecraft", oficial=True
    )
    agregar_vocabulario(glosario)
    assert glosario.todos()["Item"] == "Ítem"
    glosario.fijar({"Netherite": "Netherite"})  # el usuario manda sobre todo
    assert glosario.todos()["Netherite"] == "Netherite"


def test_sin_el_juego_el_vocabulario_completa() -> None:
    glosario = Glosario()
    agregar_vocabulario(glosario)
    assert glosario.todos() == {"Netherite": "Netherita"}


def test_el_aviso_de_dudosos_muestra_ejemplos() -> None:
    aviso = aviso_de_dudosos({"Health Boost Augment": ("Mejora de Salud mejorada", MOTIVO_REPETIDA + "mejora")})
    assert aviso.startswith("1 textos se aceptaron con dudas")
    assert "«Health Boost Augment» → «Mejora de Salud mejorada» (palabra repetida)" in aviso


def test_las_sustituciones_no_tocan_lo_del_juego_ni_lo_del_usuario() -> None:
    glosario = Glosario()
    preparar_sustituciones(glosario)
    glosario.agregar_pares({"k": "Item Pipe"}, {"k": "Tubería de ítems"}, fuente="unmod")
    glosario.agregar_pares({"j": "Netherite Sword"}, {"j": "Espada de inframundita"}, fuente="otromod")
    glosario.fijar({"Hell Ore": "Mena de inframundita"})
    todos = glosario.todos()
    assert todos["Item Pipe"] == "Tubería de ítems"  # «ítem» es del juego (es_mx): se deja
    assert todos["Netherite Sword"] == "Espada de netherita"  # «inframundita» no es del juego
    assert todos["Hell Ore"] == "Mena de inframundita"  # lo del usuario no se toca


def test_una_palabra_que_no_es_del_juego_se_corrige_en_la_traduccion() -> None:
    glosario = Glosario()
    preparar_sustituciones(glosario)
    motor = _Guion("Un peto de inframundita encantado")
    traducciones, _ = _traducir(motor, glosario, "An enchanted Netherite Chestplate")
    assert traducciones == {"An enchanted Netherite Chestplate": "Un peto de netherita encantado"}


def test_no_mezcla_idiomas_si_el_resto_quedo_en_ingles() -> None:
    faltan = {"Gear": "Engranaje"}
    final, siguen = reemplazar_en_ingles("Iron Gear", faltan, "Iron Gear")
    assert final == "Iron Gear" and siguen == faltan  # «Iron Engranaje» sería peor
    final, siguen = reemplazar_en_ingles("Un Gear de hierro", faltan, "An Iron Gear")
    assert final == "Un Engranaje de hierro" and not siguen


# ------------------------------------------------------------------ nombres propios que se repiten en frases


def test_encuentra_los_nombres_propios_que_se_repiten() -> None:
    textos = [
        "The Arachnarch lunges at targets from the ceiling.",
        "Use the keys to open the gate to the &4Arachnarch&r dungeon.",
        "Bronze Dungeons have entrances on the sides of islands.",
        "Mimics are hostile mobs in &eBronze Dungeons&r.",
        "Craft a table first.",  # «Craft» al empezar la frase no es un nombre
        "Find the Keys here. Then use the Keys again.",  # mismo texto dos veces: cuenta una
    ]
    assert nombres_propios(textos) == ["Arachnarch", "Bronze Dungeons"]


def test_los_nombres_se_deciden_una_vez_y_se_fijan() -> None:
    class Decide(Simulador):
        """Deja igual el nombre suelto; en las frases lo traduce salvo que el glosario se lo exija."""

        def traducir_lote(self, lote: Lote) -> dict[str, str]:
            self.lotes_recibidos.append(lote)
            salida: dict[str, str] = {}
            for e in lote.entradas:
                if e.texto == "Arachnarch":
                    salida[e.id] = "Arachnarch"
                elif "Arachnarch" in json.dumps(lote.glosario):
                    salida[e.id] = "La Arachnarch ataca"
                else:
                    salida[e.id] = "La Aracnarca ataca"
            return salida

    textos = ["The Arachnarch lunges at you from above.", "You must defeat the Arachnarch in its lair."]
    motor = Decide()
    with Memoria(":memory:") as mem:
        glosario = Glosario()
        r = Traductor(motor, mem, glosario).traducir(textos, "mision")
    assert [e.texto for e in motor.lotes_recibidos[0].entradas] == ["Arachnarch"]  # primero se decide el nombre
    assert glosario.todos()["Arachnarch"] == "Arachnarch"
    assert set(r.traducciones.values()) == {"La Arachnarch ataca"}  # todas las frases lo escriben igual


def test_un_nombre_que_no_se_traduce_se_exige_tambien_en_un_titulo() -> None:
    glosario = {"Arachnarch": "Arachnarch"}
    assert terminos_faltantes("Defeat the Arachnarch", "Derrota a la Aracnarca", glosario) == glosario
    assert terminos_faltantes("Defeat the Arachnarch", "Derrota a la Arachnarch", glosario) == {}


def test_los_codigos_de_color_pegados_no_esconden_un_termino() -> None:
    # «&4Arachnarch»: el «4» va pegado al nombre; antes el término ni se veía
    glosario = {"Arachnarch": "Arachnarch", "Bronze Dungeons": "Mazmorras de bronce"}
    original = "Defeat the &4Arachnarch&r in the &eBronze Dungeons&r"
    faltan = terminos_faltantes(original, "Derrota a la &4Aracnarca&r en los &ecalabozos de latón&r", glosario)
    assert faltan == glosario
    # Una variante cercana con el código pegado («&emazmorras del bronce») sí cuenta como el término
    bien = "Derrota a la &4Arachnarch&r en las &emazmorras del bronce&r"
    assert terminos_faltantes(original, bien, glosario) == {}
    g = Glosario()
    g.descubrir(glosario)
    assert g.relevantes([original]) == glosario

"""Glosario preciso: palabras con otro sentido en minúscula, traducciones a medias, género y textos sin traducir."""

from __future__ import annotations

from traductor_es.motores.base import Lote
from traductor_es.nucleo.glosario import Glosario
from traductor_es.nucleo.memoria import Memoria
from traductor_es.nucleo.traductor import MOTIVO_NOMBRE, Traductor
from traductor_es.validacion.calidad import genero, reemplazar_en_ingles, terminos_faltantes, uso_como_nombre

# Lo que dice el juego: «lead» y «string» en minúscula casi nunca son la correa o el hilo; «fire» sí es el fuego
_EN = {
    "a": "Show them the way and lead the group",
    "b": "Mobs follow the lead of their leader",
    "c": "Set fire to the block",
    "d": "The fire spreads fast",
    "e": "Craft a Redstone Torch",
    "f": "Powered by a redstone signal",
}
_ES = {
    "a": "Muéstrales el camino y guía al grupo",
    "b": "Las criaturas siguen el ejemplo de su líder",
    "c": "Prende fuego al bloque",
    "d": "El fuego se propaga rápido",
    "e": "Fabrica una antorcha de redstone",
    "f": "Funciona con una señal de redstone",
}


def _glosario() -> Glosario:
    g = Glosario()
    g.agregar_pares(
        {"lead": "Lead", "fire": "Fire"}, {"lead": "Correa", "fire": "Fuego"}, fuente="minecraft", oficial=True
    )
    g.aprender_usos(_EN, _ES)
    return g


def test_una_palabra_con_otro_sentido_en_minuscula_es_ambigua() -> None:
    g = _glosario()
    assert g.ambiguo("Lead")  # 0 de 2 textos dicen «Correa»
    assert not g.ambiguo("Fire")  # 2 de 2 dicen «fuego»: se sigue exigiendo
    g.fijar({"Lead": "Plomo"})
    assert not g.ambiguo("Lead")  # lo del usuario manda siempre


def test_solo_se_exige_cuando_el_original_la_usa_como_nombre() -> None:
    glosario = {"Lead": "Correa"}
    ambiguos = frozenset({"Lead"})
    assert not terminos_faltantes("Lead the way to the village", "Abre el camino", glosario, ambiguos)
    assert not terminos_faltantes("Follow the lead", "Sigue el ejemplo", glosario, ambiguos)
    assert terminos_faltantes("Tie the cow with a Lead", "Ata la vaca", glosario, ambiguos)
    assert terminos_faltantes("Lead", "Plomo", glosario, ambiguos)
    assert terminos_faltantes("Follow the lead", "Sigue el ejemplo", glosario)  # sin saber que es ambigua, se exige


def test_uso_como_nombre() -> None:
    assert uso_como_nombre("Lead", "Lead")
    assert uso_como_nombre("Lead", "Tie it with a Lead.")
    assert uso_como_nombre("Lead", "Lead Block")  # nombre en estilo título
    assert not uso_como_nombre("Lead", "Lead the way to the village")
    assert not uso_como_nombre("Lead", "follow the lead")


def test_el_motor_no_recibe_el_termino_si_tiene_otro_sentido() -> None:
    g = _glosario()
    assert "Lead" not in g.relevantes(["Lead the way to the village"])
    assert g.relevantes(["Tie the cow with a Lead"]) == {"Lead": "Correa"}
    assert g.relevantes(["The fire spreads"]) == {"Fire": "Fuego"}


def test_no_se_usan_las_traducciones_a_medias_de_un_mod() -> None:
    g = _glosario()
    g.agregar_pares(
        {"x": "Iron Gear", "y": "Redstone Engine"}, {"x": "Engranaje de Iron", "y": "Motor de redstone"}, fuente="mod"
    )
    g.aprender_usos({"z": "Smelt the iron ore"}, {"z": "Funde el mineral de hierro"})
    assert "Iron Gear" not in g.todos() and g.exacto("Iron Gear") is None  # «iron» no es español
    assert g.todos()["Redstone Engine"] == "Motor de redstone"  # el juego dice «redstone» en español


def test_el_nombre_de_un_mod_no_es_una_traduccion_a_medias() -> None:
    g = _glosario()
    g.aprender_usos({"z": "You can create a new world"}, {"z": "Puedes crear un mundo nuevo"})
    g.agregar_pares({"x": "Create Train"}, {"x": "Tren de Create"}, fuente="mod")
    assert "Create Train" not in g.todos()
    g.proteger_nombres(["create"])
    assert g.todos()["Create Train"] == "Tren de Create"


def test_el_articulo_sigue_al_genero_del_termino() -> None:
    assert reemplazar_en_ingles("Usa el Wrench para girarlo", {"Wrench": "Llave inglesa"}) == (
        "Usa la Llave inglesa para girarlo",
        {},
    )
    assert reemplazar_en_ingles("Saca la Gear del cofre", {"Gear": "Engranaje"})[0] == "Saca el Engranaje del cofre"
    assert reemplazar_en_ingles("Ponlo al Altar", {"Altar": "Altar"})[0] == "Ponlo al Altar"
    assert reemplazar_en_ingles("Ve a la Forge", {"Forge": "Forja"})[0] == "Ve a la Forja"
    assert reemplazar_en_ingles("Usa del Mana", {"Mana": "Maná"})[0] == "Usa del Maná"
    # Con artículo delante y sin saber el género, no se cambia: queda como duda
    assert reemplazar_en_ingles("Usa el Zorp", {"Zorp": "Zarpel"}) == ("Usa el Zorp", {"Zorp": "Zarpel"})
    assert reemplazar_en_ingles("Zorp listo", {"Zorp": "Zarpel"})[0] == "Zarpel listo"  # sin artículo, sí


def test_genero() -> None:
    assert genero("Llave inglesa") == "f"
    assert genero("Engranaje de hierro") == "m"
    assert genero("Mesa de trabajo") == "f"
    assert genero("Firma rúnica") is None  # «-ma» fuera de la lista: muchas excepciones
    assert genero("Sistema de tuberías") == "m"
    assert genero("Día") == "m"
    assert genero("Generación") == "f"
    assert genero("Xyzzy") is None


class _Terco:
    nombre = "terco"

    def traducir_lote(self, lote: Lote) -> dict[str, str]:
        return {e.id: e.texto for e in lote.entradas}


def test_una_frase_que_sigue_en_ingles_no_se_guarda_en_la_memoria() -> None:
    with Memoria(":memory:") as mem:
        r = Traductor(_Terco(), mem, Glosario()).traducir(["Place them in the slots"], "mision")
        assert not r.traducciones and "Place them in the slots" in r.rechazados
        assert mem.obtener("Place them in the slots", "es_mx", "mision") is None


def test_un_nombre_que_sigue_igual_se_acepta_para_revisarlo() -> None:
    with Memoria(":memory:") as mem:
        r = Traductor(_Terco(), mem, Glosario()).traducir(["Bronze Dungeons"], "mision")
    assert r.traducciones == {"Bronze Dungeons": "Bronze Dungeons"}
    assert r.dudosos == {"Bronze Dungeons": MOTIVO_NOMBRE}

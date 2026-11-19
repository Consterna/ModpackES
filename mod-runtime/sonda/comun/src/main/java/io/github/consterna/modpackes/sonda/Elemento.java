package io.github.consterna.modpackes.sonda;

import java.util.List;

/**
 * Algo registrado en el juego con nombre visible: un objeto, un bloque, una entidad, un efecto, un encantamiento, un
 * bioma o un atajo de teclado.
 *
 * @param categoria «objeto», «bloque», «entidad», «efecto», «encantamiento», «bioma», «atajo» o «categoria_de_atajo»
 * @param id        identificador en el registro ({@code minecraft:stone}); en los atajos, su clave
 * @param clave     clave de traducción, o {@code null} si el nombre no sale de una
 * @param valor     el texto que ve el jugador en el idioma actual
 * @param existe    si el idioma cargado tiene la clave
 * @param tooltip   líneas del tooltip sin modo avanzado (solo objetos; {@code null} en lo demás)
 */
public record Elemento(String categoria, String id, String clave, String valor, boolean existe, List<String> tooltip) {
}

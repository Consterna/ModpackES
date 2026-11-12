package io.github.consterna.modpackes;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.StringReader;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TablaTest {
    private static Tabla tabla(String... pares) {
        Map<String, String> mapa = new java.util.HashMap<>();
        for (int i = 0; i < pares.length; i += 2) {
            mapa.put(pares[i], pares[i + 1]);
        }
        return new Tabla(mapa);
    }

    @Test
    void coincidenciaExactaYSinCoincidencia() {
        Tabla t = tabla("TPA request expired!", "¡La solicitud de TPA expiró!");
        assertEquals("¡La solicitud de TPA expiró!", t.traducir("TPA request expired!"));
        assertNull(t.traducir("tpa request expired!")); // mayúsculas distintas: no es el mismo texto
        assertNull(t.traducir("TPA request expired! Now"));
        assertNull(t.traducir(""));
        assertNull(t.traducir(null));
    }

    @Test
    void conservaLosEspaciosDeLosBordes() {
        Tabla t = tabla("Hello there", "Hola");
        assertEquals("  Hola\n", t.traducir("  Hello there\n"));
        assertNull(t.traducir("   "));
    }

    @Test
    void unTextoIgualQueSuTraduccionNoCuentaComoCambio() {
        Tabla t = tabla("Creeper", "Creeper");
        assertNull(t.traducir("Creeper"));
    }

    @Test
    void conservaTildesEneYEmoji() {
        Tabla t = tabla("Pick 😀", "Elige ñandú ¡sí! 日本語 §a%s");
        assertEquals("Elige ñandú ¡sí! 日本語 §a%s", t.traducir("Pick 😀"));
    }

    @Test
    void leeJsonValidoEIgnoraLoQueNoEsTexto() throws IOException {
        Tabla t = Tabla.leer(new StringReader("{\"a b\": \"uno\", \"n\": 5, \"v\": \"\", \"l\": [\"x\"], \"z\": null}"));
        assertEquals(1, t.tamano());
        assertEquals("uno", t.traducir("a b"));
    }

    @Test
    void jsonRotoOQueNoEsObjetoFallaConIOException() {
        assertThrows(IOException.class, () -> Tabla.leer(new StringReader("{no es json")));
        assertThrows(IOException.class, () -> Tabla.leer(new StringReader("[1, 2]")));
        assertThrows(IOException.class, () -> Tabla.leer(new StringReader("\"texto\"")));
    }

    @Test
    void combinarDejaMandarALaSegunda() {
        Tabla total = tabla("a b", "viejo", "c d", "queda").combinar(tabla("a b", "nuevo"));
        assertEquals("nuevo", total.traducir("a b"));
        assertEquals("queda", total.traducir("c d"));
        assertTrue(Tabla.VACIA.vacia());
        assertFalse(total.vacia());
        assertEquals(total, total.combinar(Tabla.VACIA));
    }

    @Test
    void plantillaConUnDatoVariable() {
        Tabla t = tabla("Hello %s, welcome back!", "¡Hola %s, bienvenido de nuevo!");
        assertEquals("¡Hola Steve, bienvenido de nuevo!", t.traducir("Hello Steve, welcome back!"));
        assertEquals("¡Hola Ñandú 😀, bienvenido de nuevo!", t.traducir("Hello Ñandú 😀, welcome back!"));
        assertNull(t.traducir("Goodbye Steve, welcome back!"));
        assertNull(t.traducir("Hello Steve"));
    }

    @Test
    void plantillaConNumeroSoloCoincideConNumeros() {
        Tabla t = tabla("You have %d items left", "Te quedan %d objetos");
        assertEquals("Te quedan 5 objetos", t.traducir("You have 5 items left"));
        assertEquals("Te quedan -3 objetos", t.traducir("You have -3 items left"));
        assertNull(t.traducir("You have many items left"));
    }

    @Test
    void plantillaPuedeCambiarElOrden() {
        Tabla t = tabla("%s gave %d coins", "%2$d monedas de %1$s");
        assertEquals("7 monedas de Laly", t.traducir("Laly gave 7 coins"));
    }

    @Test
    void plantillaConIndicesExplicitosEnElIngles() {
        // String.format("%2$s of %1$s", "Tom", "Ana") muestra «Ana of Tom»: cada dato es su argumento, no su posición
        Tabla t = tabla("%2$s of %1$s left", "%2$s de %1$s se fue");
        assertEquals("Ana de Tom se fue", t.traducir("Ana of Tom left"));
        Tabla mixta = tabla("%2$s wins %s points", "%s puntos para %2$s");
        assertEquals("10 puntos para Ana", mixta.traducir("Ana wins 10 points"));
        assertNull(tabla("%1$s and %1$s again", "%1$s y %1$s otra vez").traducir("a and a again"));
    }

    @Test
    void plantillaConBordesYPorcentajeLiteral() {
        Tabla t = tabla("Progress: %d%% of %s", "Progreso: %d%% de %s");
        assertEquals("  Progreso: 50% de la misión ", t.traducir("  Progress: 50% of la misión "));
    }

    @Test
    void plantillasInseguras() {
        // sin texto fijo: coincidiría con todo
        assertNull(tabla("%s", "%s").traducir("cualquier cosa"));
        assertNull(tabla("%s %s", "%s %s").traducir("uno dos"));
        // la traducción pierde un dato o inventa uno
        assertNull(tabla("Hello %s and %s here", "Hola %s aquí").traducir("Hello A and B here"));
        assertNull(tabla("Hello %s there friend", "Hola %s y %s").traducir("Hello A there friend"));
        assertNull(tabla("Hello %s there friend", "Hola %3$s").traducir("Hello A there friend"));
    }

    @Test
    void laPlantillaMasEspecificaGana() {
        Tabla t = tabla(
                "Welcome %s", "Bienvenido %s",
                "Welcome %s to the farm", "Bienvenido %s a la granja");
        assertEquals("Bienvenido Steve a la granja", t.traducir("Welcome Steve to the farm"));
        assertEquals("Bienvenido Steve", t.traducir("Welcome Steve"));
    }

    @Test
    void caracteresDeRegexEnElTextoFijoNoSonEspeciales() {
        Tabla t = tabla("Cost (%d) [gold]. Really?", "Costo (%d) [oro]. ¿En serio?");
        assertEquals("Costo (9) [oro]. ¿En serio?", t.traducir("Cost (9) [gold]. Really?"));
        assertNull(t.traducir("Cost 9 gold. Really?"));
    }

    @Test
    void lasPlantillasSobrevivenAlCombinarYSeCuentan() {
        Tabla a = tabla("Hello %s, welcome back!", "¡Hola %s, bienvenido de nuevo!", "Exact text here", "Texto exacto");
        Tabla total = a.combinar(tabla("Another %d things here", "Otras %d cosas aquí"));
        assertEquals(3, total.tamano());
        assertEquals(2, total.plantillas());
        assertEquals("Otras 3 cosas aquí", total.traducir("Another 3 things here"));
        assertEquals("Texto exacto", total.traducir("Exact text here"));
    }
}

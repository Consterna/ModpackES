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
}

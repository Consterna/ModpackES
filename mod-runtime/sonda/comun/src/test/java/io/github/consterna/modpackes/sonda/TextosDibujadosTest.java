package io.github.consterna.modpackes.sonda;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TextosDibujadosTest {
    @Test
    void elMismoTextoEnLaMismaPantallaSeGuardaUnaVez() {
        TextosDibujados t = new TextosDibujados();
        assertTrue(t.anotar("Inventory", "InventoryScreen"));
        assertFalse(t.anotar("Inventory", "InventoryScreen"));
        assertFalse(t.anotar("Inventory", "InventoryScreen"));
        assertEquals(1, t.tamano());
    }

    @Test
    void elMismoTextoEnOtraPantallaSumaLaPantalla() {
        TextosDibujados t = new TextosDibujados();
        t.anotar("Done", "B");
        t.anotar("Done", "A");
        t.anotar("Done", null);
        assertEquals(3, t.tamano());
        List<TextosDibujados.Entrada> copia = t.copia();
        assertEquals(1, copia.size());
        assertEquals(List.of("(sin pantalla)", "A", "B"), copia.get(0).pantallas());
    }

    @Test
    void ignoraVaciosYEspacios() {
        TextosDibujados t = new TextosDibujados();
        assertFalse(t.anotar(null, "A"));
        assertFalse(t.anotar("", "A"));
        assertFalse(t.anotar("  \t", "A"));
        assertEquals(0, t.tamano());
        assertFalse(t.tomarCambio());
    }

    @Test
    void conservaElTextoTalCual() {
        TextosDibujados t = new TextosDibujados();
        t.anotar(" §aÉpico ñandú 日本語 ", "A");
        assertEquals(" §aÉpico ñandú 日本語 ", t.copia().get(0).texto());
    }

    @Test
    void laCopiaVaOrdenadaPorTexto() {
        TextosDibujados t = new TextosDibujados();
        t.anotar("b", "X");
        t.anotar("a", "X");
        t.anotar("c", "X");
        assertEquals(List.of("a", "b", "c"), t.copia().stream().map(TextosDibujados.Entrada::texto).toList());
    }

    @Test
    void elTopeCuentaLoQueNoCabe() {
        TextosDibujados t = new TextosDibujados(2);
        assertTrue(t.anotar("x 1", "A"));
        assertTrue(t.anotar("x 2", "A"));
        assertFalse(t.anotar("x 3", "A"));
        assertFalse(t.anotar("x 1", "B"));
        assertFalse(t.anotar("x 1", "A")); // ya estaba: no es un descarte
        assertEquals(2, t.tamano());
        assertEquals(2, t.descartados());
    }

    @Test
    void tomarCambioAvisaUnaVezPorTanda() {
        TextosDibujados t = new TextosDibujados();
        assertFalse(t.tomarCambio());
        t.anotar("a", "A");
        t.anotar("b", "A");
        assertTrue(t.tomarCambio());
        assertFalse(t.tomarCambio());
        t.anotar("a", "A"); // repetido: no cambia nada
        assertFalse(t.tomarCambio());
        t.anotar("a", "B");
        assertTrue(t.tomarCambio());
    }

    @Test
    void variosHilosNoDuplicanNiPierden() throws InterruptedException {
        TextosDibujados t = new TextosDibujados();
        ExecutorService hilos = Executors.newFixedThreadPool(8);
        for (int h = 0; h < 8; h++) {
            hilos.execute(() -> {
                for (int i = 0; i < 1000; i++) {
                    t.anotar("texto " + (i % 250), "P" + (i / 250)); // 250 textos en 4 pantallas
                }
            });
        }
        hilos.shutdown();
        assertTrue(hilos.awaitTermination(30, TimeUnit.SECONDS));
        assertEquals(250, t.copia().size());
        assertEquals(1000, t.tamano());
        assertTrue(t.copia().stream().allMatch(e -> e.pantallas().size() == 4));
    }
}

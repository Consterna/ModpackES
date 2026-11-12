package io.github.consterna.modpackes;

import net.minecraft.util.text.ITextComponent;
import net.minecraft.util.text.Style;
import net.minecraft.util.text.TextComponentString;
import net.minecraft.util.text.TextComponentTranslation;
import net.minecraft.util.text.TextFormatting;
import net.minecraft.util.text.event.ClickEvent;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

class ReescritorTest {
    private static Tabla tabla(String... pares) { // Map.of no existe en Java 8
        Map<String, String> mapa = new HashMap<>();
        for (int i = 0; i < pares.length; i += 2) {
            mapa.put(pares[i], pares[i + 1]);
        }
        return new Tabla(mapa);
    }

    private static final Tabla TABLA = tabla(
            "TPA request expired!", "¡La solicitud de TPA expiró!",
            "Hello", "Hola",
            "Click here", "Haz clic aquí",
            "Hello %s, welcome back!", "¡Hola %s, bienvenido de nuevo!");

    @Test
    void cambiaUnLiteralYConservaElEstilo() {
        ITextComponent original = new TextComponentString("TPA request expired!");
        original.getStyle().setColor(TextFormatting.RED).setBold(true);
        ITextComponent nuevo = Reescritor.reescribir(original, TABLA);
        assertEquals("¡La solicitud de TPA expiró!", nuevo.getUnformattedText());
        assertEquals(TextFormatting.RED, nuevo.getStyle().getColor());
        assertEquals(Boolean.TRUE, nuevo.getStyle().getBold());
    }

    @Test
    void sinCoincidenciaDevuelveNullYNoCopia() {
        assertNull(Reescritor.reescribir(new TextComponentString("Nothing to see here"), TABLA));
        assertNull(Reescritor.reescribir(new TextComponentString("Hello"), Tabla.VACIA));
        assertNull(Reescritor.reescribir(null, TABLA));
    }

    @Test
    void recorreLosHermanosYSoloCambiaLosQueCoinciden() {
        ITextComponent raiz = new TextComponentString("<Laly> ");
        raiz.getStyle().setColor(TextFormatting.AQUA);
        ITextComponent saludo = new TextComponentString("Hello");
        saludo.getStyle().setColor(TextFormatting.WHITE);
        raiz.appendSibling(saludo);
        raiz.appendSibling(new TextComponentString(" Steve"));
        ITextComponent nuevo = Reescritor.reescribir(raiz, TABLA);
        assertEquals("<Laly> Hola Steve", nuevo.getUnformattedText());
        assertEquals(TextFormatting.AQUA, nuevo.getStyle().getColor());
        assertEquals(TextFormatting.WHITE, nuevo.getSiblings().get(0).getStyle().getColor());
        assertSame(raiz.getSiblings().get(1), nuevo.getSiblings().get(1)); // lo que no cambia, no se copia
    }

    @Test
    void conservaElEventoDeClic() {
        ITextComponent original = new TextComponentString("Click here");
        original.getStyle().setClickEvent(new ClickEvent(ClickEvent.Action.OPEN_URL, "https://example.com"));
        ITextComponent nuevo = Reescritor.reescribir(original, TABLA);
        assertEquals("Haz clic aquí", nuevo.getUnformattedText());
        assertEquals("https://example.com", nuevo.getStyle().getClickEvent().getValue());
    }

    @Test
    void reconocePlantillasConDatos() {
        ITextComponent nuevo = Reescritor.reescribir(new TextComponentString("Hello Steve, welcome back!"), TABLA);
        assertEquals("¡Hola Steve, bienvenido de nuevo!", nuevo.getUnformattedText());
    }

    @Test
    void traduceLosArgumentosDeUnComponenteTraducible() {
        ITextComponent original = new TextComponentTranslation("chat.type.text", "Laly", new TextComponentString("Hello"));
        ITextComponent nuevo = Reescritor.reescribir(original, TABLA);
        Object[] argumentos = ((TextComponentTranslation) nuevo).getFormatArgs();
        assertEquals("chat.type.text", ((TextComponentTranslation) nuevo).getKey());
        assertEquals("Laly", argumentos[0]);
        assertEquals("Hola", ((ITextComponent) argumentos[1]).getUnformattedText());
    }

    @Test
    void unaLineaDeTooltipConservaSusCodigosDeFormato() {
        assertEquals("§7Hola§r", Reescritor.reescribirLinea("§7Hello§r", TABLA));
        assertEquals("¡La solicitud de TPA expiró!", Reescritor.reescribirLinea("TPA request expired!", TABLA));
        assertNull(Reescritor.reescribirLinea("§7Nothing", TABLA));
        assertNull(Reescritor.reescribirLinea("Hello", Tabla.VACIA));
        assertNull(Reescritor.reescribirLinea(null, TABLA));
    }

    @Test
    void noRompeUnEstiloVacio() {
        Style vacio = new Style();
        ITextComponent original = new TextComponentString("Hello");
        original.setStyle(vacio);
        assertEquals("Hola", Reescritor.reescribir(original, TABLA).getUnformattedText());
    }
}

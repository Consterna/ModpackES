package io.github.consterna.modpackes;

import net.minecraft.util.text.TextFormatting;
import net.minecraft.util.text.event.ClickEvent;
import net.minecraft.util.text.ITextComponent;
import net.minecraft.util.text.IFormattableTextComponent;
import net.minecraft.util.text.Style;
import net.minecraft.util.text.StringTextComponent;
import net.minecraft.util.text.TranslationTextComponent;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

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
            "Click here", "Haz clic aquí");

    @Test
    void cambiaUnLiteralYConservaElEstilo() {
        Style estilo = Style.EMPTY.withColor(TextFormatting.RED).withBold(true);
        ITextComponent original = new StringTextComponent("TPA request expired!").setStyle(estilo);
        ITextComponent nuevo = Reescritor.reescribir(original, TABLA);
        assertEquals("¡La solicitud de TPA expiró!", nuevo.getString());
        assertEquals(estilo, nuevo.getStyle());
    }

    @Test
    void sinCoincidenciaDevuelveNullYNoCopia() {
        assertNull(Reescritor.reescribir(new StringTextComponent("Nothing to see here"), TABLA));
        assertNull(Reescritor.reescribir(new StringTextComponent("Hello"), Tabla.VACIA));
        assertNull(Reescritor.reescribir(null, TABLA));
    }

    @Test
    void recorreLosHermanosYSoloCambiaLosQueCoinciden() {
        IFormattableTextComponent raiz = new StringTextComponent("<Laly> ").withStyle(TextFormatting.AQUA);
        raiz.append(new StringTextComponent("Hello").withStyle(TextFormatting.WHITE));
        raiz.append(new StringTextComponent(" Steve"));
        ITextComponent nuevo = Reescritor.reescribir(raiz, TABLA);
        assertEquals("<Laly> Hola Steve", nuevo.getString());
        assertEquals(TextFormatting.AQUA.getColor(), nuevo.getStyle().getColor().getValue());
        assertEquals(TextFormatting.WHITE.getColor(), nuevo.getSiblings().get(0).getStyle().getColor().getValue());
        assertSame(raiz.getSiblings().get(1), nuevo.getSiblings().get(1)); // lo que no cambia, no se copia
    }

    @Test
    void conservaElEventoDeClic() {
        Style estilo = Style.EMPTY.withClickEvent(new ClickEvent(ClickEvent.Action.OPEN_URL, "https://example.com"));
        ITextComponent nuevo = Reescritor.reescribir(new StringTextComponent("Click here").setStyle(estilo), TABLA);
        assertEquals("Haz clic aquí", nuevo.getString());
        assertEquals("https://example.com", nuevo.getStyle().getClickEvent().getValue());
    }

    @Test
    void cambiaLosArgumentosDeUnTraducible() {
        ITextComponent original = new TranslationTextComponent("chat.type.text", new StringTextComponent("Hello"), "Hello");
        ITextComponent nuevo = Reescritor.reescribir(original, TABLA);
        TranslationTextComponent contenido = (TranslationTextComponent) nuevo;
        assertEquals("chat.type.text", contenido.getKey());
        assertEquals("Hola", ((ITextComponent) contenido.getArgs()[0]).getString());
        assertEquals("Hola", contenido.getArgs()[1]);
    }

    @Test
    void noInventaTextoConEspaciosYAcentos() {
        Tabla t = tabla("Ñandú says hi", "Ñandú dice ¡hola! 😀");
        ITextComponent nuevo = Reescritor.reescribir(new StringTextComponent("  Ñandú says hi "), t);
        assertTrue(nuevo.getString().equals("  Ñandú dice ¡hola! 😀 "));
    }
}

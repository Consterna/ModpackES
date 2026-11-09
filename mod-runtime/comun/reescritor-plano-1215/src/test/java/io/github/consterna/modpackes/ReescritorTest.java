package io.github.consterna.modpackes;

import com.mojang.datafixers.util.Either;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.FormattedText;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import net.minecraft.network.chat.contents.TranslatableContents;
import net.minecraft.world.inventory.tooltip.TooltipComponent;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReescritorTest {
    private static final Tabla TABLA = new Tabla(Map.of(
            "TPA request expired!", "¡La solicitud de TPA expiró!",
            "Hello", "Hola",
            "Click here", "Haz clic aquí"));

    @Test
    void cambiaUnLiteralYConservaElEstilo() {
        Style estilo = Style.EMPTY.withColor(ChatFormatting.RED).withBold(true);
        Component original = Component.literal("TPA request expired!").setStyle(estilo);
        Component nuevo = Reescritor.reescribir(original, TABLA);
        assertEquals("¡La solicitud de TPA expiró!", nuevo.getString());
        assertEquals(estilo, nuevo.getStyle());
    }

    @Test
    void sinCoincidenciaDevuelveNullYNoCopia() {
        assertNull(Reescritor.reescribir(Component.literal("Nothing to see here"), TABLA));
        assertNull(Reescritor.reescribir(Component.literal("Hello"), Tabla.VACIA));
        assertNull(Reescritor.reescribir(null, TABLA));
    }

    @Test
    void recorreLosHermanosYSoloCambiaLosQueCoinciden() {
        MutableComponent raiz = Component.literal("<Laly> ").withStyle(ChatFormatting.AQUA);
        raiz.append(Component.literal("Hello").withStyle(ChatFormatting.WHITE));
        raiz.append(Component.literal(" Steve"));
        Component nuevo = Reescritor.reescribir(raiz, TABLA);
        assertEquals("<Laly> Hola Steve", nuevo.getString());
        // los colores se comparan con los del original: ChatFormatting.getColor() desaparece en Minecraft 26.2
        assertEquals(raiz.getStyle().getColor(), nuevo.getStyle().getColor());
        assertEquals(raiz.getSiblings().get(0).getStyle().getColor(), nuevo.getSiblings().get(0).getStyle().getColor());
        assertSame(raiz.getSiblings().get(1), nuevo.getSiblings().get(1)); // lo que no cambia, no se copia
    }

    @Test
    void conservaElEventoDeClic() {
        Style estilo = Style.EMPTY.withClickEvent(new ClickEvent.OpenUrl(URI.create("https://example.com")));
        Component nuevo = Reescritor.reescribir(Component.literal("Click here").setStyle(estilo), TABLA);
        assertEquals("Haz clic aquí", nuevo.getString());
        assertEquals(estilo.getClickEvent(), nuevo.getStyle().getClickEvent());
    }

    @Test
    void cambiaLosArgumentosDeUnTraducible() {
        Component original = Component.translatable("chat.type.text", Component.literal("Hello"), "Hello");
        Component nuevo = Reescritor.reescribir(original, TABLA);
        TranslatableContents contenido = (TranslatableContents) nuevo.getContents();
        assertEquals("chat.type.text", contenido.getKey());
        assertEquals("Hola", ((Component) contenido.getArgs()[0]).getString());
        assertEquals("Hola", contenido.getArgs()[1]);
    }

    @Test
    void noInventaTextoConEspaciosYAcentos() {
        Tabla t = new Tabla(Map.of("Ñandú says hi", "Ñandú dice ¡hola! 😀"));
        Component nuevo = Reescritor.reescribir(Component.literal("  Ñandú says hi "), t);
        assertTrue(nuevo.getString().equals("  Ñandú dice ¡hola! 😀 "));
    }

    @Test
    void cambiaLasLineasDeUnTooltipYDejaLoQueNoEsTexto() {
        TooltipComponent imagen = new TooltipComponent() {
        };
        FormattedText plano = FormattedText.of("Hello");
        Component otra = Component.literal("Other");
        List<Either<FormattedText, TooltipComponent>> elementos = new ArrayList<>();
        elementos.add(Either.left(Component.literal("Hello")));
        elementos.add(Either.right(imagen));
        elementos.add(Either.left(plano));
        elementos.add(Either.left(otra));

        Reescritor.reescribirElementos(elementos, TABLA);

        assertEquals("Hola", ((Component) elementos.get(0).left().orElseThrow()).getString());
        assertSame(imagen, elementos.get(1).right().orElseThrow());
        assertSame(plano, elementos.get(2).left().orElseThrow());
        assertSame(otra, elementos.get(3).left().orElseThrow());
    }

    @Test
    void losTooltipsSinTablaOSinListaNoHacenNada() {
        Component original = Component.literal("Hello");
        List<Either<FormattedText, TooltipComponent>> elementos = new ArrayList<>();
        elementos.add(Either.left(original));

        Reescritor.reescribirElementos(elementos, Tabla.VACIA);
        Reescritor.reescribirElementos(null, TABLA);

        assertSame(original, elementos.get(0).left().orElseThrow());
    }
}

package io.github.consterna.modpackes;

import com.mojang.datafixers.util.Either;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.FormattedText;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import net.minecraft.network.chat.TextComponent;
import net.minecraft.network.chat.TranslatableComponent;
import net.minecraft.world.inventory.tooltip.TooltipComponent;
import org.junit.jupiter.api.Test;

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
        Component original = new TextComponent("TPA request expired!").setStyle(estilo);
        Component nuevo = Reescritor.reescribir(original, TABLA);
        assertEquals("¡La solicitud de TPA expiró!", nuevo.getString());
        assertEquals(estilo, nuevo.getStyle());
    }

    @Test
    void sinCoincidenciaDevuelveNullYNoCopia() {
        assertNull(Reescritor.reescribir(new TextComponent("Nothing to see here"), TABLA));
        assertNull(Reescritor.reescribir(new TextComponent("Hello"), Tabla.VACIA));
        assertNull(Reescritor.reescribir(null, TABLA));
    }

    @Test
    void recorreLosHermanosYSoloCambiaLosQueCoinciden() {
        MutableComponent raiz = new TextComponent("<Laly> ").withStyle(ChatFormatting.AQUA);
        raiz.append(new TextComponent("Hello").withStyle(ChatFormatting.WHITE));
        raiz.append(new TextComponent(" Steve"));
        Component nuevo = Reescritor.reescribir(raiz, TABLA);
        assertEquals("<Laly> Hola Steve", nuevo.getString());
        assertEquals(ChatFormatting.AQUA.getColor(), nuevo.getStyle().getColor().getValue());
        assertEquals(ChatFormatting.WHITE.getColor(), nuevo.getSiblings().get(0).getStyle().getColor().getValue());
        assertSame(raiz.getSiblings().get(1), nuevo.getSiblings().get(1)); // lo que no cambia, no se copia
    }

    @Test
    void conservaElEventoDeClic() {
        Style estilo = Style.EMPTY.withClickEvent(new ClickEvent(ClickEvent.Action.OPEN_URL, "https://example.com"));
        Component nuevo = Reescritor.reescribir(new TextComponent("Click here").setStyle(estilo), TABLA);
        assertEquals("Haz clic aquí", nuevo.getString());
        assertEquals("https://example.com", nuevo.getStyle().getClickEvent().getValue());
    }

    @Test
    void cambiaLosArgumentosDeUnTraducible() {
        Component original = new TranslatableComponent("chat.type.text", new TextComponent("Hello"), "Hello");
        Component nuevo = Reescritor.reescribir(original, TABLA);
        TranslatableComponent contenido = (TranslatableComponent) nuevo;
        assertEquals("chat.type.text", contenido.getKey());
        assertEquals("Hola", ((Component) contenido.getArgs()[0]).getString());
        assertEquals("Hola", contenido.getArgs()[1]);
    }

    @Test
    void noInventaTextoConEspaciosYAcentos() {
        Tabla t = new Tabla(Map.of("Ñandú says hi", "Ñandú dice ¡hola! 😀"));
        Component nuevo = Reescritor.reescribir(new TextComponent("  Ñandú says hi "), t);
        assertTrue(nuevo.getString().equals("  Ñandú dice ¡hola! 😀 "));
    }

    @Test
    void cambiaLasLineasDeUnTooltipYDejaLoQueNoEsTexto() {
        TooltipComponent imagen = new TooltipComponent() {
        };
        FormattedText plano = FormattedText.of("Hello");
        Component otra = new TextComponent("Other");
        List<Either<FormattedText, TooltipComponent>> elementos = new ArrayList<>();
        elementos.add(Either.left(new TextComponent("Hello")));
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
        Component original = new TextComponent("Hello");
        List<Either<FormattedText, TooltipComponent>> elementos = new ArrayList<>();
        elementos.add(Either.left(original));

        Reescritor.reescribirElementos(elementos, Tabla.VACIA);
        Reescritor.reescribirElementos(null, TABLA);

        assertSame(original, elementos.get(0).left().orElseThrow());
    }
}

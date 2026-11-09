package io.github.consterna.modpackes;

import com.mojang.datafixers.util.Either;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.FormattedText;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.TextComponent;
import net.minecraft.network.chat.TranslatableComponent;
import net.minecraft.world.inventory.tooltip.TooltipComponent;

import java.util.ArrayList;
import java.util.List;

/**
 * Cambia el texto literal de un componente por su traducción, sin tocar estilos, colores, eventos de clic ni
 * el resto de la estructura. Nunca lanza por un componente raro: si algo no se entiende, se deja igual.
 */
public final class Reescritor {
    private Reescritor() {
    }

    /** El componente traducido, o {@code null} si no cambió nada (así no se copia lo que no hace falta). */
    public static Component reescribir(Component original, Tabla tabla) {
        if (original == null || tabla.vacia()) {
            return null;
        }
        // Antes de 1.19 el texto es un componente propio (TextComponent, TranslatableComponent), no un «contenido»
        String textoNuevo = null;
        Object[] argumentosNuevos = null;
        boolean cambio = false;

        if (original instanceof TextComponent literal) {
            textoNuevo = tabla.traducir(literal.getText());
            cambio = textoNuevo != null;
        } else if (original instanceof TranslatableComponent traducible) {
            Object[] argumentos = traducible.getArgs();
            for (int i = 0; i < argumentos.length; i++) {
                Object reemplazo = null;
                if (argumentos[i] instanceof Component hijo) {
                    reemplazo = reescribir(hijo, tabla);
                } else if (argumentos[i] instanceof String texto) {
                    reemplazo = tabla.traducir(texto);
                }
                if (reemplazo != null) {
                    if (argumentosNuevos == null) {
                        argumentosNuevos = argumentos.clone();
                    }
                    argumentosNuevos[i] = reemplazo;
                }
            }
            cambio = argumentosNuevos != null;
        }

        List<Component> hermanos = original.getSiblings();
        List<Component> nuevosHermanos = null;
        for (int i = 0; i < hermanos.size(); i++) {
            Component reemplazo = reescribir(hermanos.get(i), tabla);
            if (reemplazo != null) {
                if (nuevosHermanos == null) {
                    nuevosHermanos = new ArrayList<>(hermanos);
                }
                nuevosHermanos.set(i, reemplazo);
            }
        }

        if (!cambio && nuevosHermanos == null) {
            return null;
        }
        MutableComponent resultado;
        if (original instanceof TextComponent literal) {
            resultado = new TextComponent(textoNuevo != null ? textoNuevo : literal.getText());
        } else if (original instanceof TranslatableComponent traducible) {
            resultado = new TranslatableComponent(
                    traducible.getKey(), argumentosNuevos != null ? argumentosNuevos : traducible.getArgs());
        } else {
            resultado = original.plainCopy(); // otro tipo de componente: se copia tal cual y solo cambian sus hermanos
        }
        resultado.setStyle(original.getStyle());
        for (Component hermano : nuevosHermanos != null ? nuevosHermanos : hermanos) {
            resultado.append(hermano);
        }
        return resultado;
    }

    /**
     * Cambia en su sitio las líneas de texto de un tooltip (las que son un {@link Component}); lo que no es texto
     * o no está en la tabla se deja como está.
     */
    public static void reescribirElementos(List<Either<FormattedText, TooltipComponent>> elementos, Tabla tabla) {
        if (elementos == null || tabla.vacia()) {
            return;
        }
        for (int i = 0; i < elementos.size(); i++) {
            Either<FormattedText, TooltipComponent> elemento = elementos.get(i);
            if (elemento != null && elemento.left().orElse(null) instanceof Component linea) {
                Component nuevo = reescribir(linea, tabla);
                if (nuevo != null) {
                    elementos.set(i, Either.left(nuevo));
                }
            }
        }
    }

    /** Cambia el texto de un botón, casilla o etiqueta si está en la tabla. */
    public static void reescribirMensaje(AbstractWidget widget, Tabla tabla) {
        if (widget == null || tabla.vacia()) {
            return;
        }
        Component nuevo = reescribir(widget.getMessage(), tabla);
        if (nuevo != null) {
            widget.setMessage(nuevo);
        }
    }
}

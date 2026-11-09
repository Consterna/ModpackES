package io.github.consterna.modpackes;


import net.minecraft.client.gui.widget.Widget;
import net.minecraft.util.text.IFormattableTextComponent;
import net.minecraft.util.text.ITextComponent;
import net.minecraft.util.text.StringTextComponent;
import net.minecraft.util.text.TranslationTextComponent;

import java.util.ArrayList;
import java.util.List;

/**
 * Cambia el texto literal de un componente por su traducción, sin tocar estilos, colores, eventos de clic ni
 * el resto de la estructura. Nunca lanza por un componente raro: si algo no se entiende, se deja igual.
 * Variante de Minecraft 1.16.5: Java 8, el texto es un componente propio (StringTextComponent, TranslationTextComponent)
 * y no hay tooltips por elementos.
 */
public final class Reescritor {
    private Reescritor() {
    }

    /** El componente traducido, o {@code null} si no cambió nada (así no se copia lo que no hace falta). */
    public static ITextComponent reescribir(ITextComponent original, Tabla tabla) {
        if (original == null || tabla.vacia()) {
            return null;
        }
        String textoNuevo = null;
        Object[] argumentosNuevos = null;
        boolean cambio = false;

        if (original instanceof StringTextComponent) {
            textoNuevo = tabla.traducir(((StringTextComponent) original).getText());
            cambio = textoNuevo != null;
        } else if (original instanceof TranslationTextComponent) {
            Object[] argumentos = ((TranslationTextComponent) original).getArgs();
            for (int i = 0; i < argumentos.length; i++) {
                Object reemplazo = null;
                if (argumentos[i] instanceof ITextComponent) {
                    reemplazo = reescribir((ITextComponent) argumentos[i], tabla);
                } else if (argumentos[i] instanceof String) {
                    reemplazo = tabla.traducir((String) argumentos[i]);
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

        List<ITextComponent> hermanos = original.getSiblings();
        List<ITextComponent> nuevosHermanos = null;
        for (int i = 0; i < hermanos.size(); i++) {
            ITextComponent reemplazo = reescribir(hermanos.get(i), tabla);
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
        IFormattableTextComponent resultado;
        if (original instanceof StringTextComponent) {
            resultado = new StringTextComponent(textoNuevo != null ? textoNuevo : ((StringTextComponent) original).getText());
        } else if (original instanceof TranslationTextComponent) {
            TranslationTextComponent traducible = (TranslationTextComponent) original;
            resultado = new TranslationTextComponent(
                    traducible.getKey(), argumentosNuevos != null ? argumentosNuevos : traducible.getArgs());
        } else {
            resultado = original.plainCopy(); // otro tipo de componente: se copia tal cual y solo cambian sus hermanos
        }
        resultado.setStyle(original.getStyle());
        for (ITextComponent hermano : nuevosHermanos != null ? nuevosHermanos : hermanos) {
            resultado.append(hermano);
        }
        return resultado;
    }

    /** Cambia el texto de un botón, casilla o etiqueta si está en la tabla. */
    public static void reescribirMensaje(Widget widget, Tabla tabla) {
        if (widget == null || tabla.vacia()) {
            return;
        }
        ITextComponent nuevo = reescribir(widget.getMessage(), tabla);
        if (nuevo != null) {
            widget.setMessage(nuevo);
        }
    }
}

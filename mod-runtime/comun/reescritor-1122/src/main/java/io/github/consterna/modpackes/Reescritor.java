package io.github.consterna.modpackes;

import net.minecraft.client.gui.GuiButton;
import net.minecraft.util.text.ITextComponent;
import net.minecraft.util.text.TextComponentString;
import net.minecraft.util.text.TextComponentTranslation;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Cambia el texto literal de un componente (o de una línea de tooltip) por su traducción, sin tocar estilos, colores,
 * eventos de clic ni el resto de la estructura. Nunca lanza por un componente raro: si algo no se entiende, se deja
 * igual. Variante de Minecraft 1.12.2: Java 8, el texto es un componente propio (TextComponentString,
 * TextComponentTranslation) y los tooltips son cadenas con códigos de formato («§7texto»).
 */
public final class Reescritor {
    /** Códigos de formato al principio y al final de una línea: se conservan y solo se traduce lo de en medio. */
    private static final Pattern LINEA = Pattern.compile("^((?:§[0-9a-fk-orA-FK-OR])*)(.*?)((?:§[0-9a-fk-orA-FK-OR])*)$", Pattern.DOTALL);

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

        if (original instanceof TextComponentString) {
            textoNuevo = tabla.traducir(((TextComponentString) original).getText());
            cambio = textoNuevo != null;
        } else if (original instanceof TextComponentTranslation) {
            Object[] argumentos = ((TextComponentTranslation) original).getFormatArgs();
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
        ITextComponent resultado;
        if (original instanceof TextComponentString) {
            resultado = new TextComponentString(textoNuevo != null ? textoNuevo : ((TextComponentString) original).getText());
        } else if (original instanceof TextComponentTranslation) {
            TextComponentTranslation traducible = (TextComponentTranslation) original;
            resultado = new TextComponentTranslation(
                    traducible.getKey(), argumentosNuevos != null ? argumentosNuevos : traducible.getFormatArgs());
        } else {
            resultado = original.createCopy(); // otro tipo de componente: se copia tal cual y solo cambian sus hermanos
            resultado.getSiblings().clear(); // createCopy también copia los hermanos: se vuelven a poner abajo
        }
        resultado.setStyle(original.getStyle().createDeepCopy());
        for (ITextComponent hermano : nuevosHermanos != null ? nuevosHermanos : hermanos) {
            resultado.appendSibling(hermano);
        }
        return resultado;
    }

    /** La línea de tooltip traducida (con sus códigos de formato), o {@code null} si no cambió. */
    public static String reescribirLinea(String linea, Tabla tabla) {
        if (linea == null || tabla.vacia()) {
            return null;
        }
        Matcher m = LINEA.matcher(linea);
        if (!m.matches()) {
            return null;
        }
        String traducida = tabla.traducir(m.group(2));
        return traducida == null ? null : m.group(1) + traducida + m.group(3);
    }

    /** Cambia el texto de un botón si está en la tabla. */
    public static void reescribirBoton(GuiButton boton, Tabla tabla) {
        if (boton == null) {
            return;
        }
        String nuevo = reescribirLinea(boton.displayString, tabla);
        if (nuevo != null) {
            boton.displayString = nuevo;
        }
    }
}

package io.github.consterna.modpackes;

import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.ComponentContents;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.contents.PlainTextContents;
import net.minecraft.network.chat.contents.TranslatableContents;

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
        ComponentContents contenido = original.getContents();
        ComponentContents nuevoContenido = contenido;
        boolean cambio = false;

        if (contenido instanceof PlainTextContents.LiteralContents literal) {
            String traducido = tabla.traducir(literal.text());
            if (traducido != null) {
                nuevoContenido = new PlainTextContents.LiteralContents(traducido);
                cambio = true;
            }
        } else if (contenido instanceof TranslatableContents traducible) {
            Object[] argumentos = traducible.getArgs();
            Object[] nuevos = null;
            for (int i = 0; i < argumentos.length; i++) {
                Object reemplazo = null;
                if (argumentos[i] instanceof Component hijo) {
                    reemplazo = reescribir(hijo, tabla);
                } else if (argumentos[i] instanceof String texto) {
                    reemplazo = tabla.traducir(texto);
                }
                if (reemplazo != null) {
                    if (nuevos == null) {
                        nuevos = argumentos.clone();
                    }
                    nuevos[i] = reemplazo;
                }
            }
            if (nuevos != null) {
                nuevoContenido = new TranslatableContents(traducible.getKey(), traducible.getFallback(), nuevos);
                cambio = true;
            }
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
        MutableComponent resultado = MutableComponent.create(nuevoContenido).setStyle(original.getStyle());
        for (Component hermano : nuevosHermanos != null ? nuevosHermanos : hermanos) {
            resultado.append(hermano);
        }
        return resultado;
    }
}

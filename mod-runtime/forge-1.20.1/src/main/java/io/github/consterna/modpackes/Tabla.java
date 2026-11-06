package io.github.consterna.modpackes;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.io.Reader;
import java.util.HashMap;
import java.util.Map;

/**
 * Tabla de textos «inglés exacto → español» que genera ModpackES. Solo hay coincidencia si el texto es idéntico
 * (salvo los espacios de los bordes, que se conservan): no hay traducción aproximada ni en vivo.
 */
public final class Tabla {
    public static final Tabla VACIA = new Tabla(Map.of());

    private final Map<String, String> textos;

    public Tabla(Map<String, String> textos) {
        this.textos = Map.copyOf(textos);
    }

    /** Lee un objeto JSON {"inglés": "español"}. Lo que no sea texto se ignora. */
    public static Tabla leer(Reader lector) throws IOException {
        JsonElement raiz;
        try {
            raiz = JsonParser.parseReader(lector);
        } catch (JsonParseException e) {
            throw new IOException("La tabla de textos no es JSON válido", e);
        }
        if (!raiz.isJsonObject()) {
            throw new IOException("La tabla de textos no es un objeto JSON");
        }
        JsonObject objeto = raiz.getAsJsonObject();
        Map<String, String> mapa = new HashMap<>();
        for (Map.Entry<String, JsonElement> e : objeto.entrySet()) {
            JsonElement v = e.getValue();
            if (v.isJsonPrimitive() && v.getAsJsonPrimitive().isString() && !v.getAsString().isEmpty()) {
                mapa.put(e.getKey(), v.getAsString());
            }
        }
        return new Tabla(mapa);
    }

    /** Une dos tablas; si un texto está en las dos, manda la de {@code otra}. */
    public Tabla combinar(Tabla otra) {
        if (otra.textos.isEmpty()) {
            return this;
        }
        Map<String, String> mapa = new HashMap<>(textos);
        mapa.putAll(otra.textos);
        return new Tabla(mapa);
    }

    public boolean vacia() {
        return textos.isEmpty();
    }

    public int tamano() {
        return textos.size();
    }

    /** La traducción de {@code texto}, o {@code null} si no está en la tabla o no cambia nada. */
    public String traducir(String texto) {
        if (texto == null || texto.isEmpty() || textos.isEmpty()) {
            return null;
        }
        String directo = textos.get(texto);
        if (directo != null) {
            return directo.equals(texto) ? null : directo;
        }
        String nucleo = texto.strip();
        if (nucleo.isEmpty() || nucleo.length() == texto.length()) {
            return null;
        }
        String traduccion = textos.get(nucleo);
        if (traduccion == null || traduccion.equals(nucleo)) {
            return null;
        }
        int inicio = texto.length() - texto.stripLeading().length();
        int fin = texto.length() - texto.stripTrailing().length();
        return texto.substring(0, inicio) + traduccion + texto.substring(texto.length() - fin);
    }
}

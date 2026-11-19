package io.github.consterna.modpackes.sonda;

import com.google.gson.stream.JsonWriter;

import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Escribe los tres JSON de la sonda. Todos empiezan con {@code formato}, {@code loader}, {@code minecraft} y
 * {@code idioma} para que quien los lea sepa de dónde salen.
 */
public final class Volcado {
    public static final int FORMATO = 1;
    public static final String IDIOMA = "idioma.json";
    public static final String TEXTOS = "textos-dibujados.json";
    public static final String REGISTROS = "registros.json";

    private Volcado() {
    }

    /** Lo que identifica la partida: el loader, la versión de Minecraft y el idioma elegido. */
    public record Origen(String loader, String minecraft, String idioma) {
    }

    /** Escribe en un archivo temporal y lo mueve encima del final, para no dejar nunca un JSON a medias. */
    public static void escribirAtomico(Path destino, Contenido contenido) throws IOException {
        Files.createDirectories(destino.toAbsolutePath().getParent());
        Path temporal = destino.resolveSibling(destino.getFileName() + ".tmp");
        try (Writer w = Files.newBufferedWriter(temporal, StandardCharsets.UTF_8)) {
            contenido.escribir(w);
        }
        try {
            Files.move(temporal, destino, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(temporal, destino, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    /** Lo que se escribe en un archivo. */
    @FunctionalInterface
    public interface Contenido {
        void escribir(Writer w) throws IOException;
    }

    /**
     * El mapa de idioma cargado y el de en_us. Cada clave lleva su valor, el de en_us (o {@code null} si en_us no la
     * tiene) y {@code igual}: si los dos son el mismo texto, es decir, si el jugador la ve en inglés.
     */
    public static void escribirIdioma(Writer w, Origen origen, int recarga, Map<String, String> actual,
                                      Map<String, String> enUs) throws IOException {
        List<String> claves = new ArrayList<>(actual.keySet());
        claves.sort(null);
        int iguales = 0;
        for (String clave : claves) {
            if (Objects.equals(actual.get(clave), enUs.get(clave))) {
                iguales++;
            }
        }
        JsonWriter j = abrir(w, origen);
        j.name("recarga").value(recarga);
        j.name("total").value(claves.size());
        j.name("iguales_a_en_us").value(iguales);
        j.name("claves").beginArray();
        for (String clave : claves) {
            String valor = actual.get(clave);
            String ingles = enUs.get(clave);
            j.beginObject();
            j.name("clave").value(clave);
            j.name("valor").value(valor);
            j.name("en_us").value(ingles);
            j.name("igual").value(Objects.equals(valor, ingles));
            j.endObject();
        }
        j.endArray();
        cerrar(j);
    }

    /** Los textos dibujados, sin repetir, con sus pantallas. */
    public static void escribirTextos(Writer w, Origen origen, List<TextosDibujados.Entrada> textos, long descartados)
            throws IOException {
        JsonWriter j = abrir(w, origen);
        j.name("total").value(textos.size());
        j.name("descartados_por_tope").value(descartados);
        j.name("textos").beginArray();
        for (TextosDibujados.Entrada e : textos) {
            j.beginObject();
            j.name("texto").value(e.texto());
            j.name("pantallas").beginArray();
            for (String p : e.pantallas()) {
                j.value(p);
            }
            j.endArray();
            j.endObject();
        }
        j.endArray();
        cerrar(j);
    }

    /**
     * Lo registrado, en el orden recibido. {@code igual} dice si el valor es el mismo texto que la clave tiene en en_us
     * ({@code null} si no hay clave o en_us no la tiene).
     */
    public static void escribirRegistros(Writer w, Origen origen, List<Elemento> elementos, Map<String, String> enUs)
            throws IOException {
        JsonWriter j = abrir(w, origen);
        j.name("total").value(elementos.size());
        j.name("elementos").beginArray();
        for (Elemento e : elementos) {
            String ingles = e.clave() == null ? null : enUs.get(e.clave());
            j.beginObject();
            j.name("categoria").value(e.categoria());
            j.name("id").value(e.id());
            j.name("clave").value(e.clave());
            j.name("valor").value(e.valor());
            j.name("existe").value(e.existe());
            j.name("en_us").value(ingles);
            if (ingles == null) {
                j.name("igual").nullValue();
            } else {
                j.name("igual").value(ingles.equals(e.valor()));
            }
            if (e.tooltip() != null) {
                j.name("tooltip").beginArray();
                for (String linea : e.tooltip()) {
                    j.value(linea);
                }
                j.endArray();
            }
            j.endObject();
        }
        j.endArray();
        cerrar(j);
    }

    private static JsonWriter abrir(Writer w, Origen origen) throws IOException {
        JsonWriter j = new JsonWriter(w);
        j.setIndent(" ");
        j.setHtmlSafe(false);
        j.setSerializeNulls(true);
        j.beginObject();
        j.name("formato").value(FORMATO);
        j.name("loader").value(origen.loader());
        j.name("minecraft").value(origen.minecraft());
        j.name("idioma").value(origen.idioma());
        return j;
    }

    private static void cerrar(JsonWriter j) throws IOException {
        j.endObject();
        j.flush();
    }
}

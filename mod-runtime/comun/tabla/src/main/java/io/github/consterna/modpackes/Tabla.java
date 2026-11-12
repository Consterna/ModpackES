package io.github.consterna.modpackes;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.io.Reader;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Tabla de textos «inglés → español» que genera ModpackES. Hay dos clases de entrada:
 * <ul>
 *   <li><b>Exactas</b>: solo coinciden si el texto es idéntico (salvo los espacios de los bordes, que se conservan).</li>
 *   <li><b>Plantillas</b>: la clave lleva {@code %s} o {@code %d} (como el {@code String.format} del mod original) y coinciden
 *       con cualquier texto que sea ese mismo molde con otros datos: «Hello %s!» coincide con «Hello Steve!». El español
 *       reutiliza lo capturado; puede llevar {@code %1$s}, {@code %2$s} para cambiar el orden.</li>
 * </ul>
 * No hay traducción aproximada ni en vivo.
 */
public final class Tabla {
    public static final Tabla VACIA = new Tabla(Collections.<String, String>emptyMap());

    private static final Pattern MARCADOR = Pattern.compile("%(?:(\\d+)\\$)?([sd%])");
    private static final int MINIMO_FIJO = 4; // una plantilla con casi nada de texto fijo coincidiría con cualquier cosa
    private static final int TAMANO_CACHE = 512;
    private static final String SIN_COINCIDENCIA = "\u0000";

    private final Map<String, String> exactos;
    private final List<Plantilla> plantillas;
    private final Map<String, String> cache = new LinkedHashMap<String, String>(64, 0.75f, true) {
        @Override
        protected boolean removeEldestEntry(Map.Entry<String, String> eldest) {
            return size() > TAMANO_CACHE;
        }
    };

    public Tabla(Map<String, String> textos) {
        Map<String, String> exactos = new HashMap<>();
        List<Plantilla> plantillas = new ArrayList<>();
        for (Map.Entry<String, String> e : textos.entrySet()) {
            if (esPlantilla(e.getKey())) {
                Plantilla p = Plantilla.crear(e.getKey(), e.getValue());
                if (p != null) {
                    plantillas.add(p);
                }
            } else {
                exactos.put(e.getKey(), e.getValue());
            }
        }
        plantillas.sort(Comparator.comparingInt((Plantilla p) -> p.fijo.length()).reversed()); // la más específica primero
        this.exactos = Collections.unmodifiableMap(exactos);
        this.plantillas = Collections.unmodifiableList(plantillas);
    }

    /** Lee un objeto JSON {"inglés": "español"}. Lo que no sea texto se ignora. */
    public static Tabla leer(Reader lector) throws IOException {
        JsonElement raiz;
        try {
            raiz = new JsonParser().parse(lector); // el único que existe también en el Gson de 1.16.5
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
        if (otra.vacia()) {
            return this;
        }
        Map<String, String> mapa = new HashMap<>(this.comoMapa());
        mapa.putAll(otra.comoMapa());
        return new Tabla(mapa);
    }

    private Map<String, String> comoMapa() {
        Map<String, String> mapa = new HashMap<>(exactos);
        for (Plantilla p : plantillas) {
            mapa.put(p.clave, p.valor);
        }
        return mapa;
    }

    public boolean vacia() {
        return exactos.isEmpty() && plantillas.isEmpty();
    }

    public int tamano() {
        return exactos.size() + plantillas.size();
    }

    public int plantillas() {
        return plantillas.size();
    }

    /** La traducción de {@code texto}, o {@code null} si no está en la tabla o no cambia nada. */
    public String traducir(String texto) {
        if (texto == null || texto.isEmpty() || vacia()) {
            return null;
        }
        String directo = buscar(texto);
        if (directo != null) {
            return directo.equals(texto) ? null : directo;
        }
        String nucleo = sinBordes(texto);
        if (nucleo.isEmpty() || nucleo.length() == texto.length()) {
            return null;
        }
        String traduccion = buscar(nucleo);
        if (traduccion == null || traduccion.equals(nucleo)) {
            return null;
        }
        int inicio = espaciosAlInicio(texto);
        int fin = espaciosAlFinal(texto);
        return texto.substring(0, inicio) + traduccion + texto.substring(texto.length() - fin);
    }

    // Como String.strip(), String.stripLeading() y String.stripTrailing() de Java 11, que Java 8 no tiene
    private static int espaciosAlInicio(String texto) {
        int i = 0;
        while (i < texto.length() && Character.isWhitespace(texto.charAt(i))) {
            i++;
        }
        return i;
    }

    private static int espaciosAlFinal(String texto) {
        int i = 0;
        while (i < texto.length() && Character.isWhitespace(texto.charAt(texto.length() - 1 - i))) {
            i++;
        }
        return i;
    }

    private static String sinBordes(String texto) {
        int inicio = espaciosAlInicio(texto);
        return inicio == texto.length() ? "" : texto.substring(inicio, texto.length() - espaciosAlFinal(texto));
    }

    private String buscar(String texto) {
        String exacto = exactos.get(texto);
        if (exacto != null) {
            return exacto;
        }
        if (plantillas.isEmpty()) {
            return null;
        }
        synchronized (cache) { // los tooltips piden el mismo texto cada cuadro: se recuerda el resultado
            String guardado = cache.get(texto);
            if (guardado != null) {
                return guardado.equals(SIN_COINCIDENCIA) ? null : guardado;
            }
            String resultado = null;
            for (Plantilla p : plantillas) {
                resultado = p.aplicar(texto);
                if (resultado != null) {
                    break;
                }
            }
            cache.put(texto, resultado == null ? SIN_COINCIDENCIA : resultado);
            return resultado;
        }
    }

    private static boolean esPlantilla(String clave) {
        Matcher m = MARCADOR.matcher(clave);
        while (m.find()) {
            if (!m.group(2).equals("%")) {
                return true;
            }
        }
        return false;
    }

    /** Un molde con datos variables: «Hello %s!» → «¡Hola %s!». */
    private static final class Plantilla {
        final String clave;
        final String valor;
        final String fijo; // el texto de la clave sin los marcadores
        final String prefijo; // lo que va antes del primer marcador: descarta rápido lo que no coincide
        final Pattern patron;
        final List<Object> destino; // trozos de texto y números de grupo (Integer, desde 1)

        private Plantilla(String clave, String valor, String fijo, String prefijo, Pattern patron, List<Object> destino) {
            this.clave = clave;
            this.valor = valor;
            this.fijo = fijo;
            this.prefijo = prefijo;
            this.patron = patron;
            this.destino = destino;
        }

        /** {@code null} si la plantilla no es segura (poco texto fijo o marcadores que no cuadran). */
        static Plantilla crear(String clave, String valor) {
            StringBuilder regex = new StringBuilder("^");
            StringBuilder fijo = new StringBuilder();
            String prefijo = null;
            int grupos = 0;
            int ultimo = 0;
            int siguiente = 1;
            // Argumento de String.format que llena cada grupo: «%2$s of %1$s» captura primero el 2 y después el 1
            List<Integer> argumentos = new ArrayList<>();
            Matcher m = MARCADOR.matcher(clave);
            while (m.find()) {
                String tramo = clave.substring(ultimo, m.start());
                fijo.append(tramo);
                if (!tramo.isEmpty()) {
                    regex.append(Pattern.quote(tramo));
                }
                if (m.group(2).equals("%")) {
                    fijo.append('%');
                    regex.append(Pattern.quote("%"));
                } else {
                    if (prefijo == null) {
                        prefijo = clave.substring(0, m.start());
                    }
                    grupos++;
                    argumentos.add(m.group(1) != null ? Integer.parseInt(m.group(1)) : siguiente++);
                    regex.append(m.group(2).equals("d") ? "(-?\\d+)" : "(.+?)");
                }
                ultimo = m.end();
            }
            String cola = clave.substring(ultimo);
            fijo.append(cola);
            if (!cola.isEmpty()) {
                regex.append(Pattern.quote(cola));
            }
            regex.append('$');
            if (grupos == 0 || sinBordes(fijo.toString()).length() < MINIMO_FIJO) {
                return null;
            }
            List<Object> destino = destino(valor, argumentos);
            if (destino == null) {
                return null;
            }
            return new Plantilla(clave, valor, fijo.toString(), prefijo == null ? "" : prefijo,
                    Pattern.compile(regex.toString(), Pattern.DOTALL), destino);
        }

        /** Trozos del español; cada dato apunta al grupo de la clave que llenó ese mismo argumento. */
        private static List<Object> destino(String valor, List<Integer> argumentos) {
            int grupos = argumentos.size();
            List<Object> partes = new ArrayList<>();
            Matcher m = MARCADOR.matcher(valor);
            int ultimo = 0;
            int siguiente = 1;
            boolean[] usado = new boolean[grupos + 1];
            while (m.find()) {
                if (m.start() > ultimo) {
                    partes.add(valor.substring(ultimo, m.start()));
                }
                if (m.group(2).equals("%")) {
                    partes.add("%");
                } else {
                    int argumento = m.group(1) != null ? Integer.parseInt(m.group(1)) : siguiente++;
                    int grupo = argumentos.indexOf(argumento) + 1;
                    if (grupo == 0) {
                        return null; // el español pide un dato que el inglés no tiene
                    }
                    usado[grupo] = true;
                    partes.add(grupo);
                }
                ultimo = m.end();
            }
            if (ultimo < valor.length()) {
                partes.add(valor.substring(ultimo));
            }
            for (int i = 1; i <= grupos; i++) {
                if (!usado[i]) {
                    return null; // la traducción perdió un dato: mejor no usarla
                }
            }
            return partes;
        }

        String aplicar(String texto) {
            if (!prefijo.isEmpty() && !texto.startsWith(prefijo)) {
                return null;
            }
            Matcher m = patron.matcher(texto);
            if (!m.matches()) {
                return null;
            }
            StringBuilder salida = new StringBuilder();
            for (Object parte : destino) {
                if (parte instanceof Integer) {
                    salida.append(m.group((Integer) parte));
                } else {
                    salida.append((String) parte);
                }
            }
            return salida.toString();
        }
    }
}

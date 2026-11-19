package io.github.consterna.modpackes.sonda;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Textos que el juego dibujó, sin repetir, con las pantallas en las que salieron. Se llama desde el hilo de dibujo en
 * cada cuadro, así que lo ya visto se descarta sin crear objetos; la copia para el disco se toma desde otro hilo.
 *
 * <p>Hay un tope de pares «texto + pantalla»: textos que cambian en cada cuadro (coordenadas de F3, contadores) no
 * deben llenar la memoria. Lo que pasa del tope solo se cuenta.
 */
public final class TextosDibujados {
    /** Pantalla de los textos que se dibujan sin ninguna abierta: el HUD, el chat, los carteles del mundo. */
    public static final String SIN_PANTALLA = "(sin pantalla)";
    public static final int LIMITE_POR_DEFECTO = 100_000;

    private final int limite;
    private final Map<String, Set<String>> porTexto = new ConcurrentHashMap<>();
    private final AtomicInteger pares = new AtomicInteger();
    private final AtomicLong descartados = new AtomicLong();
    private final AtomicBoolean cambiado = new AtomicBoolean();

    public TextosDibujados() {
        this(LIMITE_POR_DEFECTO);
    }

    public TextosDibujados(int limite) {
        this.limite = limite;
    }

    /**
     * Anota un texto. Devuelve {@code true} si el par «texto + pantalla» es nuevo. Un texto vacío o de solo espacios no
     * se anota; una pantalla nula cuenta como {@link #SIN_PANTALLA}.
     */
    public boolean anotar(String texto, String pantalla) {
        if (texto == null || texto.isBlank()) {
            return false;
        }
        String donde = pantalla == null ? SIN_PANTALLA : pantalla;
        Set<String> pantallas = porTexto.get(texto);
        if (pantallas != null && pantallas.contains(donde)) {
            return false; // lo normal: el mismo texto en el mismo sitio, cuadro tras cuadro
        }
        if (pares.get() >= limite) {
            descartados.incrementAndGet();
            return false;
        }
        if (!porTexto.computeIfAbsent(texto, t -> ConcurrentHashMap.newKeySet()).add(donde)) {
            return false; // otro hilo lo anotó a la vez
        }
        pares.incrementAndGet();
        cambiado.set(true);
        return true;
    }

    /** Pares «texto + pantalla» distintos guardados. */
    public int tamano() {
        return pares.get();
    }

    /** Veces que un par nuevo no se guardó por estar lleno. */
    public long descartados() {
        return descartados.get();
    }

    /** Devuelve si hubo pares nuevos desde la última llamada, y lo olvida. */
    public boolean tomarCambio() {
        return cambiado.getAndSet(false);
    }

    /** Copia ordenada por texto, con las pantallas de cada uno también ordenadas. */
    public List<Entrada> copia() {
        List<Entrada> lista = new ArrayList<>(porTexto.size());
        for (Map.Entry<String, Set<String>> e : porTexto.entrySet()) {
            List<String> pantallas = new ArrayList<>(e.getValue());
            pantallas.sort(null);
            lista.add(new Entrada(e.getKey(), pantallas));
        }
        lista.sort((a, b) -> a.texto().compareTo(b.texto()));
        return lista;
    }

    /** Un texto y las pantallas en las que se dibujó. */
    public record Entrada(String texto, List<String> pantallas) {
    }
}

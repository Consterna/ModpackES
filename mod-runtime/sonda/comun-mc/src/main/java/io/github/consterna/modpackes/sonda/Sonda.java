package io.github.consterna.modpackes.sonda;

import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import com.mojang.logging.LogUtils;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;
import net.minecraft.util.FormattedCharSequence;
import org.slf4j.Logger;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/**
 * Mide dentro del juego qué texto ve el jugador y en qué idioma. Es un mod de desarrollo: no cambia nada de lo que se
 * ve, solo escribe JSON en {@code <juego>/modpackes-sonda/}.
 *
 * <ul>
 *   <li>{@value Volcado#IDIOMA}: tras cada recarga de recursos, el mapa de idioma cargado comparado con en_us.</li>
 *   <li>{@value Volcado#TEXTOS}: todo texto que se dibuja, sin repetir y con la pantalla abierta; se escribe cada
 *       {@value #SEGUNDOS} segundos y al cerrar.</li>
 *   <li>{@value Volcado#REGISTROS}: con {@code /modpackes_sonda volcar}, los nombres de lo registrado.</li>
 * </ul>
 */
public final class Sonda {
    public static final String ID = "modpackes_sonda";
    public static final String CARPETA = "modpackes-sonda";
    static final long SEGUNDOS = 5;
    private static final Logger LOG = LogUtils.getLogger();

    private static final TextosDibujados TEXTOS = new TextosDibujados();
    private static final Disco DISCO = new Disco("modpackes-sonda", Sonda::avisar);
    private static volatile String loader = "?";
    private static volatile String minecraft = "?";
    private static volatile Map<String, String> ultimoEnUs = Map.of();
    private static volatile String idioma = "?";
    private static int recargas;
    private static boolean avisado;

    private Sonda() {
    }

    /** Lo llama el punto de entrada de cada loader al arrancar. */
    public static void iniciar(String nombreDelLoader, String versionDeMinecraft) {
        loader = nombreDelLoader;
        minecraft = versionDeMinecraft;
        DISCO.cadaPocosSegundos(Sonda::guardarTextosSiCambiaron, SEGUNDOS);
        LOG.info("ModpackES Sonda: escribe en {}/ ({} {})", CARPETA, nombreDelLoader, versionDeMinecraft);
    }

    // ---------- (c) texto dibujado: lo llama FontMixin en cada dibujo ----------

    public static void anotar(String texto) {
        try {
            TEXTOS.anotar(texto, pantallaAbierta());
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    public static void anotar(FormattedCharSequence secuencia) {
        try {
            TEXTOS.anotar(aTexto(secuencia), pantallaAbierta());
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    /** El texto de una secuencia ya formateada, sin estilos. */
    public static String aTexto(FormattedCharSequence secuencia) {
        if (secuencia == null) {
            return null;
        }
        StringBuilder sb = new StringBuilder();
        secuencia.accept((indice, estilo, codigo) -> {
            sb.appendCodePoint(codigo);
            return true;
        });
        return sb.toString();
    }

    private static String pantallaAbierta() {
        Minecraft mc = Minecraft.getInstance();
        Screen pantalla = mc == null ? null : mc.screen;
        return pantalla == null ? null : pantalla.getClass().getName();
    }

    private static void guardarTextosSiCambiaron() {
        if (TEXTOS.tomarCambio()) {
            guardarTextos();
        }
    }

    private static void guardarTextos() {
        List<TextosDibujados.Entrada> copia = TEXTOS.copia();
        long descartados = TEXTOS.descartados();
        escribir(Volcado.TEXTOS, w -> Volcado.escribirTextos(w, origen(), copia, descartados));
    }

    // ---------- (a) mapa de idioma: lo llama LanguageManagerMixin al acabar cada recarga ----------

    /**
     * @param codigo el idioma elegido
     * @param actual el mapa cargado (ya trae en_us debajo, como lo arma el juego)
     * @param enUs   el mapa de en_us solo
     */
    public static void alRecargarIdioma(String codigo, Map<String, String> actual, Map<String, String> enUs) {
        int recarga;
        synchronized (Sonda.class) {
            recarga = ++recargas;
        }
        idioma = codigo;
        ultimoEnUs = enUs;
        Volcado.Origen origen = origen();
        DISCO.enviar(() -> escribirYa(Volcado.IDIOMA, w -> Volcado.escribirIdioma(w, origen, recarga, actual, enUs)));
        LOG.info("ModpackES Sonda: recarga {} con {} claves en {} ({} en en_us)", recarga, actual.size(), codigo,
                enUs.size());
    }

    // ---------- (b) registros: lo llama el comando ----------

    /** {@code /modpackes_sonda volcar}, para el despachador de comandos de cliente de cualquier loader. */
    public static <S> LiteralArgumentBuilder<S> comando(VolcadorDeRegistros volcador) {
        return LiteralArgumentBuilder.<S>literal(ID).then(LiteralArgumentBuilder.<S>literal("volcar").executes(ctx -> {
            Component mensaje = volcarRegistros(volcador);
            LocalPlayer jugador = Minecraft.getInstance().player;
            if (jugador != null) {
                jugador.displayClientMessage(mensaje, false);
            }
            return 1;
        }));
    }

    /** Reúne lo registrado (en el hilo del juego) y lo escribe en el de fondo. Devuelve el mensaje para el chat. */
    public static Component volcarRegistros(VolcadorDeRegistros volcador) {
        try {
            List<Elemento> elementos = volcador.reunir(Minecraft.getInstance());
            Map<String, String> enUs = ultimoEnUs;
            Volcado.Origen origen = origen();
            escribir(Volcado.REGISTROS, w -> Volcado.escribirRegistros(w, origen, elementos, enUs));
            DISCO.enviar(Sonda::guardarTextos);
            return Component.literal("ModpackES Sonda: " + elementos.size() + " nombres y " + TEXTOS.tamano()
                    + " textos dibujados van a " + CARPETA + "/");
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
            return Component.literal("ModpackES Sonda: no pude volcar los registros: " + e);
        }
    }

    // ---------- disco ----------

    private static Volcado.Origen origen() {
        return new Volcado.Origen(loader, minecraft, idioma);
    }

    private static void escribir(String archivo, Volcado.Contenido contenido) {
        DISCO.enviar(() -> escribirYa(archivo, contenido));
    }

    /** Sincronizado: al cerrar, el gancho de salida puede escribir a la vez que el hilo de fondo. */
    private static synchronized void escribirYa(String archivo, Volcado.Contenido contenido) {
        Path destino = Minecraft.getInstance().gameDirectory.toPath().resolve(CARPETA).resolve(archivo);
        try {
            Volcado.escribirAtomico(destino, contenido);
        } catch (IOException e) {
            LOG.warn("ModpackES Sonda: no pude escribir {}", destino, e);
        }
    }

    /** Un fallo se anota una sola vez: la sonda nunca debe romper el juego ni llenar el registro. */
    static synchronized void avisar(Throwable e) {
        if (!avisado) {
            avisado = true;
            LOG.warn("ModpackES Sonda: falló una medición; sigo sin ella", e);
        }
    }
}

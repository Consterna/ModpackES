import java.io.StringReader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Lee archivos con los parsers reales que usa Minecraft y sus mods, cargados del classpath:
 * Gson (lang JSON, Patchouli, pack.mcmeta) y el SNBT de FTB Library (FTB Quests).
 *
 * Uso: java -cp <gson.jar;ftb-library.jar;client-srg.jar;clases> ValidadorTraductor json|snbt archivo...
 * Salida, una línea por archivo: OK<TAB>ruta<TAB>forma-canónica   o   ERROR<TAB>ruta<TAB>motivo
 */
public final class ValidadorTraductor {
    private ValidadorTraductor() {}

    public static void main(String[] args) {
        if (args.length < 1 || !(args[0].equals("json") || args[0].equals("snbt"))) {
            System.err.println("uso: ValidadorTraductor json|snbt archivo...");
            System.exit(2);
        }
        for (int i = 1; i < args.length; i++) {
            Path ruta = Path.of(args[i]);
            try {
                String canonico = args[0].equals("json") ? json(ruta) : snbt(ruta);
                System.out.println("OK\t" + ruta + "\t" + escapar(canonico));
            } catch (Throwable t) {
                Throwable causa = t instanceof InvocationTargetException ite && ite.getCause() != null ? ite.getCause() : t;
                System.out.println("ERROR\t" + ruta + "\t" + escapar(causa.getClass().getSimpleName() + ": " + causa.getMessage()));
            }
        }
    }

    /** JSON estricto con Gson: sin comentarios, sin comas finales y sin basura tras el documento. */
    private static String json(Path ruta) throws Exception {
        String texto = Files.readString(ruta, StandardCharsets.UTF_8);
        Class<?> claseLector = Class.forName("com.google.gson.stream.JsonReader");
        Object lector = claseLector.getConstructor(java.io.Reader.class).newInstance(new StringReader(texto));
        claseLector.getMethod("setLenient", boolean.class).invoke(lector, false);
        Object adaptador = Class.forName("com.google.gson.internal.bind.TypeAdapters").getField("JSON_ELEMENT").get(null);
        Method leer = Class.forName("com.google.gson.TypeAdapter").getMethod("read", claseLector);
        Object elemento = leer.invoke(adaptador, lector);
        Object fin = claseLector.getMethod("peek").invoke(lector);
        if (!fin.toString().equals("END_DOCUMENT")) {
            throw new IllegalStateException("contenido extra después del JSON: " + fin);
        }
        return elemento.toString();
    }

    /** SNBT con el mismo parser que usa FTB Quests dentro del juego. */
    private static String snbt(Path ruta) throws Exception {
        List<String> lineas = Files.readAllLines(ruta, StandardCharsets.UTF_8);
        Class<?> snbt = Class.forName("dev.ftb.mods.ftblibrary.snbt.SNBT");
        Object etiqueta = snbt.getMethod("readLines", List.class).invoke(null, lineas);
        if (etiqueta == null) {
            throw new IllegalStateException("FTB Library no pudo leer el archivo");
        }
        Class<?> compuesta = Class.forName("net.minecraft.nbt.CompoundTag");
        @SuppressWarnings("unchecked")
        List<String> salida = (List<String>) snbt.getMethod("writeLines", compuesta).invoke(null, etiqueta);
        return String.join("\n", salida);
    }

    private static String escapar(String s) {
        return s == null ? "" : s.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n");
    }
}

package io.github.consterna.modpackes.sonda;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VolcadoTest {
    private static final Volcado.Origen ORIGEN = new Volcado.Origen("forge", "1.20.1", "es_es");

    private static Map<String, String> mapa(String... pares) {
        Map<String, String> m = new HashMap<>();
        for (int i = 0; i < pares.length; i += 2) {
            m.put(pares[i], pares[i + 1]);
        }
        return m;
    }

    private static JsonObject leer(Volcado.Contenido contenido) throws IOException {
        StringWriter w = new StringWriter();
        contenido.escribir(w);
        return JsonParser.parseString(w.toString()).getAsJsonObject();
    }

    @Test
    void cabeceraComun() throws IOException {
        JsonObject o = leer(w -> Volcado.escribirTextos(w, ORIGEN, List.of(), 0));
        assertEquals(1, o.get("formato").getAsInt());
        assertEquals("forge", o.get("loader").getAsString());
        assertEquals("1.20.1", o.get("minecraft").getAsString());
        assertEquals("es_es", o.get("idioma").getAsString());
    }

    @Test
    void idiomaMarcaLoQueSigueEnIngles() throws IOException {
        Map<String, String> actual = mapa("b.traducida", "Piedra", "a.igual", "Stone", "c.solo_actual", "Hola");
        Map<String, String> enUs = mapa("b.traducida", "Stone", "a.igual", "Stone");
        JsonObject o = leer(w -> Volcado.escribirIdioma(w, ORIGEN, 3, actual, enUs));
        assertEquals(3, o.get("recarga").getAsInt());
        assertEquals(3, o.get("total").getAsInt());
        assertEquals(1, o.get("iguales_a_en_us").getAsInt());
        JsonArray claves = o.getAsJsonArray("claves");
        assertEquals("a.igual", claves.get(0).getAsJsonObject().get("clave").getAsString()); // ordenadas
        assertTrue(claves.get(0).getAsJsonObject().get("igual").getAsBoolean());
        JsonObject traducida = claves.get(1).getAsJsonObject();
        assertEquals("Piedra", traducida.get("valor").getAsString());
        assertEquals("Stone", traducida.get("en_us").getAsString());
        assertFalse(traducida.get("igual").getAsBoolean());
        JsonObject soloActual = claves.get(2).getAsJsonObject();
        assertTrue(soloActual.get("en_us").isJsonNull());
        assertFalse(soloActual.get("igual").getAsBoolean());
    }

    @Test
    void textosConSusPantallas() throws IOException {
        TextosDibujados t = new TextosDibujados();
        t.anotar("Done", "B");
        t.anotar("Done", "A");
        t.anotar("<Hola & \"adiós\">", null);
        JsonObject o = leer(w -> Volcado.escribirTextos(w, ORIGEN, t.copia(), 7));
        assertEquals(2, o.get("total").getAsInt());
        assertEquals(7, o.get("descartados_por_tope").getAsLong());
        JsonArray textos = o.getAsJsonArray("textos");
        assertEquals("<Hola & \"adiós\">", textos.get(0).getAsJsonObject().get("texto").getAsString());
        JsonArray pantallas = textos.get(1).getAsJsonObject().getAsJsonArray("pantallas");
        assertEquals("A", pantallas.get(0).getAsString());
        assertEquals("B", pantallas.get(1).getAsString());
    }

    @Test
    void noEscapaComoHtml() throws IOException {
        StringWriter w = new StringWriter();
        Volcado.escribirTextos(w, ORIGEN, List.of(new TextosDibujados.Entrada("<a> & ñ", List.of("X"))), 0);
        assertTrue(w.toString().contains("\"<a> & ñ\""), w.toString());
    }

    @Test
    void registrosConTooltipYComparacionConIngles() throws IOException {
        List<Elemento> elementos = List.of(
                new Elemento("objeto", "minecraft:stone", "block.minecraft.stone", "Piedra", true,
                        List.of("Piedra", "Línea 2")),
                new Elemento("objeto", "mod:cosa", "item.mod.cosa", "item.mod.cosa", false, List.of()),
                new Elemento("bioma", "minecraft:plains", "biome.minecraft.plains", "Plains", true, null),
                new Elemento("atajo", "key.mod.raro", null, "Raro", true, null));
        Map<String, String> enUs = mapa("block.minecraft.stone", "Stone", "biome.minecraft.plains", "Plains");
        JsonObject o = leer(w -> Volcado.escribirRegistros(w, ORIGEN, elementos, enUs));
        assertEquals(4, o.get("total").getAsInt());
        JsonArray lista = o.getAsJsonArray("elementos");
        JsonObject piedra = lista.get(0).getAsJsonObject();
        assertEquals("Stone", piedra.get("en_us").getAsString());
        assertFalse(piedra.get("igual").getAsBoolean());
        assertEquals("Línea 2", piedra.getAsJsonArray("tooltip").get(1).getAsString());
        JsonObject cosa = lista.get(1).getAsJsonObject();
        assertFalse(cosa.get("existe").getAsBoolean());
        assertTrue(cosa.get("igual").isJsonNull()); // en_us no la tiene
        assertEquals(0, cosa.getAsJsonArray("tooltip").size());
        JsonObject bioma = lista.get(2).getAsJsonObject();
        assertTrue(bioma.get("igual").getAsBoolean());
        assertFalse(bioma.has("tooltip"));
        JsonObject atajo = lista.get(3).getAsJsonObject();
        assertTrue(atajo.get("clave").isJsonNull());
        assertTrue(atajo.get("igual").isJsonNull());
    }

    @Test
    void escribirAtomicoReemplazaYNoDejaTemporal(@TempDir Path dir) throws IOException {
        Path destino = dir.resolve("sub").resolve("a.json");
        Volcado.escribirAtomico(destino, w -> w.write("uno"));
        Volcado.escribirAtomico(destino, w -> w.write("dos ñ"));
        assertEquals("dos ñ", Files.readString(destino, StandardCharsets.UTF_8));
        assertEquals(List.of("a.json"), Arrays.stream(dir.resolve("sub").toFile().list()).toList());
    }

    @Test
    void unFalloAlEscribirNoTocaElArchivoAnterior(@TempDir Path dir) throws IOException {
        Path destino = dir.resolve("a.json");
        Volcado.escribirAtomico(destino, w -> w.write("bueno"));
        assertThrows(IOException.class, () -> Volcado.escribirAtomico(destino, w -> {
            w.write("a medias");
            throw new IOException("falla");
        }));
        assertEquals("bueno", Files.readString(destino, StandardCharsets.UTF_8));
    }
}

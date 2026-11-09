package io.github.consterna.modpackes;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.widget.Widget;
import net.minecraft.client.resources.ReloadListener;
import net.minecraft.profiler.IProfiler;
import net.minecraft.resources.IReloadableResourceManager;
import net.minecraft.resources.IResource;
import net.minecraft.resources.IResourceManager;
import net.minecraft.util.ResourceLocation;
import net.minecraft.util.text.ITextComponent;
import net.minecraftforge.client.event.ClientChatReceivedEvent;
import net.minecraftforge.client.event.GuiScreenEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.entity.player.ItemTooltipEvent;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;

/** Lo que solo existe en el cliente: engancha los eventos y carga la tabla. Java 8, como Minecraft 1.16.5. */
final class Cliente {
    private static final Logger LOG = LogManager.getLogger(ModpackESRuntime.ID);

    private static volatile Tabla tabla = Tabla.VACIA;
    private static boolean avisado;

    private Cliente() {
    }

    /**
     * Se llama al construir el mod, antes de la primera recarga de recursos. En 1.16.5 no hay un evento para registrar
     * recargas del cliente y {@code FMLClientSetupEvent} se dispara durante esa primera recarga: un listener
     * registrado ahí queda fuera y la tabla no se cargaría hasta que el jugador recargara los recursos.
     */
    static void iniciar() {
        IResourceManager gestor = Minecraft.getInstance().getResourceManager();
        if (gestor instanceof IReloadableResourceManager) {
            ((IReloadableResourceManager) gestor).registerReloadListener(new Cargador());
        }
        MinecraftForge.EVENT_BUS.addListener(Cliente::alRecibirChat);
        MinecraftForge.EVENT_BUS.addListener(Cliente::alCrearTooltip);
        MinecraftForge.EVENT_BUS.addListener(Cliente::alIniciarPantalla);
    }

    private static void alRecibirChat(ClientChatReceivedEvent evento) {
        try {
            ITextComponent nuevo = Reescritor.reescribir(evento.getMessage(), tabla);
            if (nuevo != null) {
                evento.setMessage(nuevo);
            }
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    private static void alCrearTooltip(ItemTooltipEvent evento) {
        try {
            Tabla actual = tabla;
            if (actual.vacia()) {
                return;
            }
            List<ITextComponent> lineas = evento.getToolTip();
            for (int i = 0; i < lineas.size(); i++) {
                ITextComponent nuevo = Reescritor.reescribir(lineas.get(i), actual);
                if (nuevo != null) {
                    lineas.set(i, nuevo);
                }
            }
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    private static void alIniciarPantalla(GuiScreenEvent.InitGuiEvent.Post evento) {
        try {
            Tabla actual = tabla;
            if (actual.vacia()) {
                return;
            }
            for (Widget widget : evento.getWidgetList()) {
                Reescritor.reescribirMensaje(widget, actual);
            }
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    /** Un fallo se anota una sola vez: el juego nunca debe romperse ni llenar el registro por esto. */
    private static synchronized void avisar(Throwable e) {
        if (!avisado) {
            avisado = true;
            LOG.warn("ModpackES Runtime: no pude cambiar un texto; se deja el original", e);
        }
    }

    /** Variantes de la tabla a probar, en orden. Vacío si el juego no está en español. */
    static List<String> variantes(String codigoDeIdioma) {
        if (codigoDeIdioma == null || !codigoDeIdioma.toLowerCase(Locale.ROOT).startsWith("es_")) {
            return Collections.emptyList();
        }
        String codigo = codigoDeIdioma.toLowerCase(Locale.ROOT);
        return new ArrayList<>(new LinkedHashSet<>(Arrays.asList(codigo, "es_mx", "es_es")));
    }

    private static final class Cargador extends ReloadListener<Tabla> {
        @Override
        protected Tabla prepare(IResourceManager recursos, IProfiler perfil) {
            Tabla total = Tabla.VACIA;
            for (String variante : variantes(Minecraft.getInstance().options.languageCode)) {
                ResourceLocation ruta = new ResourceLocation(ModpackESRuntime.ID, "textos/" + variante + ".json");
                if (!recursos.hasResource(ruta)) {
                    continue;
                }
                try {
                    for (IResource recurso : recursos.getResources(ruta)) { // de menor a mayor prioridad
                        try (IResource r = recurso;
                             Reader lector = new InputStreamReader(r.getInputStream(), StandardCharsets.UTF_8)) {
                            total = total.combinar(Tabla.leer(lector));
                        } catch (IOException | RuntimeException e) {
                            LOG.warn("ModpackES Runtime: no pude leer {} de {}", ruta, recurso.getSourceName(), e);
                        }
                    }
                } catch (IOException | RuntimeException e) {
                    LOG.warn("ModpackES Runtime: no pude listar {}", ruta, e);
                }
                if (!total.vacia()) {
                    break;
                }
            }
            return total;
        }

        @Override
        protected void apply(Tabla nueva, IResourceManager recursos, IProfiler perfil) {
            tabla = nueva;
            LOG.info("ModpackES Runtime: {} textos en la tabla ({} plantillas)", nueva.tamano(), nueva.plantillas());
        }
    }
}

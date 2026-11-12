package io.github.consterna.modpackes;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiButton;
import net.minecraft.client.resources.IResource;
import net.minecraft.client.resources.IReloadableResourceManager;
import net.minecraft.client.resources.IResourceManager;
import net.minecraft.client.resources.IResourceManagerReloadListener;
import net.minecraft.util.ResourceLocation;
import net.minecraft.util.text.ITextComponent;
import net.minecraftforge.client.event.ClientChatReceivedEvent;
import net.minecraftforge.client.event.GuiScreenEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.entity.player.ItemTooltipEvent;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
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

/** Lo que solo existe en el cliente: engancha los eventos y carga la tabla. Java 8, como Minecraft 1.12.2. */
final class Cliente {
    private static final Logger LOG = LogManager.getLogger(ModpackESRuntime.ID);

    private static volatile Tabla tabla = Tabla.VACIA;
    private static boolean avisado;

    private Cliente() {
    }

    /**
     * Se llama en la fase de inicialización del mod, antes de la recarga de recursos con que el juego termina de
     * arrancar. {@code registerReloadListener} carga la tabla al registrarla y otra vez en cada recarga (F3+T, cambiar
     * de idioma o de resource pack).
     */
    static void iniciar() {
        IResourceManager gestor = Minecraft.getMinecraft().getResourceManager();
        if (gestor instanceof IReloadableResourceManager) {
            ((IReloadableResourceManager) gestor).registerReloadListener(new Cargador());
        }
        MinecraftForge.EVENT_BUS.register(new Cliente());
    }

    @SubscribeEvent
    public void alRecibirChat(ClientChatReceivedEvent evento) {
        try {
            ITextComponent nuevo = Reescritor.reescribir(evento.getMessage(), tabla);
            if (nuevo != null) {
                evento.setMessage(nuevo);
            }
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    @SubscribeEvent
    public void alCrearTooltip(ItemTooltipEvent evento) {
        try {
            Tabla actual = tabla;
            if (actual.vacia()) {
                return;
            }
            List<String> lineas = evento.getToolTip();
            for (int i = 0; i < lineas.size(); i++) {
                String nueva = Reescritor.reescribirLinea(lineas.get(i), actual);
                if (nueva != null) {
                    lineas.set(i, nueva);
                }
            }
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    @SubscribeEvent
    public void alIniciarPantalla(GuiScreenEvent.InitGuiEvent.Post evento) {
        try {
            Tabla actual = tabla;
            if (actual.vacia()) {
                return;
            }
            for (GuiButton boton : evento.getButtonList()) {
                Reescritor.reescribirBoton(boton, actual);
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

    private static final class Cargador implements IResourceManagerReloadListener {
        @Override
        public void onResourceManagerReload(IResourceManager recursos) {
            Tabla total = Tabla.VACIA;
            for (String variante : variantes(Minecraft.getMinecraft().gameSettings.language)) {
                ResourceLocation ruta = new ResourceLocation(ModpackESRuntime.ID, "textos/" + variante + ".json");
                try {
                    for (IResource recurso : recursos.getAllResources(ruta)) { // de menor a mayor prioridad
                        try (IResource r = recurso;
                             Reader lector = new InputStreamReader(r.getInputStream(), StandardCharsets.UTF_8)) {
                            total = total.combinar(Tabla.leer(lector));
                        } catch (IOException | RuntimeException e) {
                            LOG.warn("ModpackES Runtime: no pude leer {} de {}", ruta, recurso.getResourcePackName(), e);
                        }
                    }
                } catch (IOException | RuntimeException e) {
                    LOG.debug("ModpackES Runtime: no hay {} (o no pude listarlo)", ruta, e);
                }
                if (!total.vacia()) {
                    break;
                }
            }
            tabla = total;
            LOG.info("ModpackES Runtime: {} textos en la tabla ({} plantillas)", total.tamano(), total.plantillas());
        }
    }
}

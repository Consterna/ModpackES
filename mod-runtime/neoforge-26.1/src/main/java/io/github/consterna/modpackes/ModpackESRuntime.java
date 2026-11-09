package io.github.consterna.modpackes;

import com.mojang.logging.LogUtils;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraft.server.packs.resources.SimplePreparableReloadListener;
import net.minecraft.util.profiling.ProfilerFiller;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.client.event.ClientChatReceivedEvent;
import net.neoforged.neoforge.client.event.AddClientReloadListenersEvent;
import net.neoforged.neoforge.client.event.RenderTooltipEvent;
import net.neoforged.neoforge.client.event.ScreenEvent;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.entity.player.ItemTooltipEvent;
import org.slf4j.Logger;

import java.io.IOException;
import java.io.Reader;
import java.util.List;

/**
 * Muestra en español el texto que otros mods escriben en su código. Solo cambia mensajes de chat, de la barra de
 * acción y tooltips cuyo texto sea exactamente uno de la tabla {@code assets/modpackes_runtime/textos/<variante>.json}
 * que genera ModpackES (o encaje en una de sus plantillas con {@code %s} o {@code %d}). Si el juego no está en una
 * variante de español, no hace nada.
 *
 * <p>También cambia el texto de los botones de una pantalla al abrirla y los tooltips que no son de objetos. El
 * texto que una pantalla dibuja directamente no pasa por ningún evento y no se toca.
 */
@Mod(value = ModpackESRuntime.ID, dist = Dist.CLIENT)
public final class ModpackESRuntime {
    public static final String ID = "modpackes_runtime";
    private static final Logger LOG = LogUtils.getLogger();

    private static volatile Tabla tabla = Tabla.VACIA;
    private static boolean avisado;

    public ModpackESRuntime(IEventBus busDelMod) {
        busDelMod.addListener(ModpackESRuntime::alRegistrarRecargas);
        NeoForge.EVENT_BUS.addListener(ModpackESRuntime::alRecibirChat);
        NeoForge.EVENT_BUS.addListener(ModpackESRuntime::alCrearTooltip);
        NeoForge.EVENT_BUS.addListener(ModpackESRuntime::alReunirTooltip);
        NeoForge.EVENT_BUS.addListener(ModpackESRuntime::alIniciarPantalla);
    }

    private static void alRegistrarRecargas(AddClientReloadListenersEvent evento) {
        evento.addListener(Identifier.fromNamespaceAndPath(ID, "textos"), new Cargador());
    }

    private static void alRecibirChat(ClientChatReceivedEvent evento) {
        try {
            Component nuevo = Reescritor.reescribir(evento.getMessage(), tabla);
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
            List<Component> lineas = evento.getToolTip();
            for (int i = 0; i < lineas.size(); i++) {
                Component nuevo = Reescritor.reescribir(lineas.get(i), actual);
                if (nuevo != null) {
                    lineas.set(i, nuevo);
                }
            }
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    private static void alReunirTooltip(RenderTooltipEvent.GatherComponents evento) {
        try {
            Reescritor.reescribirElementos(evento.getTooltipElements(), tabla);
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
        }
    }

    private static void alIniciarPantalla(ScreenEvent.Init.Post evento) {
        try {
            Tabla actual = tabla;
            if (actual.vacia()) {
                return;
            }
            for (GuiEventListener hijo : evento.getListenersList()) {
                if (hijo instanceof AbstractWidget widget) {
                    Reescritor.reescribirMensaje(widget, actual);
                }
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
        if (codigoDeIdioma == null || !codigoDeIdioma.toLowerCase().startsWith("es_")) {
            return List.of();
        }
        String codigo = codigoDeIdioma.toLowerCase();
        return List.of(codigo, "es_mx", "es_es").stream().distinct().toList();
    }

    private static final class Cargador extends SimplePreparableReloadListener<Tabla> {
        @Override
        protected Tabla prepare(ResourceManager recursos, ProfilerFiller perfil) {
            Tabla total = Tabla.VACIA;
            for (String variante : variantes(Minecraft.getInstance().options.languageCode)) {
                Identifier ruta = Identifier.fromNamespaceAndPath(ID, "textos/" + variante + ".json");
                for (Resource recurso : recursos.getResourceStack(ruta)) { // de menor a mayor prioridad
                    try (Reader lector = recurso.openAsReader()) {
                        total = total.combinar(Tabla.leer(lector));
                    } catch (IOException | RuntimeException e) {
                        LOG.warn("ModpackES Runtime: no pude leer {} de {}", ruta, recurso.sourcePackId(), e);
                    }
                }
                if (!total.vacia()) {
                    break;
                }
            }
            return total;
        }

        @Override
        protected void apply(Tabla nueva, ResourceManager recursos, ProfilerFiller perfil) {
            tabla = nueva;
            LOG.info("ModpackES Runtime: {} textos en la tabla ({} plantillas)", nueva.tamano(), nueva.plantillas());
        }
    }
}

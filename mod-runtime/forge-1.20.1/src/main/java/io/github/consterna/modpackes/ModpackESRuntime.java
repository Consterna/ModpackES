package io.github.consterna.modpackes;

import com.mojang.logging.LogUtils;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraft.server.packs.resources.SimplePreparableReloadListener;
import net.minecraft.util.profiling.ProfilerFiller;
import net.minecraftforge.client.event.ClientChatReceivedEvent;
import net.minecraftforge.client.event.RegisterClientReloadListenersEvent;
import net.minecraftforge.client.event.RenderTooltipEvent;
import net.minecraftforge.client.event.ScreenEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.entity.player.ItemTooltipEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;
import org.slf4j.Logger;

import java.io.IOException;
import java.io.Reader;
import java.util.List;

/**
 * Muestra en español el texto que otros mods escriben en su código. Solo cambia mensajes de chat, de la barra de
 * acción y tooltips cuyo texto sea exactamente uno de la tabla {@code assets/modpackes_runtime/textos/<variante>.json}
 * que genera ModpackES. Si el juego no está en una variante de español, no hace nada.
 *
 * <p>También cambia el texto de los botones de una pantalla al abrirla y los tooltips que no son de objetos. El
 * texto que una pantalla dibuja directamente no pasa por ningún evento y no se toca.
 */
@Mod(ModpackESRuntime.ID)
public final class ModpackESRuntime {
    public static final String ID = "modpackes_runtime";
    private static final Logger LOG = LogUtils.getLogger();

    private static volatile Tabla tabla = Tabla.VACIA;
    private static boolean avisado;

    public ModpackESRuntime() {
        FMLJavaModLoadingContext.get().getModEventBus().addListener(ModpackESRuntime::alRegistrarRecargas);
        MinecraftForge.EVENT_BUS.addListener(ModpackESRuntime::alRecibirChat);
        MinecraftForge.EVENT_BUS.addListener(ModpackESRuntime::alCrearTooltip);
        MinecraftForge.EVENT_BUS.addListener(ModpackESRuntime::alReunirTooltip);
        MinecraftForge.EVENT_BUS.addListener(ModpackESRuntime::alIniciarPantalla);
    }

    private static void alRegistrarRecargas(RegisterClientReloadListenersEvent evento) {
        evento.registerReloadListener(new Cargador());
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
                ResourceLocation ruta = new ResourceLocation(ID, "textos/" + variante + ".json");
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
            LOG.info("ModpackES Runtime: {} textos en la tabla", nueva.tamano());
        }
    }
}

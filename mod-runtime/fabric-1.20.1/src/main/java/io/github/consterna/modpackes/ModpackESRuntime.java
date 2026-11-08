package io.github.consterna.modpackes;

import com.mojang.logging.LogUtils;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.item.v1.ItemTooltipCallback;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.fabric.api.client.screen.v1.ScreenEvents;
import net.fabricmc.fabric.api.client.screen.v1.Screens;
import net.fabricmc.fabric.api.resource.ResourceManagerHelper;
import net.fabricmc.fabric.api.resource.SimpleSynchronousResourceReloadListener;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.PackType;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.server.packs.resources.ResourceManager;
import org.slf4j.Logger;

import java.io.IOException;
import java.io.Reader;
import java.util.List;

/**
 * Muestra en español el texto que otros mods escriben en su código. Solo cambia mensajes del juego (los de
 * {@code tellraw}, los de los mods y la barra de acción) y tooltips cuyo texto sea exactamente uno de la tabla
 * {@code assets/modpackes_runtime/textos/<variante>.json} que genera ModpackES (o encaje en una de sus plantillas con
 * {@code %s} o {@code %d}). Si el juego no está en una variante de español, no hace nada.
 *
 * <p>También cambia el texto de los botones de una pantalla al abrirla. Fabric API no tiene evento para los
 * tooltips que no son de objetos ni para el texto que una pantalla dibuja directamente: esos no se tocan.
 *
 * <p>El chat de otros jugadores no se toca: Fabric API no permite modificarlo, y no hace falta.
 */
public final class ModpackESRuntime implements ClientModInitializer {
    public static final String ID = "modpackes_runtime";
    private static final Logger LOG = LogUtils.getLogger();

    private static volatile Tabla tabla = Tabla.VACIA;
    private static boolean avisado;

    @Override
    public void onInitializeClient() {
        ResourceManagerHelper.get(PackType.CLIENT_RESOURCES).registerReloadListener(new Cargador());
        ClientReceiveMessageEvents.MODIFY_GAME.register(ModpackESRuntime::alRecibirMensaje);
        ItemTooltipCallback.EVENT.register((pila, contexto, lineas) -> alCrearTooltip(lineas));
        ScreenEvents.AFTER_INIT.register((cliente, pantalla, ancho, alto) -> alIniciarPantalla(pantalla));
    }

    private static Component alRecibirMensaje(Component mensaje, boolean barraDeAccion) {
        try {
            Component nuevo = Reescritor.reescribir(mensaje, tabla);
            return nuevo != null ? nuevo : mensaje;
        } catch (RuntimeException | LinkageError e) {
            avisar(e);
            return mensaje;
        }
    }

    private static void alCrearTooltip(List<Component> lineas) {
        try {
            Tabla actual = tabla;
            if (actual.vacia()) {
                return;
            }
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

    private static void alIniciarPantalla(Screen pantalla) {
        try {
            Tabla actual = tabla;
            if (actual.vacia()) {
                return;
            }
            for (AbstractWidget widget : Screens.getButtons(pantalla)) {
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
        if (codigoDeIdioma == null || !codigoDeIdioma.toLowerCase().startsWith("es_")) {
            return List.of();
        }
        String codigo = codigoDeIdioma.toLowerCase();
        return List.of(codigo, "es_mx", "es_es").stream().distinct().toList();
    }

    private static final class Cargador implements SimpleSynchronousResourceReloadListener {
        @Override
        public ResourceLocation getFabricId() {
            return new ResourceLocation(ID, "textos");
        }

        @Override
        public void onResourceManagerReload(ResourceManager recursos) {
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
            tabla = total;
            LOG.info("ModpackES Runtime: {} textos en la tabla ({} plantillas)", total.tamano(), total.plantillas());
        }
    }
}

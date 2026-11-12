package io.github.consterna.modpackes;

import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.event.FMLInitializationEvent;

/**
 * Muestra en español el texto que otros mods escriben en su código. Solo cambia mensajes de chat, tooltips de
 * objetos y el texto de los botones de una pantalla al abrirla, cuyo texto sea exactamente uno de la tabla
 * {@code assets/modpackes_runtime/textos/<variante>.json} que genera ModpackES (o encaje en una de sus plantillas
 * con {@code %s} o {@code %d}). Si el juego no está en una variante de español, no hace nada.
 *
 * <p>Esta clase solo decide cuándo arrancar: todo lo del cliente está en {@link Cliente}, para que un servidor
 * dedicado no cargue clases que no tiene ({@code clientSideOnly} ya impide que lo cargue). Minecraft 1.12.2 no tiene
 * tooltips por elementos, así que los tooltips que no son de objetos no se tocan.
 */
@Mod(
        modid = ModpackESRuntime.ID,
        name = "ModpackES Runtime",
        version = "0.1.0",
        clientSideOnly = true,
        acceptedMinecraftVersions = "[1.12.2]")
public final class ModpackESRuntime {
    public static final String ID = "modpackes_runtime";

    @Mod.EventHandler
    public void iniciar(FMLInitializationEvent evento) {
        Cliente.iniciar();
    }
}

package io.github.consterna.modpackes;

import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.fml.DistExecutor;
import net.minecraftforge.fml.ExtensionPoint;
import net.minecraftforge.fml.ModLoadingContext;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.network.FMLNetworkConstants;
import org.apache.commons.lang3.tuple.Pair;

/**
 * Muestra en español el texto que otros mods escriben en su código. Solo cambia mensajes de chat y tooltips de
 * objetos, y el texto de los botones de una pantalla al abrirla, cuyo texto sea exactamente uno de la tabla
 * {@code assets/modpackes_runtime/textos/<variante>.json} que genera ModpackES (o encaje en una de sus plantillas
 * con {@code %s} o {@code %d}). Si el juego no está en una variante de español, no hace nada.
 *
 * <p>Esta clase solo decide dónde se carga: todo lo del cliente está en {@link Cliente}, para que un servidor
 * dedicado no cargue clases que no tiene. Minecraft 1.16.5 no tiene tooltips por elementos, así que los
 * tooltips que no son de objetos no se tocan.
 */
@Mod(ModpackESRuntime.ID)
public final class ModpackESRuntime {
    public static final String ID = "modpackes_runtime";

    public ModpackESRuntime() {
        // Que un servidor sin el mod (o un cliente sin él en un servidor) no marque error por esto
        ModLoadingContext.get().registerExtensionPoint(
                ExtensionPoint.DISPLAYTEST,
                () -> Pair.of(() -> FMLNetworkConstants.IGNORESERVERONLY, (version, remoto) -> true));
        DistExecutor.safeRunWhenOn(Dist.CLIENT, () -> Cliente::iniciar);
    }
}

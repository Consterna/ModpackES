package io.github.consterna.modpackes.sonda;

import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.item.enchantment.Enchantment;

import java.util.List;
import java.util.function.Consumer;

/** Minecraft 1.20.1 (Forge y Fabric): tooltip con el jugador y encantamientos en un registro fijo. */
public final class Volcador1201 extends VolcadorDeRegistros {
    @Override
    protected List<Component> tooltip(Minecraft mc, ItemStack pila) {
        return pila.getTooltipLines(mc.player, TooltipFlag.NORMAL);
    }

    @Override
    protected void encantamientos(Minecraft mc, Consumer<Elemento> salida) {
        for (Enchantment e : BuiltInRegistries.ENCHANTMENT) {
            String clave = e.getDescriptionId();
            salida.accept(elemento("encantamiento", id(BuiltInRegistries.ENCHANTMENT, e), clave, traducir(clave),
                    null));
        }
    }
}

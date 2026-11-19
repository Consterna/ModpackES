package io.github.consterna.modpackes.sonda;

import net.minecraft.client.Minecraft;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.contents.TranslatableContents;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.item.enchantment.Enchantment;

import java.util.List;
import java.util.function.Consumer;

/**
 * Minecraft 1.21.1: el tooltip pide un {@code Item.TooltipContext} y los encantamientos vienen con los datos del mundo
 * (su nombre es un {@code Component}, de ordinario traducible).
 */
public final class Volcador1211 extends VolcadorDeRegistros {
    @Override
    protected List<Component> tooltip(Minecraft mc, ItemStack pila) {
        Item.TooltipContext contexto = mc.level == null ? Item.TooltipContext.EMPTY : Item.TooltipContext.of(mc.level);
        return pila.getTooltipLines(contexto, mc.player, TooltipFlag.NORMAL);
    }

    @Override
    protected void encantamientos(Minecraft mc, Consumer<Elemento> salida) {
        if (mc.level == null) {
            return;
        }
        Registry<Enchantment> registro = mc.level.registryAccess().registryOrThrow(Registries.ENCHANTMENT);
        for (Enchantment e : registro) {
            Component nombre = e.description();
            String clave = nombre.getContents() instanceof TranslatableContents t ? t.getKey() : null;
            salida.accept(elemento("encantamiento", id(registro, e), clave, texto(nombre), null));
        }
    }
}

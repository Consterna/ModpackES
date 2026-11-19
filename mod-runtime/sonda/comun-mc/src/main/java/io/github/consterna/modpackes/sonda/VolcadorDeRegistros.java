package io.github.consterna.modpackes.sonda;

import net.minecraft.Util;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.locale.Language;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

/**
 * Reúne los nombres de lo registrado: objetos (con su tooltip), bloques, entidades, efectos, encantamientos, biomas y
 * atajos de teclado. Lo que cambia entre versiones (cómo se pide un tooltip y de dónde salen los encantamientos) lo pone
 * cada proyecto.
 */
public abstract class VolcadorDeRegistros {
    /** Las líneas del tooltip sin modo avanzado. */
    protected abstract List<Component> tooltip(Minecraft mc, ItemStack pila);

    /** Los encantamientos: en 1.20.1 son un registro fijo; desde 1.21 vienen con los datos del mundo. */
    protected abstract void encantamientos(Minecraft mc, Consumer<Elemento> salida);

    public final List<Elemento> reunir(Minecraft mc) {
        List<Elemento> salida = new ArrayList<>();
        for (Item item : BuiltInRegistries.ITEM) {
            ItemStack pila = new ItemStack(item);
            List<String> lineas = new ArrayList<>();
            try {
                for (Component linea : tooltip(mc, pila)) {
                    lineas.add(linea.getString());
                }
            } catch (RuntimeException | LinkageError e) {
                lineas.add("!! el tooltip falló: " + e); // un objeto roto no corta el volcado
            }
            salida.add(elemento("objeto", id(BuiltInRegistries.ITEM, item), item.getDescriptionId(),
                    texto(pila.getHoverName()), lineas));
        }
        for (Block bloque : BuiltInRegistries.BLOCK) {
            salida.add(elemento("bloque", id(BuiltInRegistries.BLOCK, bloque), bloque.getDescriptionId(),
                    texto(bloque.getName()), null));
        }
        for (EntityType<?> tipo : BuiltInRegistries.ENTITY_TYPE) {
            salida.add(elemento("entidad", id(BuiltInRegistries.ENTITY_TYPE, tipo), tipo.getDescriptionId(),
                    texto(tipo.getDescription()), null));
        }
        for (MobEffect efecto : BuiltInRegistries.MOB_EFFECT) {
            salida.add(elemento("efecto", id(BuiltInRegistries.MOB_EFFECT, efecto), efecto.getDescriptionId(),
                    texto(efecto.getDisplayName()), null));
        }
        encantamientos(mc, salida::add);
        if (mc.level != null) {
            for (ResourceLocation bioma : mc.level.registryAccess().registryOrThrow(Registries.BIOME).keySet()) {
                String clave = Util.makeDescriptionId("biome", bioma);
                salida.add(elemento("bioma", bioma.toString(), clave, traducir(clave), null));
            }
        }
        Set<String> categorias = new LinkedHashSet<>();
        for (KeyMapping atajo : mc.options.keyMappings) {
            salida.add(elemento("atajo", atajo.getName(), atajo.getName(), traducir(atajo.getName()), null));
            categorias.add(atajo.getCategory());
        }
        for (String categoria : categorias) {
            salida.add(elemento("categoria_de_atajo", categoria, categoria, traducir(categoria), null));
        }
        return salida;
    }

    protected static Elemento elemento(String categoria, String id, String clave, String valor, List<String> tooltip) {
        boolean existe = clave != null && Language.getInstance().has(clave);
        return new Elemento(categoria, id, clave, valor, existe, tooltip);
    }

    protected static <T> String id(Registry<T> registro, T valor) {
        ResourceLocation id = registro.getKey(valor);
        return id == null ? "?" : id.toString();
    }

    protected static String traducir(String clave) {
        return Component.translatable(clave).getString();
    }

    protected static String texto(Component c) {
        return c == null ? null : c.getString();
    }
}

package io.github.consterna.modpackes.sonda.mixin;

import net.minecraft.client.resources.language.ClientLanguage;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.Map;

/** Lee el mapa «clave → texto» de un idioma cargado, que el juego guarda en un campo privado. */
@Mixin(ClientLanguage.class)
public interface ClientLanguageAccessor {
    @Accessor("storage")
    Map<String, String> modpackesSonda$mapa();
}

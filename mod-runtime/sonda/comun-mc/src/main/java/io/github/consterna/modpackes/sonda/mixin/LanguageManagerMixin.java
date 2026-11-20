package io.github.consterna.modpackes.sonda.mixin;

import io.github.consterna.modpackes.sonda.Sonda;
import net.minecraft.client.resources.language.ClientLanguage;
import net.minecraft.client.resources.language.LanguageManager;
import net.minecraft.locale.Language;
import net.minecraft.server.packs.resources.ResourceManager;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Al acabar cada recarga de recursos, {@code LanguageManager.onResourceManagerReload} ya dejó el idioma nuevo en
 * {@code Language.getInstance()}: ahí se copia, con lo que hayan añadido los mods mientras el juego corre (KubeJS,
 * ARRP/BRRP, Moonlight), y se carga aparte en_us para comparar.
 */
@Mixin(LanguageManager.class)
public abstract class LanguageManagerMixin {
    @Inject(method = "onResourceManagerReload(Lnet/minecraft/server/packs/resources/ResourceManager;)V",
            at = @At("TAIL"))
    private void modpackesSonda$alRecargar(ResourceManager recursos, CallbackInfo ci) {
        try {
            String codigo = ((LanguageManager) (Object) this).getSelected();
            Map<String, String> actual;
            if (Language.getInstance() instanceof ClientLanguage cargado) {
                actual = new HashMap<>(((ClientLanguageAccessor) cargado).modpackesSonda$mapa());
            } else {
                // Algún mod envolvió el idioma (pasa en Fabric): se arma como lo arma el juego, en_us debajo del
                // elegido. Se pierde solo lo que un mod agregue mientras el juego corre, y el registro lo dice.
                org.slf4j.LoggerFactory.getLogger(Sonda.class).warn(
                        "ModpackES Sonda: el idioma activo es {}, no ClientLanguage; se lee de los recursos",
                        Language.getInstance().getClass().getName());
                List<String> idiomas = "en_us".equals(codigo) ? List.of("en_us") : List.of("en_us", codigo);
                actual = new HashMap<>(((ClientLanguageAccessor) ClientLanguage.loadFrom(recursos, idiomas, false))
                        .modpackesSonda$mapa());
            }
            Map<String, String> enUs = "en_us".equals(codigo) ? actual : new HashMap<>(
                    ((ClientLanguageAccessor) ClientLanguage.loadFrom(recursos, List.of("en_us"), false))
                            .modpackesSonda$mapa());
            Sonda.alRecargarIdioma(codigo, actual, enUs);
        } catch (RuntimeException | LinkageError e) {
            org.slf4j.LoggerFactory.getLogger(Sonda.class).warn("ModpackES Sonda: no pude copiar el idioma", e);
        }
    }
}

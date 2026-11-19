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
            if (!(Language.getInstance() instanceof ClientLanguage cargado)) {
                return;
            }
            Map<String, String> actual = new HashMap<>(((ClientLanguageAccessor) cargado).modpackesSonda$mapa());
            Map<String, String> enUs = "en_us".equals(codigo) ? actual : new HashMap<>(
                    ((ClientLanguageAccessor) ClientLanguage.loadFrom(recursos, List.of("en_us"), false))
                            .modpackesSonda$mapa());
            Sonda.alRecargarIdioma(codigo, actual, enUs);
        } catch (RuntimeException | LinkageError e) {
            org.slf4j.LoggerFactory.getLogger(Sonda.class).warn("ModpackES Sonda: no pude copiar el idioma", e);
        }
    }
}

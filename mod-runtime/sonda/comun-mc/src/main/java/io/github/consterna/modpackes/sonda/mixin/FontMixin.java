package io.github.consterna.modpackes.sonda.mixin;

import io.github.consterna.modpackes.sonda.Sonda;
import net.minecraft.client.gui.Font;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.util.FormattedCharSequence;
import org.joml.Matrix4f;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Anota cada texto que dibuja la fuente. En 1.20.1 y 1.21.1 todos los {@code Font.drawInBatch} (y con ellos los
 * {@code GuiGraphics.drawString}) acaban en uno de los dos {@code drawInternal}; el texto con contorno de los carteles
 * brillantes va aparte por {@code drawInBatch8xOutline}. Solo se mira el texto: el dibujo sigue igual.
 */
@Mixin(Font.class)
public abstract class FontMixin {
    @Inject(
            method = "drawInternal(Ljava/lang/String;FFIZLorg/joml/Matrix4f;"
                    + "Lnet/minecraft/client/renderer/MultiBufferSource;Lnet/minecraft/client/gui/Font$DisplayMode;IIZ)I",
            at = @At("HEAD"))
    private void modpackesSonda$cadena(String texto, float x, float y, int color, boolean sombra, Matrix4f matriz,
                                       MultiBufferSource buffer, Font.DisplayMode modo, int fondo, int luz,
                                       boolean bidireccional, CallbackInfoReturnable<Integer> cir) {
        Sonda.anotar(texto);
    }

    @Inject(
            method = "drawInternal(Lnet/minecraft/util/FormattedCharSequence;FFIZLorg/joml/Matrix4f;"
                    + "Lnet/minecraft/client/renderer/MultiBufferSource;Lnet/minecraft/client/gui/Font$DisplayMode;II)I",
            at = @At("HEAD"))
    private void modpackesSonda$secuencia(FormattedCharSequence texto, float x, float y, int color, boolean sombra,
                                          Matrix4f matriz, MultiBufferSource buffer, Font.DisplayMode modo, int fondo,
                                          int luz, CallbackInfoReturnable<Integer> cir) {
        Sonda.anotar(texto);
    }

    @Inject(
            method = "drawInBatch8xOutline(Lnet/minecraft/util/FormattedCharSequence;FFIILorg/joml/Matrix4f;"
                    + "Lnet/minecraft/client/renderer/MultiBufferSource;I)V",
            at = @At("HEAD"))
    private void modpackesSonda$contorno(FormattedCharSequence texto, float x, float y, int color, int colorContorno,
                                         Matrix4f matriz, MultiBufferSource buffer, int luz, CallbackInfo ci) {
        Sonda.anotar(texto);
    }
}

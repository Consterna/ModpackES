package io.github.consterna.modpackes.sonda;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;

/** Punto de entrada en Fabric 1.20.1. Lo que mide está en {@link Sonda} y en los mixins. */
public final class ModpackESSonda implements ClientModInitializer {
    private static final VolcadorDeRegistros VOLCADOR = new Volcador1201();

    @Override
    public void onInitializeClient() {
        Sonda.iniciar("fabric", "1.20.1");
        ClientCommandRegistrationCallback.EVENT.register(
                (despachador, contexto) -> despachador.register(Sonda.<FabricClientCommandSource>comando(VOLCADOR)));
    }
}

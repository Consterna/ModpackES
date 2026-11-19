package io.github.consterna.modpackes.sonda;

import net.minecraftforge.client.event.RegisterClientCommandsEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.fml.common.Mod;

/** Punto de entrada en Forge 1.20.1. Lo que mide está en {@link Sonda} y en los mixins. */
@Mod(Sonda.ID)
public final class ModpackESSonda {
    private static final VolcadorDeRegistros VOLCADOR = new Volcador1201();

    public ModpackESSonda() {
        Sonda.iniciar("forge", "1.20.1");
        MinecraftForge.EVENT_BUS.addListener(ModpackESSonda::alRegistrarComandos);
    }

    private static void alRegistrarComandos(RegisterClientCommandsEvent evento) {
        evento.getDispatcher().register(Sonda.comando(VOLCADOR));
    }
}

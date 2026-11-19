package io.github.consterna.modpackes.sonda;

import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.client.event.RegisterClientCommandsEvent;
import net.neoforged.neoforge.common.NeoForge;

/** Punto de entrada en NeoForge 1.21.1. Lo que mide está en {@link Sonda} y en los mixins. */
@Mod(value = Sonda.ID, dist = Dist.CLIENT)
public final class ModpackESSonda {
    private static final VolcadorDeRegistros VOLCADOR = new Volcador1211();

    public ModpackESSonda() {
        Sonda.iniciar("neoforge", "1.21.1");
        NeoForge.EVENT_BUS.addListener(ModpackESSonda::alRegistrarComandos);
    }

    private static void alRegistrarComandos(RegisterClientCommandsEvent evento) {
        evento.getDispatcher().register(Sonda.comando(VOLCADOR));
    }
}

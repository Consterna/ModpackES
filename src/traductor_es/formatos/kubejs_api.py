"""Métodos de KubeJS que le muestran texto al jugador, según la versión de Minecraft.

Los verificados salen del código de KubeJS (repositorio KubeJS-Mods/KubeJS, ramas 1202, 1605, 1802, 1902, 2001,
2101 y 2601: `MessageSender(KJS)`, `PlayerJS`/`PlayerKJS`, `ServerPlayerJS`/`ServerPlayerKJS`). El resto son
los de siempre (constructores de objetos, tooltips, títulos) y se aceptan en todas las versiones.
"""

from __future__ import annotations

#: método → primera versión de Minecraft (mayor, menor) en la que existe, comprobado en el código de cada rama
VERIFICADOS: dict[str, tuple[int, int]] = {
    "tell": (1, 12),  # MessageSender.tell(Component)
    "setStatusMessage": (1, 12),  # MessageSender / PlayerJS.setStatusMessage(Component)
    "kick": (1, 12),  # ServerPlayerJS.kick(Component)
    "notify": (1, 19),  # PlayerKJS.notify(título, texto): aparece en la rama 1902
    "openInventoryGUI": (1, 19),  # ServerPlayerKJS.openInventoryGUI(…, Component título)
    "openChestGUI": (1, 20),  # ServerPlayerKJS.openChestGUI(Component título, …): aparece en la rama 2001
}

#: Se aceptan en cualquier versión; no se comprobaron una por una contra el código de KubeJS.
GENERALES = frozenset({
    "statusMessage", "displayClientMessage", "sendSystemMessage", "sendMessage", "displayName", "setDisplayName",
    "tooltip", "addTooltip", "title", "setTitle", "subtitle", "setSubtitle", "lore", "setLore", "actionbar",
    "setActionbar",
})  # fmt: skip


def llamadas_de_texto(version: tuple[int, ...] | None) -> frozenset[str]:
    """Los métodos de texto que existen en esa versión de Minecraft. Sin versión: todos (es lo más prudente)."""
    if version is None:
        return GENERALES | VERIFICADOS.keys()
    return GENERALES | {m for m, desde in VERIFICADOS.items() if tuple(version[:2]) >= desde}

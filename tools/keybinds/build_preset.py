"""Build the pack's controls preset from the captured Minecraft option registry."""

from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
PRESET = HERE.parents[1] / "launcher/controls-preset.txt"
UNKNOWN = "key.keyboard.unknown"
VANILLA = frozenset("attack use forward left back right jump sneak sprint drop inventory chat playerlist pickItem "
                    "command socialInteractions screenshot togglePerspective fullscreen swapOffhand "
                    "saveToolbarActivator loadToolbarActivator advancements".split()) | {
                        f"hotbar.{slot}" for slot in range(1, 10)}
RESERVED = {"key.keyboard." + key for key in ("escape", "f1", "f3", "b")}
PRIORITY = {
    "key.sophisticatedbackpacks.open_backpack": "g",
    "key.ars_nouveau.open_book": "v",
    "key.ftbultimine": "grave.accent",
    "key.ftbchunks.map": "m",
    "keybind.ironjetpacks.engine": "f8",
    "keybind.ironjetpacks.hover": "h",
    "keybind.ironjetpacks.increment_throttle": "period",
    "keybind.ironjetpacks.decrement_throttle": "comma",
    "justdirethings.key.toggle_tool": "j",
    "key.mekanism.module_tweaker": "backslash",
    "key.curios.open.desc": "i",
    "key.occultism.storage_remote": "n",
    "key.buildinggadgets2.settings_menu": "f6",
    "key.buildinggadgets2.undo": "backspace",
    "key.jei.showRecipe": "r",
    "key.jei.showUses": "u",
    "key.jei.bookmark": "y",
    "key.moreoverlays.lightoverlay.desc": "f7",
    "key.moreoverlays.chunkbounds.desc": "f9",
    "key.keybindbundles.open_radial_menu": "left.alt",
    "pneumaticcraft.helmet.hack": "home",
    "key.sophisticatedcore.transfer_to_storage": "left.bracket",
    "key.sophisticatedcore.transfer_to_inventory": "right.bracket",
    "key.enderio.travel_staff": "end",
    "key.railcraft.loco.mode": "f10",
    "key.utilityvest.radial": "f12",
    "create.keyinfo.shift_modifier": "right.shift",
    "create.keyinfo.ctrl_modifier": "right.control",
    "create.keyinfo.alt_modifier": "right.alt",
    "create.keyinfo.toolbelt": "caps.lock",
    "create.keyinfo.toolmenu": "menu",
    "key.draconicevolution.tool_modules": "f4:SHIFT",
    "pneumaticcraft.boots.kick": "insert:CONTROL",
    "key.apotheosis.open_world_tier_select": "0:CONTROL",
    "zume.zoom": "z",
}
BINDING = re.compile(r"key\.(?:(?:keyboard|mouse)\.[a-z0-9.]+|scancode\.[0-9]+)(?::(?:SHIFT|CONTROL|ALT))?")


def read_mappings(text):
    mappings = {}
    for line in text.splitlines():
        if not line.startswith("key_"):
            continue
        name, _, binding = line[4:].partition(":")
        if not name or name != name.strip() or name in mappings or not BINDING.fullmatch(binding):
            raise ValueError(f"Invalid or duplicate Minecraft option: {line}")
        mappings[name] = binding
    return mappings


def layout(recorded):
    result = {f"key.{name}": recorded[f"key.{name}"] for name in sorted(VANILLA)}
    used = RESERVED | set(result.values())
    for name, key in PRIORITY.items():
        binding = "key.keyboard." + key
        physical = binding.split(":", 1)[0]
        if name not in recorded or physical in used:
            raise ValueError(f"Missing mapping or occupied priority key: {name} ({binding})")
        used.add(physical)
        result[name] = binding
    remaining = sorted(set(recorded) - result.keys())
    counts = {}
    for name in remaining:
        physical = recorded[name].split(":", 1)[0]
        counts[physical] = counts.get(physical, 0) + 1
    for name in remaining:
        binding = recorded[name]
        physical = binding.split(":", 1)[0]
        result[name] = binding if counts[physical] == 1 and physical not in used else UNKNOWN
    return result


def render(mappings):
    return (
        "# All the Mods 10 To the Sky 2.3.1 | tools/keybinds/design.md\n"
        + "".join(f"key_{name}:{value}\n" for name, value in sorted(mappings.items()))
    )


if __name__ == "__main__":
    recorded = read_mappings((HERE / "registered-keys.txt").read_text(encoding="utf-8"))
    PRESET.write_text(render(layout(recorded)), encoding="utf-8", newline="\n")

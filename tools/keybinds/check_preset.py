"""Verify the exact namespace, vanilla controls and conservative collision policy."""

from build_preset import HERE, PRESET, RESERVED, UNKNOWN, VANILLA, layout, read_mappings, render


def main():
    recorded = read_mappings((HERE / "registered-keys.txt").read_text(encoding="utf-8"))
    text = PRESET.read_bytes().decode("utf-8")
    actual = read_mappings(text)
    if actual.keys() != recorded.keys() or text != render(layout(recorded)):
        raise ValueError("Preset must be regenerated from the pinned mapping snapshot")
    if any(actual[f"key.{name}"] != recorded[f"key.{name}"] for name in VANILLA):
        raise ValueError("A vanilla control changed")
    used = set(RESERVED)
    for name, value in actual.items():
        key = value.split(":", 1)[0]
        if key == UNKNOWN:
            continue
        if key in used:
            raise ValueError(f"Potential simultaneous key collision: {name}: {value}")
        used.add(key)
    print(f"{len(actual)} mappings; {len(VANILLA)} vanilla; {len(used - RESERVED)} bound; "
          f"{sum(':' in value for value in actual.values())} chords; zero shared physical keys.")


if __name__ == "__main__":
    main()

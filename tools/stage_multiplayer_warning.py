"""Stage the multiplayer warning policy on the checked Sky release."""

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "keybinds"))
from stage_release import ROOT, bundle, git, pin


BASE = "b549d5b15a088dc0b93401068bdc15156c4cd0d3"
BASE_SHA = "9810ffdac118e683c8aae9b4975955f1543cb995de985b285ab4e6cdfe388705"
SCRIPT = "kubejs/client_scripts/lanmc_multiplayer_warning.js"
OWNERSHIP = "launcher/pack-owned.txt"
OPTIONS = "config/defaultoptions/options.txt"
OLD_SETTING = b"skipMultiplayerWarning:false"
SETTING = b"skipMultiplayerWarning:true"


def verify_flags(manifest, read_file):
    files = {row["path"]: row for row in manifest["files"]}
    recipe = json.loads((ROOT / "tools/overlay.json").read_bytes())
    expected_script = (ROOT / SCRIPT).read_bytes()
    if expected_script.count(b".options.skipMultiplayerWarning = true") != 1:
        raise ValueError("The client script must enable the native warning skip option")
    approved = {"path": SCRIPT, **pin(expected_script)}
    if approved not in recipe["clientScripts"]["files"] or files.get(SCRIPT) != approved:
        raise ValueError("The mandatory multiplayer-warning script is missing or differs")
    if read_file(SCRIPT) != expected_script or SCRIPT not in read_file(OWNERSHIP).decode().splitlines():
        raise ValueError("The mandatory multiplayer-warning script is missing from the pack or ownership")
    if any(entry["path"] == OPTIONS for entry in recipe["patches"]) and OPTIONS not in files:
        raise ValueError("The patched native defaults are missing")
    if OPTIONS in files:
        lines = [line for line in read_file(OPTIONS).splitlines() if line.startswith(b"skipMultiplayerWarning:")]
        if lines != [SETTING]:
            raise ValueError("The distributed native default must explicitly enable skipMultiplayerWarning")


def option_patch(source):
    matches = list(re.finditer(rb"(?m)^skipMultiplayerWarning:[^\r\n]*", source))
    if len(matches) > 1:
        raise ValueError("Found several authored multiplayer-warning options")
    if matches:
        old = matches[0][0]
        if old == SETTING:
            return None
        if old != OLD_SETTING or source.count(old) != 1:
            raise ValueError("Unsupported authored multiplayer-warning option")
        new = SETTING
    else:
        old = source
        if not old:
            raise ValueError("Expected nonempty authored options")
        newline = b"\r\n" if b"\r\n" in source else b"\n"
        new = source + (b"" if source.endswith(b"\n") else newline) + SETTING + newline
    return {"path": OPTIONS, "from": old.decode("utf-8"), "to": new.decode("utf-8"),
            "before": pin(source), "after": pin(source.replace(old, new, 1))}


def rebind(archive_path, client_lock):
    lock = json.loads(client_lock.read_bytes())
    archive_data = checked(archive_path, lock["client"])
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        listed = next((row for row in lock["overrides"] if row["path"] == OPTIONS), None)
        if listed is None:
            patch = None
        else:
            data = archive.read(listed["archivePath"])
            if pin(data) != {key: listed[key] for key in ("sizeBytes", "sha256")}:
                raise ValueError("The new author options differ from the approved receipt")
            patch = option_patch(data)
    print(json.dumps({"authorArchiveSha256": lock["client"]["sha256"], "patch": patch,
                      "ownNativeOptions": patch is not None}, ensure_ascii=False, indent=2))


def checked(path, record):
    data = path.read_bytes()
    if pin(data) != {key: record[key] for key in ("sizeBytes", "sha256")}:
        raise ValueError(f"Unexpected input bytes: {path}")
    return data


def stage(base, output):
    raw = (base / "base-manifest.json").read_bytes()
    if pin(raw)["sha256"] != BASE_SHA:
        raise ValueError("Unknown base release")
    manifest = json.loads(raw)
    if manifest["revision"] != BASE or manifest["packId"] != "minecraft-13":
        raise ValueError("Unexpected base manifest")
    revision = git("rev-parse", "HEAD").decode().strip()
    original = {row["path"]: row for row in manifest["files"]}
    old_asset, = (entry for entry in manifest["assets"] if OWNERSHIP in entry["covers"])
    with zipfile.ZipFile(io.BytesIO(checked(base / old_asset["name"], old_asset))) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    if set(payload) != {OWNERSHIP, "launcher/jvm-args.txt"} or sorted(payload) != sorted(old_asset["covers"]):
        raise ValueError("Unexpected original launcher archive")
    for name, data in payload.items():
        if pin(data) != {key: original[name][key] for key in ("sha256", "sizeBytes")}:
            raise ValueError(f"Invalid launcher member {name}")
    new_ownership = (ROOT / OWNERSHIP).read_bytes()
    expected = ("\n".join(sorted(set(payload[OWNERSHIP].decode().splitlines()) | {SCRIPT, OPTIONS})) + "\n").encode()
    script = (ROOT / SCRIPT).read_bytes()
    if new_ownership != expected or SCRIPT in original:
        raise ValueError("Unexpected ownership change")
    for name, data in ((SCRIPT, script), (OWNERSHIP, new_ownership)):
        if git("show", f"{revision}:{name}") != data:
            raise ValueError(f"Working file differs from Git: {name}")
        original[name] = {"path": name, **pin(data)}
    recipe = json.loads(git("show", f"{revision}:tools/overlay.json"))
    if {"path": SCRIPT, **pin(script)} not in recipe["clientScripts"]["files"]:
        raise ValueError("The author overlay does not pin the script")
    payload[OWNERSHIP] = new_ownership
    old_config, = (entry for entry in manifest["assets"] if OPTIONS in entry["covers"])
    with zipfile.ZipFile(io.BytesIO(checked(base / old_config["name"], old_config))) as archive:
        config = {name: archive.read(name) for name in archive.namelist()}
    if sorted(config) != sorted(old_config["covers"]):
        raise ValueError("Unexpected original config archive")
    for name, data in config.items():
        if original[name] != {"path": name, **pin(data)}:
            raise ValueError(f"Invalid config member {name}")
    before = config[OPTIONS]
    if [line for line in before.splitlines() if line.startswith(b"skipMultiplayerWarning:")] != [OLD_SETTING]:
        raise ValueError("Expected one false native warning default in the base manifest")
    config[OPTIONS] = before.replace(OLD_SETTING, SETTING, 1)
    patch = option_patch(before)
    if patch not in recipe["patches"]:
        raise ValueError("The author overlay does not pin the native option change")
    original[OPTIONS] = {"path": OPTIONS, **pin(config[OPTIONS])}

    asset_data = {}
    additions = []
    for name, members in (("launcher", payload), ("config", config), ("multiplayer-warning", {SCRIPT: script})):
        data = bundle(members)
        filename = f"r-{pin(data)['sha256'][:12]}-{name}.zip"
        asset_data[filename] = data
        additions.append({"name": filename, "kind": "zipRoot", "covers": sorted(members), **pin(data)})
    library = manifest["library"]
    with zipfile.ZipFile(io.BytesIO(checked(base / library["name"], library))) as archive:
        card = json.loads(archive.read("library.json"))
        preview = archive.read("preview.jpg")
    if card["revision"] != BASE or preview != (ROOT / "library/preview.jpg").read_bytes():
        raise ValueError("Unexpected base library")
    card["revision"] = revision
    data = bundle({"library.json": (json.dumps(card, ensure_ascii=False, indent=2) + "\n").encode(),
                   "preview.jpg": preview})
    name = f"library-{pin(data)['sha256']}.zip"
    asset_data[name] = data
    manifest["library"] = {"name": name, "revision": revision, **pin(data)}
    manifest["revision"] = revision
    manifest["generatedAtUtc"] = datetime.fromtimestamp(
        int(git("show", "-s", "--format=%ct", revision)), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["files"] = [original[name] for name in sorted(original)]
    manifest["assets"] = sorted([entry for entry in manifest["assets"] if entry not in (old_asset, old_config)] + additions,
                                key=lambda entry: entry["name"])
    if sorted(name for entry in manifest["assets"] for name in entry["covers"]) != sorted(original):
        raise ValueError("Asset coverage differs from the supported payload")
    required = {**payload, OPTIONS: config[OPTIONS], SCRIPT: script}
    verify_flags(manifest, required.__getitem__)
    output.mkdir()
    (output / "assets").mkdir()
    for name, data in asset_data.items():
        (output / "assets" / name).write_bytes(data)
    (output / "pack-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8", newline="\n")
    print(revision, pin(script)["sha256"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--verify", type=Path, metavar="RELEASE_DIRECTORY")
    parser.add_argument("--rebind", nargs=2, type=Path, metavar=("AUTHOR_ZIP", "CLIENT_LOCK"))
    args = parser.parse_args()
    if args.rebind:
        rebind(*args.rebind)
    elif args.verify:
        manifest = json.loads((args.verify / "pack-manifest.json").read_bytes())

        def read_asset(path):
            asset, = (entry for entry in manifest["assets"] if path in entry["covers"])
            data = checked(args.verify / "assets" / asset["name"], asset)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                content = archive.read(path)
            row, = (entry for entry in manifest["files"] if entry["path"] == path)
            if row != {"path": path, **pin(content)}:
                raise ValueError(f"File pin differs: {path}")
            return content

        verify_flags(manifest, read_asset)
        print("Multiplayer warning policy verified")
    elif args.base and args.output:
        stage(args.base, args.output)
    else:
        parser.error("supply base and output directories or --verify")

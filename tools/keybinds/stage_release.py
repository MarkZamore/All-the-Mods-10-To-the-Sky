"""Append the checked controls preset to the approved published Sky payload."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

from build_preset import PRESET
from check_preset import main as check_preset


BASE = "a64c7c774e41a0e69f6ddd2233dbcf32a1aa962e"
BASE_HASH = "8e448e98005ff74c7e1f49eab9c454ab36d28dc5ecb849ea8e92eabf3d8ccd6e"
PATH = "launcher/controls-preset.txt"
ROOT = PRESET.parents[1]


def pin(data):
    return {"sizeBytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def bundle(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    return buf.getvalue()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    check_preset()
    raw = (args.base / "base-manifest.json").read_bytes()
    if pin(raw)["sha256"] != BASE_HASH:
        raise ValueError("Approved source pack manifest has changed")
    manifest = json.loads(raw)
    if manifest["packId"] != "minecraft-13" or manifest["revision"] != BASE:
        raise ValueError("Unexpected source pack")
    revision = git("rev-parse", "HEAD").decode().strip()
    changed = git("diff", "--name-only", BASE, revision).decode().splitlines()
    if any(path not in (PATH, ".gitattributes", "README.md") and not path.startswith("tools/keybinds/")
           for path in changed):
        raise ValueError("Unexpected change besides the controls preset")
    preset = PRESET.read_bytes()
    if preset != git("show", f"{revision}:{PATH}") or any(f["path"] == PATH for f in manifest["files"]):
        raise ValueError("Preset is not the checked source or already exists in the base manifest")
    old_library = manifest["library"]
    lib_bytes = (args.base / old_library["name"]).read_bytes()
    if pin(lib_bytes) != {key: old_library[key] for key in ("sizeBytes", "sha256")}:
        raise ValueError("Base library hash differs")
    with zipfile.ZipFile(io.BytesIO(lib_bytes)) as archive:
        if set(archive.namelist()) != {"library.json", "preview.jpg"}:
            raise ValueError("Unexpected library members")
        preview = archive.read("preview.jpg")
        catalog = json.loads(archive.read("library.json"))
    if catalog["revision"] != BASE or preview != (ROOT / "library/preview.jpg").read_bytes():
        raise ValueError("Unexpected library revision or preview")
    catalog["revision"] = revision
    library = bundle({"library.json": (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode(),
                      "preview.jpg": preview})
    archive = bundle({PATH: preset})
    asset_name = f"r-{pin(archive)['sha256'][:12]}-controls-preset.zip"
    library_name = f"library-{pin(library)['sha256']}.zip"
    manifest["revision"] = revision
    timestamp = int(git("show", "-s", "--format=%ct", revision))
    manifest["generatedAtUtc"] = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["files"] = sorted([*manifest["files"], {"path": PATH, **pin(preset)}], key=lambda row: row["path"])
    manifest["assets"] = sorted([*manifest["assets"], {"name": asset_name, "kind": "zipRoot",
        "covers": [PATH], **pin(archive)}], key=lambda row: row["name"])
    manifest["library"] = {"name": library_name, "revision": revision, **pin(library)}
    if sorted(f["path"] for f in manifest["files"]) != sorted(
            name for asset in manifest["assets"] for name in asset["covers"]):
        raise ValueError("Unexpected asset coverage")
    args.output.mkdir()
    (args.output / "assets").mkdir()
    (args.output / "assets" / asset_name).write_bytes(archive)
    (args.output / "assets" / library_name).write_bytes(library)
    (args.output / "pack-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8", newline="\n")
    print(f"{revision} {PATH} SHA-256 {pin(preset)['sha256']}")


if __name__ == "__main__":
    main()

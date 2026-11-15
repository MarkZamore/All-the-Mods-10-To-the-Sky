"""Reuse verified Sky release assets whose files are unaffected by localization."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

import stage_early_memory_release as bundles


BASE_REVISION = "f3f16d5361d48152d4eaf4291e088370d89d7c94"
BASE_SHA = "9b5fe72696de53e4db2444e90b0995275c47d1b4036a6094a3673176ee9fe5f9"
ROOT = Path(__file__).resolve().parents[1]


def table(rows):
    return {row["path"]: {name: row[name] for name in ("sizeBytes", "sha256")} for row in rows}


def stage(base, out, revision, prepare, release, delivery, verify_library):
    manifest_bytes = (base / "pack-manifest.json").read_bytes()
    prepare.require(hashlib.sha256(manifest_bytes).hexdigest() == BASE_SHA, "Use the reviewed Sky base manifest")
    current = prepare.decode_json(manifest_bytes)
    prepare.require(current["revision"] == BASE_REVISION and current["packId"] == "minecraft-13",
                    "Unexpected release base")
    author = release.read_lock(ROOT / release.COMPLETE_LOCK, "complete")
    release.same_author(release.read_lock(ROOT / release.CLIENT_LOCK, "client-only"), author)
    recipe, _, _, descriptor = release.source_policy(ROOT, author)
    localized = prepare.book_localizations(recipe, ROOT, author)
    prepare.require(localized and "bookJarLocalization" not in recipe and not recipe["patches"],
                    "This release path accepts source-only locale files")
    policy = {
        **prepare.overlay_additions(recipe, ROOT, author),
        **prepare.memory_settings_config(recipe, ROOT, author),
        **prepare.client_scripts(recipe, ROOT, author),
        **localized,
        release.OWNERSHIP: (ROOT / release.OWNERSHIP).read_bytes(),
    }
    owned = sorted(set(policy) - {release.OWNERSHIP, "launcher/jvm-args.txt"})
    prepare.require(policy[release.OWNERSHIP] == ("\n".join(owned) + "\n").encode(), "Incorrect file ownership")
    pins = {name: prepare.fingerprint(data) for name, data in policy.items()}
    pins[release.DESCRIPTOR] = descriptor
    original = table(current["files"])
    unchanged_policy = pins.keys() - localized.keys() - {release.OWNERSHIP}
    prepare.require(all(pins[name] == original[name] for name in unchanged_policy), "Non-localization policy changed")
    modified = {name for name in pins if original.get(name) != pins[name]}
    files = original | pins
    excluded = prepare.excluded_dependency_files(prepare.overlay_dependency_keys(recipe, author), author["files"])
    timestamp = delivery.check_source(ROOT, revision, current["packId"], pins, recipe=recipe)
    release.verify_manifest({**current, "files": [{"path": name, **pin} for name, pin in sorted(files.items())]},
                            pins, author, excluded)

    affected = [asset for asset in current["assets"] if modified.intersection(asset["covers"])]
    staged = modified.union(name for asset in affected for name in asset["covers"])
    with TemporaryDirectory(prefix=".sky-localization-", dir=out.parent) as temporary:
        work = Path(temporary)
        payload = work / "payload"
        pending = work / "release"
        (pending / "assets").mkdir(parents=True)
        for asset in affected:
            prepare.require(asset["kind"] == "zipRoot", "Expected ZIP for changed localization content")
            archive = base / "assets" / asset["name"]
            with archive.open("rb") as stream:
                prepare.require(archive.stat().st_size == asset["sizeBytes"] and
                                hashlib.file_digest(stream, "sha256").hexdigest() == asset["sha256"],
                                f"Unexpected ZIP bytes: {archive.name}")
            with zipfile.ZipFile(archive) as source:
                prepare.require(sorted(source.namelist()) == sorted(asset["covers"]), "Unexpected ZIP entries")
                for name in asset["covers"]:
                    original_bytes = source.read(name)
                    prepare.require(prepare.fingerprint(original_bytes) == original[name],
                                    f"Original release content differs: {name}")
                    dest = payload / prepare.safe_path(name)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(policy.get(name, original_bytes))
        for name in modified:
            dest = payload / prepare.safe_path(name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(policy[name])
        added = delivery.build_assets(payload, pending / "assets", {name: files[name] for name in staged})
        assets = sorted(added + [asset for asset in current["assets"] if asset not in affected],
                        key=lambda asset: asset["name"])
        prepare.require(sorted(name for asset in assets for name in asset["covers"]) == sorted(files),
                        "Invalid coverage in localization release")
        # The published base library still describes the exact same mod JARs.
        bundles.BASE_REVISION = BASE_REVISION
        library = bundles.retag_library(base, current["library"], pending, ROOT, revision, prepare, verify_library)
        result = {**current, "revision": revision, "generatedAtUtc": timestamp, "library": library,
                  "files": [{"path": name, **pin} for name, pin in sorted(files.items())], "assets": assets}
        release.verify_manifest(result, pins, author, excluded)
        prepare.write_json(pending / "pack-manifest.json", result)
        prepare.write_json(pending / "locale-release.json", {
            "baseRevision": BASE_REVISION, "revision": revision, "changedFiles": sorted(modified),
            "newAssets": added, "removedAssets": [asset["name"] for asset in affected], "library": library,
        })
        pending.rename(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    sys.path[:0] = [str(args.tools / "tools/PackData/CurseForge"), str(args.tools / "tools")]
    import prepare
    import release_overlay
    import stage_release
    from pack_library import verify_library

    revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    stage(args.base.resolve(strict=True), prepare.check_output(args.output, args.workspace.resolve(strict=True)),
          revision, prepare, release_overlay, stage_release, verify_library)


if __name__ == "__main__":
    main()

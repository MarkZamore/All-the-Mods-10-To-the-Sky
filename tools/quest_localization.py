"""Check/update the source bindings for Sky's native Russian FTB Quests tables."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LANG = "config/ftbquests/quests/lang/"
INDEX = ROOT / "tools/quest-source-index.json"
RECIPE = ROOT / "tools/overlay.json"
KEY = re.compile(r"[A-Za-z0-9_.-]+")
TABLE = re.compile(r"en_us(?:/(?:chapters/)?[a-z0-9_.-]+)?\.snbt")
WHITESPACE = re.compile(r"[\s,]*")
STRING_LIST = re.compile(r'\[\s*(?:"(?:\\.|[^"\\])*"\s*,?\s*)*\]')


def digest(payload):
    return {"sizeBytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def parse(payload):
    """Read the flat FTB SNBT dialect, whose values are strings or lists of strings."""
    source = payload.decode("utf-8-sig").strip()
    if not source.startswith("{") or not source.endswith("}"):
        raise ValueError("Expected an FTB locale compound")
    offset = 1
    result = {}
    decoder = json.JSONDecoder()
    while (offset := WHITESPACE.match(source, offset).end()) < len(source) - 1:
        match = KEY.match(source, offset)
        if not match:
            raise ValueError(f"Invalid locale key near {source[offset:offset + 50]!r}")
        key = match[0]
        offset = WHITESPACE.match(source, match.end()).end()
        if key in result or source[offset] != ":":
            raise ValueError(f"Invalid or duplicate locale key: {key}")
        offset = WHITESPACE.match(source, offset + 1).end()
        match = STRING_LIST.match(source, offset)
        if match:
            value = [json.loads(token[0]) for token in re.finditer(r'"(?:\\.|[^"\\])*"', match[0])]
            offset = match.end()
        else:
            value, offset = decoder.raw_decode(source, offset)
            if not isinstance(value, str):
                raise ValueError(f"Expected locale string or string list for {key}")
        result[key] = value
    return result


def render(values):
    rows = (f"\t{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in sorted(values.items()))
    return ("{\n" + "".join(rows) + "}\n").encode("utf-8")


def author_sources(archive, lock):
    if archive.stat().st_size != lock["client"]["sizeBytes"]:
        raise ValueError("Unexpected author ZIP size")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != lock["client"]["sha256"]:
            raise ValueError("Unexpected author ZIP SHA256")
    pinned = {item["path"]: {key: item[key] for key in ("sizeBytes", "sha256")} for item in lock["overrides"]}
    sources, original_russian = {}, {}
    with zipfile.ZipFile(archive) as original:
        for path, pin in pinned.items():
            if not path.startswith(LANG):
                continue
            name = path.removeprefix(LANG)
            if not TABLE.fullmatch(name.replace("ru_ru", "en_us", 1)):
                continue
            payload = original.read("overrides/" + path)
            if digest(payload) != pin:
                raise ValueError(f"Author locale differs from its pin: {path}")
            (sources if name.startswith("en_us") else original_russian)[path] = parse(payload)
    return sources, original_russian, pinned


def fingerprints(sources):
    return {path: {key: hashlib.sha256(json_bytes(value)).hexdigest() for key, value in sorted(rows.items())}
            for path, rows in sorted(sources.items())}


def references(value):
    return sorted(re.findall(r"\{(?:@[a-z_][a-z0-9_]*|[a-z_][a-z0-9_.-]*:[^{}]*)\}"
                             r"|https?://[^\s\]>)\"']+", value))


def compatible(source, translation):
    if type(source) is not type(translation):
        return False
    if isinstance(source, str):
        return references(source) == references(translation)
    return len(source) == len(translation) and all(compatible(en, ru) for en, ru in zip(source, translation))


def check(archive, lock_path):
    lock = json.loads(lock_path.read_bytes())
    english, author_russian, _ = author_sources(archive, lock)
    current = fingerprints(english)
    previous = json.loads(INDEX.read_bytes())
    for path in sorted(current.keys() | previous.keys()):
        if path not in current:
            print(f"REMOVED {path}")
        elif path not in previous:
            print(f"NEW {path}")
        else:
            before, after = previous[path], current[path]
            changed = [key for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)]
            if changed:
                print(f"CHANGED {path} ({len(changed)} keys)")
                for key in changed:
                    print(f"  {key}")
    if previous != current:
        raise ValueError("Review the changed English strings before rebinding the Russian locale")

    recipe = json.loads(RECIPE.read_bytes())
    rows = {row["path"]: row["output"] for row in recipe["bookLocalization"] if row["path"].startswith(LANG)}
    flat = LANG + "ru_ru.snbt"
    if set(author_russian) - rows.keys() or flat not in rows:
        raise ValueError("The recipe must include the merged translation and each author Russian table")
    translations = {}
    for output, pin in rows.items():
        payload = (ROOT / output).read_bytes()
        if digest(payload) != pin:
            raise ValueError(f"Russian locale differs from its pin: {output}")
        translations[output] = parse(payload)
    combined = {}
    for path, values in english.items():
        russian = path.replace("/en_us", "/ru_ru")
        if russian == flat:
            continue
        if russian not in translations or translations[russian].keys() != values.keys():
            raise ValueError(f"Incomplete Russian quest table: {russian}")
        for key, value in values.items():
            if not compatible(value, translations[russian][key]):
                raise ValueError(f"Quest locale changes a format token or value shape: {russian} {key}")
        combined.update(translations[russian])
    if translations[flat] != combined:
        raise ValueError("Flat Russian translation must match the split tables")
    print(f"Verified {len(combined)} locale keys in {len(rows)} Russian tables")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--lock", type=Path, default=ROOT / "tools/upstream-client-lock.json")
    args = parser.parse_args()
    try:
        check(args.archive, args.lock)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()

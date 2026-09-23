#!/usr/bin/env python3
"""Local evidence cache. No networking; a hit does not establish the live patch."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

IDENTITY_FIELDS = ("game", "region", "season", "patch", "mode", "edition")
TTL_HOURS = {"rules": 168, "guide": 24, "stats": 6}
UNKNOWN = {"unknown", "latest", "current", "未知", "待确认", "当前", "最新"}
MAX_BYTES = 256 * 1024


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def identity(value):
    if not isinstance(value, dict) or set(value) != set(IDENTITY_FIELDS):
        raise ValueError("identity must contain exactly: " + ", ".join(IDENTITY_FIELDS))
    result = {key: text(value[key], key) for key in IDENTITY_FIELDS}
    if any(item.casefold() in UNKNOWN for item in result.values()):
        raise ValueError("Resolve the exact version before caching")
    return result


def timestamp(value):
    parsed = datetime.fromisoformat(text(value, "timestamp").replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamps require an explicit timezone")
    return parsed.astimezone(timezone.utc)


def validate(card, now=None):
    now = now or datetime.now(timezone.utc)
    fields = {"schema_version", "identity", "topic", "kind", "status", "verified_at",
              "summary", "sources", "limitations"}
    if (not isinstance(card, dict) or set(card) != fields
            or type(card["schema_version"]) is not int or card["schema_version"] != 1):
        raise ValueError("Invalid evidence card schema")
    normalized = dict(card)
    normalized["identity"] = identity(card["identity"])
    for name in ("topic", "summary", "kind", "status"):
        normalized[name] = text(card[name], name)
    if normalized["kind"] not in TTL_HOURS or normalized["status"] not in {"verified", "partial", "conflict"}:
        raise ValueError("Invalid kind or evidence status")
    verified = timestamp(card["verified_at"])
    if verified > now + timedelta(minutes=5):
        raise ValueError("Evidence timestamp is in the future")
    normalized["verified_at"] = verified.isoformat()
    if not isinstance(card["limitations"], list):
        raise ValueError("limitations must be a list")
    normalized["limitations"] = [text(item, "limitation") for item in card["limitations"]]
    if normalized["status"] != "verified" and not normalized["limitations"]:
        raise ValueError("Incomplete evidence needs an explicit limitation")
    if not isinstance(card["sources"], list) or not card["sources"]:
        raise ValueError("At least one actually opened source is required")
    normalized["sources"] = []
    for source in card["sources"]:
        if not isinstance(source, dict) or set(source) != {"title", "url", "checked_at", "supports"}:
            raise ValueError("Invalid source schema")
        entry = {key: text(value, key) for key, value in source.items()}
        url = urlsplit(entry["url"])
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            raise ValueError("Use a public HTTP(S) source URL without credentials")
        checked = timestamp(entry["checked_at"])
        if checked > verified:
            raise ValueError("Source check cannot follow the card verification")
        entry["checked_at"] = checked.isoformat()
        normalized["sources"].append(entry)
    return normalized


def key_for(version, topic):
    value = {"identity": identity(version), "topic": text(topic, "topic")}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing a symlink evidence file")
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Evidence card exceeds 256 KiB; save a concise summary")
    return json.loads(data)


def put(directory, card, now=None, replace_invalid=False):
    card = validate(card, now)
    directory = Path(directory)
    key = key_for(card["identity"], card["topic"])
    target = directory / f"{key}.json"
    if target.is_symlink():
        raise ValueError("Refusing a symlink evidence file")
    invalid_existing = False
    if target.exists():
        try:
            previous = validate(read_json(target), now)
            if key_for(previous["identity"], previous["topic"]) != key:
                raise ValueError("Evidence identity does not match its filename")
        except (ValueError, TypeError, UnicodeError) as error:
            if not replace_invalid:
                raise ValueError("Existing cache is invalid; use --replace-invalid to preserve a backup") from error
            invalid_existing = True
        else:
            # Never silently replace a newer verification with an older one.
            if timestamp(previous["verified_at"]) > timestamp(card["verified_at"]):
                raise ValueError("Refusing an older replacement")
    data = (json.dumps(card, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("Evidence card exceeds 256 KiB")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    backup = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".card-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if invalid_existing:
            backup = directory / f"{key}.invalid-{uuid4().hex}.bak"
            target.rename(backup)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target, backup


def get(directory, version, topic, scope="current", now=None):
    if scope not in {"current", "historical"}:
        raise ValueError("scope must be current or historical")
    now = now or datetime.now(timezone.utc)
    key = key_for(version, topic)
    result = {"status": "miss", "scope": scope, "requires_research": True,
              "requires_version_check": scope == "current"}
    path = Path(directory) / f"{key}.json"
    try:
        card = validate(read_json(path), now)
        if key_for(card["identity"], card["topic"]) != key:
            raise ValueError("Evidence identity does not match the requested key")
    except FileNotFoundError:
        return result
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        return dict(result, status="invalid", reason=str(error))
    # Old source timestamps must not become fresh merely by rewriting verified_at.
    evidence_time = min([timestamp(card["verified_at"])] +
                        [timestamp(source["checked_at"]) for source in card["sources"]])
    age = max(0, (now - evidence_time).total_seconds() / 3600)
    status = card["status"]
    if status == "verified":
        status = "hit" if scope == "historical" or age < TTL_HOURS[card["kind"]] else "stale"
    return dict(result, status=status, requires_research=status != "hit",
                age_hours=round(age, 2), card=card)


def list_cards(directory, now=None):
    entries, invalid = [], []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            card = validate(read_json(path), now)
            if path.stem != key_for(card["identity"], card["topic"]):
                raise ValueError("Evidence filename does not match its identity")
            entries.append({key: card[key] for key in
                            ("identity", "topic", "kind", "status", "verified_at")})
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            invalid.append({"file": path.name, "reason": str(error)})
    entries.sort(key=lambda item: timestamp(item["verified_at"]), reverse=True)
    return {"entries": entries, "invalid": invalid,
            "note": "Discovery only; listed versions are not necessarily current."}


def main():
    # Stable machine-readable Chinese output, including redirected Windows stdout.
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", default=".jinchanchan-cache",
                        help="Use the same workspace directory across sessions")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List identities/topics, not full strategy text")
    writer = commands.add_parser("put", help="Save a verified public evidence card")
    writer.add_argument("--file", required=True)
    writer.add_argument("--replace-invalid", action="store_true",
                        help="Move an invalid existing card to a .bak file before writing")
    reader = commands.add_parser("get", help="Exact version/topic lookup; never falls back to another patch")
    for field in IDENTITY_FIELDS:
        defaults = {"game": "金铲铲之战", "region": "国服"}
        reader.add_argument(f"--{field}", default=defaults.get(field), required=field not in defaults)
    reader.add_argument("--topic", required=True)
    reader.add_argument("--scope", choices=("current", "historical"), default="current")
    args = parser.parse_args()
    try:
        if not args.cache_dir.strip():
            raise ValueError("cache-dir must not be empty")
        directory = Path(args.cache_dir).expanduser()
        if args.command == "put":
            saved, backup = put(directory, read_json(args.file), replace_invalid=args.replace_invalid)
            result = {"saved": str(saved), "backup": str(backup) if backup else None}
        elif args.command == "list":
            result = list_cards(directory)
        else:
            version = {field: getattr(args, field) for field in IDENTITY_FIELDS}
            result = get(directory, version, args.topic, args.scope)
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        parser.exit(1, f"Cache error: {error}\n")
    # A miss/stale/invalid lookup is data, not a process failure. Inspect status.
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

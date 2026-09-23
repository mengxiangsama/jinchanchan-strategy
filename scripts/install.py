#!/usr/bin/env python3
"""Install only this skill; never overwrite an existing destination."""
import argparse
from pathlib import Path
import shutil

SKILL_NAME = "jinchanchan-strategy"
SOURCE = Path(__file__).resolve().parents[1] / "skills" / SKILL_NAME


def install(destination):
    root = Path(destination).expanduser()
    target = root / SKILL_NAME
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Refusing to overwrite: {target}")
    if not (SOURCE / "SKILL.md").is_file():
        raise FileNotFoundError("Skill source is incomplete")
    root.mkdir(parents=True, exist_ok=True)
    # copytree also refuses an intervening concurrent creation.
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns(
        "__pycache__", ".DS_Store", ".jinchanchan-cache"))
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", default=str(Path.home() / ".agents" / "skills"))
    args = parser.parse_args()
    if not args.destination.strip():
        parser.error("destination must not be empty")
    try:
        target = install(args.destination)
    except OSError as error:
        parser.exit(1, f"Installation failed: {error}\n")
    print(f"Installed: {target}")
    print("Invoke $jinchanchan-strategy. Check or refresh your host's skill list.")


if __name__ == "__main__":
    main()

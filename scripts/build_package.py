#!/usr/bin/env python3
"""Build the runtime-only plugin archive from explicit, reviewed members."""
import argparse
from pathlib import Path
import zipfile

MEMBERS = (
    "plugin.json", "README.md",
    "skills/task-disk-review/SKILL.md",
    "skills/task-disk-review/agents/openai.yaml",
    "skills/task-disk-review/scripts/devspace.py",
    "skills/task-disk-review/scripts/devspace/__init__.py",
    "skills/task-disk-review/scripts/devspace/review.py",
    "skills/task-disk-review/scripts/devspace/report.py",
    "skills/task-disk-review/scripts/devspace/git_inventory.py",
    "skills/task-disk-review/scripts/devspace/git_worktree.py",
    "skills/task-disk-review/scripts/devspace/plans.py",
    "skills/task-disk-review/scripts/devspace/global_inventory.py",
    "skills/task-disk-review/scripts/devspace/cleanup.py",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new zip archive; never overwrites an existing file")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Validate every member before creating output. No directory glob or Git archive.
    for member in MEMBERS:
        source = root / member
        if not source.is_file() or source.is_symlink() or source.resolve() != source:
            parser.error("package member missing or linked: " + member)
    with zipfile.ZipFile(arguments.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in MEMBERS:
            archive.write(root / member, member)
    print("Packaged " + str(len(MEMBERS)) + " runtime files")


if __name__ == "__main__":
    main()

"""Validate release tags against the integration manifest version."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def normalize_tag(tag: str) -> str:
    """Normalize a git tag to the manifest version format."""
    return tag.removeprefix("v")


def validate_release_version(
    manifest_path: Path, release_tag: str | None = None
) -> str:
    """Return the manifest version and validate it against an optional tag."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_version = manifest["version"]

    if release_tag is not None:
        normalized_tag = normalize_tag(release_tag)
        if normalized_tag != manifest_version:
            msg = (
                "Release tag does not match manifest version: "
                f"tag={release_tag!r}, manifest={manifest_version!r}"
            )
            raise ValueError(msg)

    return manifest_version


def main() -> int:
    """Validate the release version for local checks and CI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest_path", type=Path)
    parser.add_argument("release_tag", nargs="?")
    args = parser.parse_args()

    version = validate_release_version(args.manifest_path, args.release_tag)
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

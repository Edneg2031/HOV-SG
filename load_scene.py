#!/usr/bin/env python3
"""Extract one scene archive and prepare an HOV-SG-compatible directory.

The repository expects a scene directory shaped like:

  <scene_root>/
    rgb/
    depth/
    pose/

Some HM3D-style archives instead use alternate names such as
`depth_euclidean` and `point_info`. This script extracts one scene archive
into the current project and creates compatibility symlinks when it can do so
unambiguously.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


STANDARD_DIRS = ("rgb", "depth", "pose")
COMPATIBILITY_ALIASES = {
    "depth": ("depth", "depth_euclidean", "depth_zbuffer"),
    "pose": ("pose", "point_info"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one scene archive and prepare a local HOV-SG scene directory.",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Path to a scene .zip archive or an already unpacked scene directory.",
    )
    parser.add_argument(
        "--scene-id",
        type=str,
        default=None,
        help="Scene id to locate inside the archive when the top-level folder name is not enough.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/hm3dsem_walks/val"),
        help="Where the prepared scene directory should be written.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing target scene directory.",
    )
    return parser.parse_args()


def choose_scene_dir(root: Path, scene_id: str | None) -> Path:
    if scene_id:
        candidate = root / scene_id
        if candidate.is_dir():
            return candidate

    entries = [entry for entry in root.iterdir() if entry.is_dir()]
    if len(entries) == 1:
        return entries[0]

    for entry in entries:
        if scene_id and scene_id in entry.name:
            return entry

    available = ", ".join(sorted(entry.name for entry in entries))
    raise RuntimeError(f"Could not identify the extracted scene directory. Available folders: {available or '<none>'}")


def ensure_dir_link(target: Path, source: Path) -> None:
    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    target.symlink_to(source, target_is_directory=True)


def prepare_scene_layout(scene_dir: Path) -> None:
    for standard_name in STANDARD_DIRS:
        standard_path = scene_dir / standard_name
        if standard_path.exists():
            continue

        alias_source = None
        for alias_name in COMPATIBILITY_ALIASES.get(standard_name, (standard_name,)):
            candidate = scene_dir / alias_name
            if candidate.exists():
                alias_source = candidate
                break

        if alias_source is None:
            continue

        ensure_dir_link(standard_path, alias_source)


def copy_or_link_scene(source_dir: Path, target_dir: Path) -> None:
    if target_dir.exists() or target_dir.is_symlink():
        raise RuntimeError(f"Target directory already exists: {target_dir}")

    shutil.copytree(source_dir, target_dir, dirs_exist_ok=False)
    prepare_scene_layout(target_dir)


def extract_zip(source_zip: Path, output_root: Path, scene_id: str | None, force: bool) -> Path:
    with tempfile.TemporaryDirectory(prefix="hovsg_scene_") as tmpdir:
        tmp_root = Path(tmpdir)
        with zipfile.ZipFile(source_zip) as zf:
            zf.extractall(tmp_root)

        extracted_scene = choose_scene_dir(tmp_root, scene_id)
        target_dir = output_root / extracted_scene.name

        if target_dir.exists():
            if not force:
                raise RuntimeError(f"Target directory already exists: {target_dir}. Use --force to replace it.")
            shutil.rmtree(target_dir)

        shutil.copytree(extracted_scene, target_dir)
        prepare_scene_layout(target_dir)
        return target_dir


def main() -> int:
    args = parse_args()
    source = args.source.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        print(f"Source path does not exist: {source}", file=sys.stderr)
        return 1

    try:
        if source.is_dir():
            scene_dir = choose_scene_dir(source, args.scene_id)
            target_dir = output_root / scene_dir.name
            if target_dir.exists():
                if not args.force:
                    raise RuntimeError(f"Target directory already exists: {target_dir}. Use --force to replace it.")
                shutil.rmtree(target_dir)
            copy_or_link_scene(scene_dir, target_dir)
        else:
            if not zipfile.is_zipfile(source):
                raise RuntimeError(f"Source is neither a directory nor a zip archive: {source}")
            target_dir = extract_zip(source, output_root, args.scene_id, args.force)
    except Exception as exc:  # pragma: no cover - surfaced to the user directly.
        print(f"Failed to prepare scene: {exc}", file=sys.stderr)
        return 1

    print(f"Prepared scene at: {target_dir}")
    print("Expected structure:")
    for name in STANDARD_DIRS:
        print(f"  - {target_dir / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
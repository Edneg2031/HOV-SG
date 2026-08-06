#!/usr/bin/env python3
"""Batch-extract HM3D-Omni scenes into this project without converting files."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


DEFAULT_DATASET_ROOT = Path("/home/bod/184Nas/open_source/hm3d_omni_dataset")
DEFAULT_OUTPUT_ROOT = Path("data/hm3d_omni")
DEFAULT_MODALITIES = (
    "rgb",
    "depth_zbuffer",
    "depth_euclidean",
    "mask_valid",
    "point_info",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one or more HM3D-Omni scenes from per-modality ZIP files."
    )
    parser.add_argument(
        "scenes",
        nargs="+",
        help="Scene IDs or ZIP names, e.g. 00127-EN7GiDgxdQ2 00128-pAjDzi9kWjE.",
    )
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--modalities",
        nargs="+",
        default=list(DEFAULT_MODALITIES),
        help="Modalities to extract (default: all five directories shown on the server).",
    )
    parser.add_argument("--force", action="store_true", help="Replace already extracted modality folders.")
    return parser.parse_args()


def normalized_scene(value: str) -> str:
    scene = Path(value).name
    if scene.lower().endswith(".zip"):
        scene = scene[:-4]
    if not scene or scene in {".", ".."} or "/" in scene or "\\" in scene:
        raise ValueError(f"invalid scene ID: {value}")
    return scene


def safe_extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"unsafe ZIP path in {archive}: {member.filename}")
        zipped.extractall(destination)


def unwrap_single_directory(directory: Path) -> None:
    """Remove redundant archive wrapper directories while preserving all files."""
    while True:
        entries = list(directory.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            return
        wrapper = entries[0]
        temporary = directory.parent / f".{directory.name}_unwrap"
        if temporary.exists():
            shutil.rmtree(temporary)
        wrapper.rename(temporary)
        directory.rmdir()
        temporary.rename(directory)


def extract_modality(
    dataset_root: Path,
    output_root: Path,
    scene: str,
    modality: str,
    force: bool,
) -> int:
    archive = dataset_root / modality / f"{scene}.zip"
    destination = output_root / scene / modality
    if not archive.is_file():
        raise RuntimeError(f"archive does not exist: {archive}")
    if not zipfile.is_zipfile(archive):
        raise RuntimeError(f"invalid ZIP archive: {archive}")
    if destination.exists() and not force:
        print(f"  skip {modality}: already exists")
        return sum(1 for path in destination.rglob("*") if path.is_file())

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{scene}_{modality}_", dir=destination.parent) as temp:
        staging = Path(temp) / modality
        staging.mkdir()
        safe_extract(archive, staging)
        unwrap_single_directory(staging)
        count = sum(1 for path in staging.rglob("*") if path.is_file())
        if count == 0:
            raise RuntimeError(f"archive contains no files: {archive}")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(staging), destination)
    print(f"  extracted {modality}: {count} files")
    return count


def main() -> int:
    args = parse_args()
    dataset_root = args.dataset_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    failures: list[str] = []

    try:
        scenes = list(dict.fromkeys(normalized_scene(value) for value in args.scenes))
    except ValueError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 2

    for scene in scenes:
        print(f"[{scene}]")
        for modality in args.modalities:
            try:
                extract_modality(dataset_root, output_root, scene, modality, args.force)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                message = f"{scene}/{modality}: {exc}"
                failures.append(message)
                print(f"  ERROR: {exc}", file=sys.stderr)

    print(f"Output root: {output_root}")
    if failures:
        print(f"Completed with {len(failures)} failure(s):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"Done: extracted {len(scenes)} scene(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

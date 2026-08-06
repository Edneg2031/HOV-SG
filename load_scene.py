#!/usr/bin/env python3
"""Assemble one HM3D-Omni scene for HOV-SG from per-modality ZIPs.

Expected source layout (the layout shown on the data server)::

    DATASET_ROOT/
      rgb/00127-EN7GiDgxdQ2.zip
      depth_zbuffer/00127-EN7GiDgxdQ2.zip
      point_info/00127-EN7GiDgxdQ2.zip

The resulting directory contains ``rgb``, ``depth`` and ``pose``, which are
the names expected by ``hovsg/dataloader/hm3dsem.py``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


MODALITIES = {"rgb": "rgb", "point_info": "pose"}
ALLOWED_SUFFIXES = {
    "rgb": {".png", ".jpg", ".jpeg"},
    "depth": {".png", ".tif", ".tiff"},
    "pose": {".txt"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one scene from an HM3D-Omni per-modality dataset for HOV-SG."
    )
    parser.add_argument(
        "scene",
        help="Scene id/archive stem, for example 00127-EN7GiDgxdQ2 (a .zip suffix is accepted).",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("/home/bod/184Nas/open_source/hm3d_omni_dataset"),
        help="Directory containing rgb/, depth_zbuffer/ and point_info/ (server default shown).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/hm3dsem_walks/train"),
        help="Destination parent directory (default: data/hm3dsem_walks/train).",
    )
    parser.add_argument(
        "--depth-source",
        choices=("depth_euclidean", "depth_zbuffer"),
        default="depth_zbuffer",
        help="Depth modality to use. HOV-SG's pinhole back-projection expects z-buffer (camera-Z) depth.",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing destination scene.")
    parser.add_argument(
        "--keep-extra",
        action="store_true",
        help="Also extract mask_valid and the unused depth modality when present.",
    )
    return parser.parse_args()


def safe_extract(archive: Path, destination: Path) -> None:
    """Extract without permitting absolute paths or ``..`` traversal."""
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            member_path = (destination / member.filename).resolve()
            if member_path != destination_resolved and destination_resolved not in member_path.parents:
                raise RuntimeError(f"unsafe path in {archive}: {member.filename}")
        zipped.extractall(destination)


def collect_files(extracted: Path, output: Path, output_name: str) -> int:
    """Flatten wrapper/scene directories because the HOV-SG loader is non-recursive."""
    allowed = ALLOWED_SUFFIXES.get(output_name)
    files = sorted(
        path for path in extracted.rglob("*")
        if path.is_file() and (allowed is None or path.suffix.lower() in allowed)
    )
    if not files:
        suffix_hint = ", ".join(sorted(allowed or ())) or "any file"
        raise RuntimeError(f"no {output_name} files ({suffix_hint}) found after extraction")

    output.mkdir(parents=True)
    seen: set[str] = set()
    for source in files:
        if source.name in seen:
            raise RuntimeError(f"duplicate flattened filename in {output_name}: {source.name}")
        seen.add(source.name)
        shutil.move(str(source), output / source.name)
    return len(files)


def validate_pose_file(path: Path) -> None:
    try:
        values = [float(value) for value in path.read_text(encoding="utf-8").split()]
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError(f"pose file is not whitespace-separated numeric text: {path.name}") from exc
    if len(values) != 16:
        raise RuntimeError(f"pose file must contain 16 numbers for a 4x4 matrix: {path.name} has {len(values)}")


def archive_for(root: Path, modality: str, scene: str) -> Path:
    archive = root / modality / f"{scene}.zip"
    if not archive.is_file():
        raise RuntimeError(f"missing archive: {archive}")
    if not zipfile.is_zipfile(archive):
        raise RuntimeError(f"not a valid ZIP archive: {archive}")
    return archive


def main() -> int:
    args = parse_args()
    scene = Path(args.scene).name
    if scene.lower().endswith(".zip"):
        scene = scene[:-4]
    if not scene or scene in {".", ".."} or "/" in scene or "\\" in scene:
        print(f"Invalid scene id: {args.scene}", file=sys.stderr)
        return 2

    dataset_root = args.dataset_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    target = output_root / scene
    modality_map = dict(MODALITIES)
    modality_map[args.depth_source] = "depth"
    if args.keep_extra:
        modality_map["mask_valid"] = "mask_valid"
        other_depth = "depth_zbuffer" if args.depth_source == "depth_euclidean" else "depth_euclidean"
        modality_map[other_depth] = other_depth

    try:
        archives = {name: archive_for(dataset_root, name, scene) for name in modality_map}
        if target.exists() and not args.force:
            raise RuntimeError(f"destination already exists: {target} (pass --force to replace it)")

        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"hovsg_{scene}_", dir=output_root) as temp_name:
            staging = Path(temp_name) / scene
            counts: dict[str, int] = {}
            for modality, output_name in modality_map.items():
                extracted = Path(temp_name) / f"extract_{modality}"
                extracted.mkdir()
                safe_extract(archives[modality], extracted)
                counts[output_name] = collect_files(extracted, staging / output_name, output_name)

            required_counts = {name: counts[name] for name in ("rgb", "depth", "pose")}
            if len(set(required_counts.values())) != 1:
                details = ", ".join(f"{name}={count}" for name, count in required_counts.items())
                raise RuntimeError(f"frame counts do not match: {details}")
            for pose in sorted((staging / "pose").iterdir()):
                validate_pose_file(pose)

            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(staging), target)

    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 1

    print(f"Prepared {scene}: {counts['rgb']} aligned RGB-D-pose frames")
    print(f"Scene path: {target}")
    print("Run HOV-SG with:")
    print(
        "  python application/create_graph.py "
        f"main.dataset=hm3dsem main.split={target.parent.name} "
        f"main.scene_id={scene} main.dataset_path={target.parent.parent}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

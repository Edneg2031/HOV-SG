#!/usr/bin/env python3
"""Convert one processed ScanNet++ pinhole scene into HOV-SG RGB-D input."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ScanNet++ aligned scenes use Z as the gravity/up axis. HOV-SG floor and room
# segmentation use Y as height. This proper rotation maps (x, y, z) to
# (x, z, -y) while preserving handedness.
Z_UP_TO_Y_UP = np.array(
    [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, -1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert one vggtSam/StreamVGGT processed ScanNet++ scene for HOV-SG."
    )
    parser.add_argument(
        "source_scene",
        type=Path,
        help="Scene directory containing images/, depth/ and scene_metadata.npz.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/scannetpp_hovsg"),
        help="HOV-SG dataset root (default: data/scannetpp_hovsg).",
    )
    parser.add_argument("--split", default="test", help="Output split name (default: test).")
    parser.add_argument("--scene-id", default=None, help="Output scene id; defaults to source folder name.")
    parser.add_argument("--stride", type=int, default=1, help="Keep every Nth frame.")
    parser.add_argument("--max-frames", type=int, default=0, help="Maximum frames after striding; 0 means all.")
    parser.add_argument("--copy", action="store_true", help="Copy RGB/depth instead of making symlinks.")
    parser.add_argument("--force", action="store_true", help="Replace an existing output scene.")
    return parser.parse_args()


def locate_file(directory: Path, stem: str, suffixes: tuple[str, ...]) -> Path:
    for suffix in suffixes:
        candidate = directory / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    matches = [path for path in directory.glob(f"{stem}.*") if path.is_file()]
    raise RuntimeError(
        f"could not uniquely locate {stem!r} in {directory}; candidates: "
        + ", ".join(path.name for path in matches)
    )


def link_or_copy(source: Path, destination: Path, copy: bool) -> None:
    if copy:
        shutil.copy2(source, destination)
    else:
        destination.symlink_to(source.resolve())


def validate_pose(pose: np.ndarray, frame_name: str) -> None:
    if pose.shape != (4, 4) or not np.isfinite(pose).all():
        raise RuntimeError(f"invalid 4x4 pose for {frame_name}: shape={pose.shape}")
    if not np.allclose(pose[3], [0, 0, 0, 1], atol=1e-5):
        raise RuntimeError(f"invalid homogeneous pose row for {frame_name}: {pose[3]}")
    rotation = pose[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=2e-3):
        raise RuntimeError(f"pose rotation is not orthonormal for {frame_name}")


def resolve_record_path(value: str, manifest_path: Path) -> Path:
    path = Path(value).expanduser()
    candidates = (
        [path]
        if path.is_absolute()
        else [Path.cwd() / path, *(parent / path for parent in manifest_path.parents)]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise RuntimeError(f"could not resolve manifest path: {value}")


def qvec_to_rotation(qvec: np.ndarray) -> np.ndarray:
    qvec = np.asarray(qvec, dtype=np.float64)
    qvec /= np.linalg.norm(qvec)
    w, x, y, z = qvec
    return np.array(
        [
            [1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * w * z, 2 * z * x + 2 * w * y],
            [2 * x * y + 2 * w * z, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * w * x],
            [2 * z * x - 2 * w * y, 2 * y * z + 2 * w * x, 1 - 2 * x * x - 2 * y * y],
        ]
    )


def find_colmap_text_dir(root: Path) -> Path:
    for candidate in (root, root / "0", root / "sparse" / "0", root / "text"):
        if (candidate / "cameras.txt").is_file() and (candidate / "images.txt").is_file():
            return candidate
    raise RuntimeError(f"COLMAP cameras.txt/images.txt not found below {root}")


def read_colmap_model(colmap_root: Path) -> tuple[dict[int, dict], dict[str, dict]]:
    model = find_colmap_text_dir(colmap_root)
    cameras: dict[int, dict] = {}
    for line in (model / "cameras.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        cameras[int(parts[0])] = {
            "model": parts[1], "width": int(parts[2]), "height": int(parts[3]),
            "params": np.asarray(parts[4:], dtype=np.float64),
        }
    lines = [
        line.strip() for line in (model / "images.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    images: dict[str, dict] = {}
    index = 0
    while index < len(lines):
        parts = lines[index].split()
        if len(parts) >= 10:
            name = " ".join(parts[9:])
            record = {
                "qvec": np.asarray(parts[1:5], dtype=np.float64),
                "tvec": np.asarray(parts[5:8], dtype=np.float64),
                "camera_id": int(parts[8]),
            }
            images[name] = record
            images[Path(name).name] = record
            index += 2
        else:
            index += 1
    return cameras, images


def intrinsics_from_colmap(camera: dict, width: int, height: int) -> np.ndarray:
    model, params = camera["model"], camera["params"].copy()
    sx, sy = width / camera["width"], height / camera["height"]
    if model in {"PINHOLE", "OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV", "FOV", "THIN_PRISM_FISHEYE"}:
        fx, fy, cx, cy = params[:4]
    elif model in {"SIMPLE_PINHOLE", "SIMPLE_RADIAL", "RADIAL", "SIMPLE_RADIAL_FISHEYE", "RADIAL_FISHEYE"}:
        if abs(sx - sy) > 1e-6:
            raise RuntimeError(f"cannot anisotropically resize {model}")
        fx, cx, cy = params[:3]
        fy = fx
    else:
        raise RuntimeError(f"unsupported COLMAP camera model: {model}")
    # COLMAP/rasterizer pixel centers are offset by +0.5 from OpenCV indexing.
    return np.array([[fx * sx, 0, cx * sx - 0.5], [0, fy * sy, cy * sy - 0.5], [0, 0, 1]])


def load_vggtsam_manifest(source: Path) -> list[dict]:
    manifest_path = source / "scene_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene_root = resolve_record_path(manifest["scene_root"], manifest_path)
    cameras, colmap_images = read_colmap_model(scene_root / "colmap")
    frames = []
    for record in manifest.get("frames", []):
        image_name = record.get("image_name") or Path(record["image_path"]).name
        colmap = colmap_images.get(image_name) or colmap_images.get(Path(image_name).name)
        if colmap is None:
            raise RuntimeError(f"frame not found in COLMAP images.txt: {image_name}")
        rgb_path = resolve_record_path(record["image_path"], manifest_path)
        raster_value = record.get("raster")
        if not raster_value:
            raise RuntimeError(f"frame has no raster/z-buffer; rerun preprocessing with --save-raster: {image_name}")
        raster_path = resolve_record_path(raster_value, manifest_path)
        with Image.open(rgb_path) as image:
            width, height = image.size
        w2c = np.eye(4)
        w2c[:3, :3] = qvec_to_rotation(colmap["qvec"])
        w2c[:3, 3] = colmap["tvec"]
        frames.append(
            {
                "name": image_name,
                "rgb": rgb_path,
                "raster": raster_path,
                "pose": np.linalg.inv(w2c),
                "intrinsics": intrinsics_from_colmap(cameras[colmap["camera_id"]], width, height),
            }
        )
    if not frames:
        raise RuntimeError(f"no frames found in {manifest_path}")
    return frames


def main() -> int:
    args = parse_args()
    if args.stride < 1 or args.max_frames < 0:
        print("Failed: --stride must be >= 1 and --max-frames must be >= 0", file=sys.stderr)
        return 2

    source = args.source_scene.expanduser().resolve()
    scene_id = args.scene_id or source.name
    target = args.output_root.expanduser().resolve() / args.split / scene_id
    metadata_path = source / "new_scene_metadata.npz"
    if not metadata_path.is_file():
        metadata_path = source / "scene_metadata.npz"
    target_created = False

    try:
        if not source.is_dir():
            raise RuntimeError(f"source scene does not exist: {source}")
        manifest_mode = not metadata_path.is_file() and (source / "scene_manifest.json").is_file()
        if not metadata_path.is_file() and not manifest_mode:
            raise RuntimeError(f"missing scene_metadata.npz or scene_manifest.json in {source}")
        if target.exists() and not args.force:
            raise RuntimeError(f"output already exists: {target} (use --force to replace it)")

        manifest_frames = load_vggtsam_manifest(source) if manifest_mode else None
        if not manifest_mode:
            with np.load(metadata_path, allow_pickle=True) as payload:
                images = np.asarray(payload["images"]).astype(str)
                trajectories = np.asarray(payload["trajectories"], dtype=np.float64)
                intrinsics = np.asarray(payload["intrinsics"], dtype=np.float64)
            if trajectories.shape != (len(images), 4, 4):
                raise RuntimeError(
                    f"trajectories must be [N,4,4], got {trajectories.shape} for {len(images)} images"
                )
            if intrinsics.shape != (len(images), 3, 3):
                raise RuntimeError(
                    f"intrinsics must be [N,3,3], got {intrinsics.shape} for {len(images)} images"
                )
        else:
            images = np.asarray([frame["name"] for frame in manifest_frames])

        indices = list(range(0, len(images), args.stride))
        if args.max_frames:
            indices = indices[: args.max_frames]
        if not indices:
            raise RuntimeError("no frames selected")

        if target.exists():
            shutil.rmtree(target)
        for name in ("rgb", "depth", "pose", "intrinsics"):
            (target / name).mkdir(parents=True, exist_ok=True)
        target_created = True

        source_frames: list[dict[str, object]] = []
        expected_size: tuple[int, int] | None = None
        for output_index, source_index in enumerate(indices):
            source_name = images[source_index]
            if manifest_mode:
                frame = manifest_frames[source_index]
                rgb_source = frame["rgb"]
                depth_source = None
                pose = frame["pose"]
                intrinsic = frame["intrinsics"].copy()
            else:
                rgb_source = locate_file(source / "images", source_name, (".jpg", ".png", ".jpeg"))
                depth_source = locate_file(source / "depth", source_name, (".png", ".tif", ".tiff"))
                pose = trajectories[source_index]
                intrinsic = intrinsics[source_index].copy()
            output_stem = f"{output_index:06d}"

            with Image.open(rgb_source) as rgb_image:
                if manifest_mode:
                    with np.load(frame["raster"]) as raster:
                        zbuf = np.asarray(raster["zbuf"], dtype=np.float32)
                    zbuf[~np.isfinite(zbuf) | (zbuf <= 0)] = 0
                    if np.nanmax(zbuf, initial=0) >= 65.535:
                        raise RuntimeError(f"depth exceeds uint16 millimeter range for {source_name}")
                    depth_array = np.rint(zbuf * 1000.0).astype(np.uint16)
                    depth_size = (depth_array.shape[1], depth_array.shape[0])
                else:
                    with Image.open(depth_source) as depth_image:
                        depth_size = depth_image.size
                        if depth_image.mode not in {"I;16", "I;16B", "I;16L", "I"}:
                            raise RuntimeError(f"depth is not an integer depth image for {source_name}: {depth_image.mode}")
                if rgb_image.size != depth_size:
                    raise RuntimeError(
                        f"RGB/depth size mismatch for {source_name}: {rgb_image.size} vs {depth_size}"
                    )
                if expected_size is None:
                    expected_size = rgb_image.size
                elif rgb_image.size != expected_size:
                    raise RuntimeError(
                        f"frame size changes at {source_name}: {rgb_image.size} vs {expected_size}"
                    )

            validate_pose(pose, source_name)
            pose = Z_UP_TO_Y_UP @ pose
            validate_pose(pose, source_name)
            if not np.isfinite(intrinsic).all() or intrinsic[0, 0] <= 0 or intrinsic[1, 1] <= 0:
                raise RuntimeError(f"invalid intrinsics for {source_name}")
            if not manifest_mode:
                # StreamVGGT preprocessing stores COLMAP pixel-center intrinsics.
                intrinsic[0, 2] -= 0.5
                intrinsic[1, 2] -= 0.5

            link_or_copy(rgb_source, target / "rgb" / f"{output_stem}{rgb_source.suffix.lower()}", args.copy)
            if manifest_mode:
                Image.fromarray(depth_array).save(target / "depth" / f"{output_stem}.png")
            else:
                link_or_copy(depth_source, target / "depth" / f"{output_stem}{depth_source.suffix.lower()}", args.copy)
            np.savetxt(target / "pose" / f"{output_stem}.txt", pose, fmt="%.10g")
            np.savetxt(target / "intrinsics" / f"{output_stem}.txt", intrinsic, fmt="%.10g")
            source_frames.append({"output_frame": output_stem, "source_index": source_index, "source_name": source_name})

        width, height = expected_size or (0, 0)
        metadata = {
            "scene_id": scene_id,
            "source_scene": str(source),
            "source_metadata": str(source / "scene_manifest.json" if manifest_mode else metadata_path),
            "source_format": "vggtsam_manifest_raster" if manifest_mode else "streamvggt_scene_metadata",
            "frame_count": len(indices),
            "width": width,
            "height": height,
            "depth_unit": "millimeter",
            "depth_scale": 1000.0,
            "depth_type": "z_depth",
            "pose_type": "camera_to_world",
            "camera_coordinates": "opencv",
            "source_world_up_axis": "+Z",
            "world_up_axis": "+Y",
            "world_transform": "(x, y, z) -> (x, z, -y)",
            "intrinsics_coordinates": "opencv",
            "rgb_depth_registered": True,
            "stride": args.stride,
            "frames": source_frames,
        }
        (target / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        if target_created and target.exists():
            shutil.rmtree(target)
        print(f"Failed: {exc}", file=sys.stderr)
        return 1

    print(f"Converted {len(indices)} frames: {target}")
    print("HOV-SG arguments:")
    print(f"  main.dataset=hm3dsem main.dataset_path={target.parent.parent}")
    print(f"  main.split={args.split} main.scene_id={scene_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

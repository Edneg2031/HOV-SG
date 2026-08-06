"""
    Habitat Matterport 3D Semantics dataset loader.
"""

import sys
import os
import math
import json
import numpy as np
from pathlib import Path
from PIL import Image
import open3d as o3d

from hovsg.dataloader.generic import RGBDDataset

# pylint: disable=all

class HM3DSemDataset(RGBDDataset):
    """
    Dataset class for the Habitat Matterport3D Semantic dataset.

    This class provides an interface to load RGB-D data samples from the ScanNet
    dataset. The dataset format is assumed to follow the ScanNet v2 dataset format.
    """    
    def __init__(self, cfg):
        """
        Args:
            root_dir: Path to the root directory containing the dataset.
            transforms: Optional transformations to apply to the data.
        """
        self.root_dir = cfg["root_dir"]
        self.transforms = cfg["transforms"]
        metadata_path = Path(self.root_dir) / "metadata.json"
        self.metadata = {}
        if metadata_path.is_file():
            with metadata_path.open("r", encoding="utf-8") as handle:
                self.metadata = json.load(handle)
        self.pose_coordinates = self.metadata.get("camera_coordinates", "opengl")
        super(HM3DSemDataset, self).__init__(cfg)
        self.scale = float(self.metadata.get("depth_scale", 1000.0))
        self.data_list = self._get_data_list()
        self.rgb_H = self._load_image(self.data_list[0][0]).size[1]
        self.rgb_W = self._load_image(self.data_list[0][0]).size[0]
        self.depth_intrinsics = self._intrinsics_for_sample(self.data_list[0])
    
    def __getitem__(self, idx):
        """
        Get a data sample based on the given index.

        Args:
            idx: Index of the data sample.

        Returns:
            RGB image and depth image as numpy arrays.
        """
        rgb_path, depth_path, pose_path, intrinsics_path = self.data_list[idx]
        rgb_image = self._load_image(rgb_path)
        depth_image = self._load_depth(depth_path)
        pose = self._load_pose(pose_path)
        depth_intrinsics = self._load_depth_intrinsics(intrinsics_path)
        self.depth_intrinsics = depth_intrinsics
        if self.transforms is not None:
            rgb_image = self.transforms(rgb_image)
            depth_image = self.transforms(depth_image)   
        return rgb_image, depth_image, pose, list(), depth_intrinsics
    
    def _get_data_list(self):
        """
        Get a list of RGB-D data samples based on the dataset format and mode.

        Returns:
            List of RGB-D data samples (RGB image path, depth image path).
        """
        root = Path(self.root_dir)
        suffixes = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
        rgb = {path.stem: path for path in (root / "rgb").iterdir() if path.is_file() and path.suffix.lower() in suffixes}
        depth = {path.stem: path for path in (root / "depth").iterdir() if path.is_file() and path.suffix.lower() in suffixes}
        pose = {path.stem: path for path in (root / "pose").iterdir() if path.is_file() and path.suffix.lower() == ".txt"}
        intrinsics_dir = root / "intrinsics"
        intrinsics = (
            {path.stem: path for path in intrinsics_dir.iterdir() if path.is_file() and path.suffix.lower() == ".txt"}
            if intrinsics_dir.is_dir()
            else {}
        )
        stems = set(rgb) & set(depth) & set(pose)
        if not stems:
            raise RuntimeError(f"No aligned RGB-depth-pose frames found in {root}")
        if set(rgb) != stems or set(depth) != stems or set(pose) != stems:
            raise RuntimeError(
                f"RGB/depth/pose frame ids do not match: rgb={len(rgb)}, depth={len(depth)}, pose={len(pose)}"
            )
        if intrinsics and set(intrinsics) != stems:
            raise RuntimeError(f"Per-frame intrinsics do not match the {len(stems)} frame ids")
        return [
            (str(rgb[stem]), str(depth[stem]), str(pose[stem]), str(intrinsics[stem]) if intrinsics else None)
            for stem in sorted(stems)
        ]
        
    def _load_image(self, path):
        """
        Load the RGB image from the given path.

        Args:
            path: Path to the RGB image file.

        Returns:
            RGB image as a numpy array.
        """
        # Load the RGB image using PIL
        rgb_image = Image.open(path)
        return rgb_image

    def _load_depth(self, path):
        """
        Load the depth image from the given path.

        Args:
            path: Path to the depth image file.

        Returns:
            Depth image as a numpy array.
        """
        # Load the depth image using OpenCV
        depth_image = Image.open(path)
        return depth_image
    
    def _load_pose(self, path):
        """
        Load the camera pose from the given path.

        Args:
            path: Path to the camera pose file.

        Returns:
            Camera pose as a numpy array (4x4 matrix).
        """
        with open(path, "r") as file:
            values = [float(val) for val in file.read().split()]
            if len(values) != 16:
                raise ValueError(
                    f"Pose file must contain 16 numeric values, got {len(values)}: {path}"
                )
            transformation_matrix = np.array(values).reshape((4, 4))
            if self.pose_coordinates == "opengl":
                C = np.eye(4)
                C[1, 1] = -1
                C[2, 2] = -1
                transformation_matrix = np.matmul(transformation_matrix, C)
            elif self.pose_coordinates != "opencv":
                raise ValueError(f"Unsupported camera_coordinates: {self.pose_coordinates}")
        return transformation_matrix
    
    def _load_depth_intrinsics(self, path=None):
        """
        Load the depth camera intrinsics.

        Returns:
            Depth camera intrinsics as a numpy array (3x3 matrix).
        """        
        if path is not None:
            matrix = np.loadtxt(path, dtype=np.float64)
            if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
                raise ValueError(f"Invalid 3x3 intrinsics: {path}")
            return matrix
        H, W = self.rgb_H, self.rgb_W
        hfov = 90 * np.pi / 180
        vfov = 2 * math.atan(np.tan(hfov / 2) * H / W)
        fx = W / (2.0 * np.tan(hfov / 2.0))
        fy = H / (2.0 * np.tan(vfov / 2.0))
        cx = W / 2
        cy = H / 2
        depth_camera_matrix = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])
        return depth_camera_matrix

    def _intrinsics_for_sample(self, sample):
        return self._load_depth_intrinsics(sample[3])

    def create__pcd(self, rgb, depth, camera_pose=None):
        """
        Create a point cloud from RGB-D images.

        Args:
            rgb: RGB image as a numpy array.
            depth: Depth image as a numpy array.
            camera_pose: Camera pose as a numpy array (4x4 matrix).

        Returns:
            Point cloud as an Open3D object.
        """
        # convert rgb and depth images to numpy arrays
        rgb = np.array(rgb)
        depth = np.array(depth)
        # load depth camera intrinsics
        H = rgb.shape[0]
        W = rgb.shape[1]
        camera_matrix = self.depth_intrinsics
        # create point cloud
        y, x = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
        depth = depth.astype(np.float32) / 1000.0
        mask = depth > 0
        x = x[mask]
        y = y[mask]
        depth = depth[mask]
        # convert to 3D
        X = (x - camera_matrix[0, 2]) * depth / camera_matrix[0, 0]
        Y = (y - camera_matrix[1, 2]) * depth / camera_matrix[1, 1]
        Z = depth
        # convert to open3d point cloud
        points = np.hstack((X.reshape(-1, 1), Y.reshape(-1, 1), Z.reshape(-1, 1)))
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        colors = rgb[mask]
        pcd.colors = o3d.utility.Vector3dVector(colors / 255.0)
        pcd.transform(camera_pose)
        return pcd
    

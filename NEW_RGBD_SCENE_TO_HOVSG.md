# 新 RGB-D 场景接入与运行 HOV-SG

本文用于把任意新场景整理成当前 HOV-SG 可读取的格式，然后完成点云、物体、楼层、房间
和导航图构建。环境和两个模型权重假定已经配置完成。

## 1. 每个场景必须提供的数据

每一帧需要四项数据，且必须一一对应：

| 数据 | 要求 |
|---|---|
| RGB | JPG 或 PNG，建议 RGB 三通道 |
| Depth | 与 RGB 已配准的相机 Z-depth，不是欧氏射线距离 |
| Pose | 4×4 camera-to-world 矩阵，单位为米 |
| Intrinsics | 与当前图像分辨率对应的 3×3 OpenCV 相机内参 |

不需要提供 mesh、真值语义标签、实例标签、房间标签或楼层标签。SAM 从 RGB 生成 mask，
OpenCLIP生成视觉语义特征，RGB-D 几何负责三维构建。

## 2. 数据约定

### RGB 与 Depth

- RGB 和 depth 必须像素对齐且分辨率相同。
- Depth 保存为单通道 uint16 PNG。
- 当前推荐单位为毫米，`0` 表示无效深度。
- `metadata.json` 中对应设置 `"depth_scale": 1000.0`。
- 例如真实深度 `1.234m` 应保存为数值 `1234`。
- uint16 毫米深度最大约为 `65.535m`，足够普通室内场景。

若原始 depth 是米制 float32：

```python
depth_mm = np.rint(depth_m * 1000.0).astype(np.uint16)
```

转换前必须先将 NaN、Inf、负值及超量程深度置零。

### 相机内参

每帧内参文件为：

```text
fx  0  cx
0  fy  cy
0   0   1
```

采用 OpenCV 像素坐标约定。如果 RGB/depth 被缩放，必须同步缩放 `fx、fy、cx、cy`。

### 相机位姿

每帧 pose 必须是 4×4 camera-to-world：

```text
R00 R01 R02 tx
R10 R11 R12 ty
R20 R21 R22 tz
0   0   0   1
```

- 平移单位为米。
- 如果来源提供 world-to-camera，需要先求逆：`T_c2w = inv(T_w2c)`。
- 相机坐标采用 OpenCV：X 向右、Y 向下、Z 向前。
- 世界坐标必须是 Y-up：Y 为高度，X-Z 为地面平面。

若原始世界坐标是 Z-up，对每个 camera-to-world pose 左乘：

```python
Z_UP_TO_Y_UP = np.array([
    [1,  0, 0, 0],
    [0,  0, 1, 0],
    [0, -1, 0, 0],
    [0,  0, 0, 1],
], dtype=float)

pose_y_up = Z_UP_TO_Y_UP @ pose_z_up
```

对应世界坐标变换为 `(x, y, z) → (x, z, -y)`。RGB、depth 和内参不需要旋转。

## 3. HOV-SG 目录结构

为每个新场景选择唯一的 `SCENE_ID`，例如 `my_scene_001`：

```text
data/custom_rgbd/
└── test/
    └── my_scene_001/
        ├── rgb/
        │   ├── 000000.jpg
        │   ├── 000001.jpg
        │   └── ...
        ├── depth/
        │   ├── 000000.png
        │   ├── 000001.png
        │   └── ...
        ├── pose/
        │   ├── 000000.txt
        │   ├── 000001.txt
        │   └── ...
        ├── intrinsics/
        │   ├── 000000.txt
        │   ├── 000001.txt
        │   └── ...
        └── metadata.json
```

四个目录中的文件名 stem 必须完全一致。可以使用六位编号，也可以使用其他名称，但排序
后必须保持正确的时间顺序。推荐统一使用 `000000、000001、...`。

如果所有帧内参相同，仍建议为每一帧复制一个同名内参文件。

## 4. 创建 metadata.json

在场景根目录创建：

```json
{
  "scene_id": "my_scene_001",
  "frame_count": 300,
  "depth_unit": "millimeter",
  "depth_scale": 1000.0,
  "depth_type": "z_depth",
  "pose_type": "camera_to_world",
  "camera_coordinates": "opencv",
  "world_up_axis": "+Y",
  "intrinsics_coordinates": "opencv",
  "rgb_depth_registered": true
}
```

`frame_count` 改为实际数量。如果从 Z-up 转换而来，可以额外记录：

```json
"source_world_up_axis": "+Z",
"world_transform": "(x, y, z) -> (x, z, -y)"
```

## 5. 设置新场景变量

以下路径在服务器执行，根据实际场景修改前四项：

```bash
cd /home/wlh50060092/HOV-SG
conda activate hovsg

export HOVSG_ROOT=/home/wlh50060092/HOV-SG
export SCENE_ID=my_scene_001
export HOVSG_DATA_ROOT=$HOVSG_ROOT/data/custom_rgbd
export CONVERTED_SCENE=$HOVSG_DATA_ROOT/test/$SCENE_ID
export HOVSG_OUTPUT_ROOT=$HOVSG_ROOT/data/custom_scene_graphs
export SCENE_GRAPH_DIR=$HOVSG_OUTPUT_ROOT/hm3dsem/$SCENE_ID

test -d "$CONVERTED_SCENE" || { echo "ERROR: $CONVERTED_SCENE not found"; return 1 2>/dev/null || exit 1; }
```

虽然数据是自定义 RGB-D，运行时仍使用当前已经扩展过的 `hm3dsem` loader。

## 6. 运行前自动校验

```bash
python - "$CONVERTED_SCENE" <<'PY'
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

scene = Path(sys.argv[1])
allowed_rgb = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
allowed_depth = allowed_rgb

def indexed(folder, suffixes):
    return {
        p.stem: p for p in (scene / folder).iterdir()
        if p.is_file() and p.suffix.lower() in suffixes
    }

rgb = indexed("rgb", allowed_rgb)
depth = indexed("depth", allowed_depth)
pose = indexed("pose", {".txt"})
intrinsics = indexed("intrinsics", {".txt"})

stems = set(rgb)
assert stems, "no RGB frames"
assert set(depth) == stems, "RGB/depth frame ids differ"
assert set(pose) == stems, "RGB/pose frame ids differ"
assert set(intrinsics) == stems, "RGB/intrinsics frame ids differ"

metadata = json.loads((scene / "metadata.json").read_text(encoding="utf-8"))
assert metadata["camera_coordinates"] == "opencv"
assert metadata["pose_type"] == "camera_to_world"
assert metadata["world_up_axis"] == "+Y"
assert float(metadata["depth_scale"]) > 0

camera_centres = []
for stem in sorted(stems):
    with Image.open(rgb[stem]) as rgb_image, Image.open(depth[stem]) as depth_image:
        assert rgb_image.size == depth_image.size, f"size mismatch: {stem}"
        depth_array = np.asarray(depth_image)
        assert depth_array.ndim == 2, f"depth must be single channel: {stem}"
        assert depth_array.dtype == np.uint16, f"depth must be uint16: {stem}"

    T = np.loadtxt(pose[stem])
    K = np.loadtxt(intrinsics[stem])
    assert T.shape == (4, 4), f"bad pose shape: {stem}"
    assert K.shape == (3, 3), f"bad intrinsics shape: {stem}"
    assert np.isfinite(T).all() and np.isfinite(K).all(), f"NaN/Inf: {stem}"
    assert np.allclose(T[3], [0, 0, 0, 1]), f"bad pose last row: {stem}"
    assert np.allclose(T[:3, :3].T @ T[:3, :3], np.eye(3), atol=1e-3), f"bad rotation: {stem}"
    assert np.isclose(np.linalg.det(T[:3, :3]), 1, atol=1e-3), f"bad rotation determinant: {stem}"
    assert K[0, 0] > 0 and K[1, 1] > 0 and np.isclose(K[2, 2], 1), f"bad K: {stem}"
    camera_centres.append(T[:3, 3])

camera_centres = np.asarray(camera_centres)
print("frames:", len(stems))
print("first frame:", sorted(stems)[0])
print("camera XYZ min:", camera_centres.min(axis=0))
print("camera XYZ max:", camera_centres.max(axis=0))
print("camera Y median:", np.median(camera_centres[:, 1]))
print("Input validation: OK")
PY
```

校验通过不代表 pose 一定语义正确。还要确认相机 Y 大致是离地高度，并在生成点云后检查
多帧是否重影、尺度是否合理以及绿色 Y 轴是否竖直。

## 7. 第一次冒烟测试

先计算帧数：

```bash
export FRAME_COUNT=$(find "$CONVERTED_SCENE/rgb" -type f | wc -l | tr -d ' ')
echo "FRAME_COUNT=$FRAME_COUNT"
```

目标先处理约 6～12 帧。按数据量选择固定步长：

```text
30 帧：skip_frames=5
60 帧：skip_frames=10
120 帧：skip_frames=20
300 帧：skip_frames=50
600 帧：skip_frames=100
```

例如 300 帧场景先用 6 帧，只验证点云和物体，不构建层级图：

```bash
CUDA_VISIBLE_DEVICES=0 python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id="$SCENE_ID" \
  main.save_path="$HOVSG_OUTPUT_ROOT" \
  pipeline.skip_frames=50 \
  pipeline.create_graph=false \
  pipeline.denoise_full_pcd=false \
  pipeline.save_full_feats=false \
  pipeline.save_mask_feats=false \
  models.sam.points_per_side=6 \
  models.sam.points_per_batch=36
```

检查：

```bash
ls -lh "$SCENE_GRAPH_DIR/full_pcd.ply" "$SCENE_GRAPH_DIR/masked_pcd.ply"
```

在 MeshLab 中必须确认：

- 多帧点云正确对齐，没有明显双墙或重影；
- RGB 颜色与几何匹配；
- 尺度符合米制场景；
- 绿色 Y 轴竖直，地面位于 X-Z 平面；
- `masked_pcd.ply` 中存在合理的物体候选。

## 8. 完整 Scene Graph 测试

点云正确后换一个输出根目录，处理约 12～24 帧：

```bash
export HOVSG_OUTPUT_ROOT=$HOVSG_ROOT/data/custom_scene_graphs_hierarchy
export SCENE_GRAPH_DIR=$HOVSG_OUTPUT_ROOT/hm3dsem/$SCENE_ID
```

以下以 300 帧、每 25 帧取一张为例：

```bash
CUDA_VISIBLE_DEVICES=0 python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id="$SCENE_ID" \
  main.save_path="$HOVSG_OUTPUT_ROOT" \
  pipeline.skip_frames=25 \
  pipeline.create_graph=true \
  pipeline.denoise_full_pcd=false \
  pipeline.save_full_feats=false \
  pipeline.save_mask_feats=false \
  models.sam.points_per_side=6 \
  models.sam.points_per_batch=36
```

结果正常后可以逐步增加帧数或将 `points_per_side` 提高到 `12`。不要同时大幅增加帧数和
SAM 密度，否则无法判断耗时或结果变化来自哪个参数。

## 9. 查看结果

```bash
find "$SCENE_GRAPH_DIR" -maxdepth 3 -type f | sort
du -sh "$SCENE_GRAPH_DIR"
```

主要输出：

```text
full_pcd.ply       完整融合点云
masked_pcd.ply     物体候选点云
objects/           物体节点点云
floors/、rooms/    楼层和房间结果
nav_graph/         导航图
```

如果不保存 `.pt`，同一次运行仍可完成层级构图，但之后无法从特征缓存恢复，需要重新运行
SAM/OpenCLIP。

## 10. 同时运行多个新场景

每个场景必须有不同的 `SCENE_ID` 和输出目录。当前实现不会使用多 GPU 加速同一个场景，
但可以让不同 GPU 并行处理不同场景：

```bash
CUDA_VISIBLE_DEVICES=0 python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id=scene_a \
  main.save_path="$HOVSG_ROOT/data/output_scene_a" \
  pipeline.skip_frames=25 \
  pipeline.create_graph=true \
  pipeline.denoise_full_pcd=false \
  pipeline.save_full_feats=false \
  pipeline.save_mask_feats=false \
  models.sam.points_per_side=6 \
  models.sam.points_per_batch=36 \
  > "$HOVSG_ROOT/scene_a.log" 2>&1 &

CUDA_VISIBLE_DEVICES=1 python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id=scene_b \
  main.save_path="$HOVSG_ROOT/data/output_scene_b" \
  pipeline.skip_frames=25 \
  pipeline.create_graph=true \
  pipeline.denoise_full_pcd=false \
  pipeline.save_full_feats=false \
  pipeline.save_mask_feats=false \
  models.sam.points_per_side=6 \
  models.sam.points_per_batch=36 \
  > "$HOVSG_ROOT/scene_b.log" 2>&1 &
```

查看进程和日志：

```bash
jobs -l
tail -f "$HOVSG_ROOT/scene_a.log"
```

3D mask merging 主要消耗 CPU，多场景并行时还要观察 CPU 和内存，不要只看 GPU 是否空闲。

## 11. 常见错误定位

| 现象 | 优先检查 |
|---|---|
| 点云重影、双墙 | pose 类型、帧对应关系、depth 与 RGB 是否来自同一时刻 |
| 尺度错误 | depth 单位和 `depth_scale` |
| 点云朝向正确但楼层高度异常 | 是否仍为 Z-up；HOV-SG 要求 Y-up |
| `cannot reshape ... 4x4` | pose 是否完整包含 16 个数 |
| RGB/depth 数量不同 | 四类文件 stem 是否完全一致 |
| masked 点云很少 | 增加帧数或提高 SAM `points_per_side` |
| CPU 长时间 100%、GPU 0% | 通常处于 3D mask merging 或 DBSCAN，不是模型推理 |
| 导航 DBSCAN 收到 0 个 pose | 检查 pose 的 Y 高度、楼层边界以及新版导航回退代码 |

## 12. 推荐顺序

```text
整理 RGB/depth/pose/intrinsics
  → 创建 metadata.json
  → 运行全量输入校验
  → 6～12 帧且 create_graph=false 验证点云
  → MeshLab 确认对齐、尺度和 Y-up
  → 新输出目录运行 12～24 帧完整层级图
  → 检查 floor、room、object、nav graph
  → 单独增加帧数或提高 SAM 密度
```

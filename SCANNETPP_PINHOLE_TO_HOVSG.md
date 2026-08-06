# 使用 ScanNet++ Pinhole 数据测试 HOV-SG

本文档用于把 `vggtSam` 已处理的一个 ScanNet++ pinhole 场景转换为 HOV-SG 输入，
然后运行一次最小效果测试。

## 1. 数据对应关系

转换过程使用以下数据：

| vggtSam 数据 | HOV-SG 输入 |
|---|---|
| `image_path` 对应的 RGB | `rgb/*.jpg` |
| `raster/*.npz` 中的 `zbuf` | `depth/*.png` |
| COLMAP `images.txt` 中的 world-to-camera | `pose/*.txt` camera-to-world |
| COLMAP `cameras.txt` 中的相机参数 | `intrinsics/*.txt` |

转换器会完成：

- 将 `zbuf` 的米制 Z-depth 转为毫米制 uint16 PNG。
- 将 COLMAP world-to-camera 位姿转换为 4×4 camera-to-world 矩阵。
- 将 COLMAP 像素中心约定转换为 OpenCV 像素坐标约定。
- 检查 RGB 和 depth 分辨率。
- 检查位姿矩阵、旋转矩阵和相机内参是否合法。
- 给所有输出帧重新生成统一的六位数字 ID。

## 当前进度：600 帧已经转换成功后从这里继续

如果终端已经出现：

```text
Converted 600 frames: /home/wlh50060092/HOV-SG/data/scannetpp_hovsg/test/00a231a370
```

不需要再次转换。进入 HOV-SG 项目后，从本节开始逐段执行。

### 设置当前场景变量

```bash
cd /home/wlh50060092/HOV-SG
conda activate hovsg

export HOVSG_ROOT=/home/wlh50060092/HOV-SG
export SCENE_ID=00a231a370
export HOVSG_DATA_ROOT=$HOVSG_ROOT/data/scannetpp_hovsg
export HOVSG_OUTPUT_ROOT=$HOVSG_ROOT/data/scene_graphs
export CONVERTED_SCENE=$HOVSG_DATA_ROOT/test/$SCENE_ID

: "${CONVERTED_SCENE:?CONVERTED_SCENE is not set}"
test -d "$CONVERTED_SCENE" \
  && echo "converted scene: $CONVERTED_SCENE" \
  || { echo "ERROR: converted scene not found"; return 1 2>/dev/null || exit 1; }
```

### 检查四类输入数量

```bash
for MODALITY in rgb depth pose intrinsics; do
  printf '%-12s ' "$MODALITY"
  find "$CONVERTED_SCENE/$MODALITY" -type f | wc -l
done
```

预期结果：

```text
rgb          600
depth        600
pose         600
intrinsics   600
```

### 检查第一帧 RGB、Depth、Pose 和内参

```bash
python - "$CONVERTED_SCENE" <<'PY'
import sys
from pathlib import Path

import numpy as np
from PIL import Image

scene = Path(sys.argv[1])
rgb_path = sorted((scene / "rgb").iterdir())[0]
depth_path = sorted((scene / "depth").iterdir())[0]
pose_path = sorted((scene / "pose").iterdir())[0]
intrinsics_path = sorted((scene / "intrinsics").iterdir())[0]

rgb = Image.open(rgb_path)
depth = np.asarray(Image.open(depth_path))
pose = np.loadtxt(pose_path)
intrinsics = np.loadtxt(intrinsics_path)
valid = depth[depth > 0]

print("RGB:", rgb_path.name, rgb.size, rgb.mode)
print("Depth:", depth_path.name, (depth.shape[1], depth.shape[0]), depth.dtype)
print("Valid depth pixels:", valid.size)
if valid.size:
    print("Depth range (m):", float(valid.min()) / 1000.0, float(valid.max()) / 1000.0)
print("Pose shape:", pose.shape)
print(pose)
print("Intrinsics shape:", intrinsics.shape)
print(intrinsics)

assert rgb.size == (depth.shape[1], depth.shape[0])
assert pose.shape == (4, 4)
assert intrinsics.shape == (3, 3)
print("First-frame validation: OK")
PY
```

### 运行第一轮 HOV-SG 测试

当前有 600 帧，先设置 `pipeline.skip_frames=10`，实际处理约 60 帧。不要在第一次测试中
设置为 1，否则会对 600 帧执行点云融合、SAM 和 CLIP，耗时很长。

若终端出现 SciPy 要求 NumPy `<1.25.0` 的警告，说明 Habitat-Sim 安装过程换回了旧版
SciPy。先重新固定兼容版本：

```bash
python -m pip install --upgrade --force-reinstall \
  numpy==1.26.4 \
  scipy==1.13.1 \
  pillow==10.4.0 \
  imageio-ffmpeg

python - <<'PY'
import matplotlib
import numpy
import scipy

print("NumPy:", numpy.__version__)
print("SciPy:", scipy.__version__)
print("Matplotlib backend:", matplotlib.get_backend())
PY

python -m pip check
```

预期为 NumPy 1.26.4、SciPy 1.13.1、Matplotlib `agg`，并且 `pip check` 输出
`No broken requirements found`。Habitat-Sim 0.3.3 要求 Pillow 10.4.0 和
`imageio-ffmpeg`，因此这里同时固定安装。HOV-SG 已将导航图后端改为 `Agg`，服务器
不需要 Tk 或桌面显示。

```bash
python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id="$SCENE_ID" \
  main.save_path="$HOVSG_OUTPUT_ROOT" \
  pipeline.skip_frames=10 \
  pipeline.create_graph=false
```

### 检查运行输出

```bash
export SCENE_GRAPH_DIR=$HOVSG_OUTPUT_ROOT/hm3dsem/$SCENE_ID

find "$SCENE_GRAPH_DIR" -maxdepth 2 -type f | sort
ls -lh \
  "$SCENE_GRAPH_DIR/full_pcd.ply" \
  "$SCENE_GRAPH_DIR/masked_pcd.ply" \
  "$SCENE_GRAPH_DIR/full_feats.pt" \
  "$SCENE_GRAPH_DIR/mask_feats.pt"
```

第一次重点查看：

```text
full_pcd.ply
masked_pcd.ply
```

确认点云没有翻转、重影、尺度异常后，再继续本文档第 9 节的完整层级场景图测试。

## 2. 设置项目路径

在服务器终端中设置以下路径。只需要根据服务器的实际目录修改前两行：

```bash
export VGGT_SAM_ROOT=/home/wlh50060092/vggtSam
export HOVSG_ROOT=/home/wlh50060092/HOV-SG

export SCANNETPP_PROCESSED_ROOT=$VGGT_SAM_ROOT/data/processed/scannetpp_pinhole_2d
export HOVSG_DATA_ROOT=$HOVSG_ROOT/data/scannetpp_hovsg
export HOVSG_OUTPUT_ROOT=$HOVSG_ROOT/data/scene_graphs
```

确认两个项目存在：

```bash
test -d "$VGGT_SAM_ROOT" && echo "vggtSam directory: OK"
test -d "$HOVSG_ROOT" && echo "HOV-SG directory: OK"
```

## 3. 查找可用场景

列出已经完成 vggtSam pinhole 预处理的场景：

```bash
find "$SCANNETPP_PROCESSED_ROOT" \
  -mindepth 2 -maxdepth 2 \
  -name scene_manifest.json \
  -print | sort | head -20
```

本文档使用以下场景作为示例：

```bash
export SCENE_ID=00a231a370
export SOURCE_SCENE=$SCANNETPP_PROCESSED_ROOT/$SCENE_ID
```

如果实际场景 ID 不同，只需修改 `SCENE_ID`。

检查源场景：

```bash
test -f "$SOURCE_SCENE/scene_manifest.json" \
  && echo "scene manifest: OK" \
  || echo "ERROR: scene_manifest.json not found"

find "$SOURCE_SCENE" -maxdepth 2 -type f | sort | head -30
```

转换至少需要：

```text
scene_manifest.json
raster/<frame>.npz
```

`scene_manifest.json` 中引用的原始场景还需要包含：

```text
images/
colmap/cameras.txt
colmap/images.txt
```

如果缺少 `raster/*.npz`，需要在 vggtSam 中重新执行 ScanNet++ 预处理，并启用
`--save-raster`。

## 4. 激活 HOV-SG 环境

```bash
cd "$HOVSG_ROOT"
conda activate hovsg
```

确认转换器存在：

```bash
test -f convert_scannetpp_pinhole.py \
  && echo "converter: OK" \
  || echo "ERROR: convert_scannetpp_pinhole.py not found"
```

## 5. 转换一个场景

执行转换：

```bash
python convert_scannetpp_pinhole.py \
  "$SOURCE_SCENE" \
  --output-root "$HOVSG_DATA_ROOT" \
  --split test \
  --scene-id "$SCENE_ID" \
  --copy
```

说明：

- `--copy` 会把 RGB 复制到 HOV-SG 数据目录，传输或移动项目时更可靠。
- 不使用 `--copy` 时，RGB 会使用绝对路径软链接，可节省空间。
- 默认转换场景中的全部帧。
- 已存在输出时脚本会停止，不会自动覆盖。

需要重新转换时：

```bash
python convert_scannetpp_pinhole.py \
  "$SOURCE_SCENE" \
  --output-root "$HOVSG_DATA_ROOT" \
  --split test \
  --scene-id "$SCENE_ID" \
  --copy \
  --force
```

如果源场景帧数很多，只想快速测试前 100 帧：

```bash
python convert_scannetpp_pinhole.py \
  "$SOURCE_SCENE" \
  --output-root "$HOVSG_DATA_ROOT" \
  --split test \
  --scene-id "$SCENE_ID" \
  --max-frames 100 \
  --copy \
  --force
```

如需每隔 5 帧采样一帧：

```bash
python convert_scannetpp_pinhole.py \
  "$SOURCE_SCENE" \
  --output-root "$HOVSG_DATA_ROOT" \
  --split test \
  --scene-id "$SCENE_ID" \
  --stride 5 \
  --max-frames 100 \
  --copy \
  --force
```

## 6. 检查转换结果

设置转换后的场景目录：

```bash
export CONVERTED_SCENE=$HOVSG_DATA_ROOT/test/$SCENE_ID
: "${CONVERTED_SCENE:?CONVERTED_SCENE is not set}"
test -d "$CONVERTED_SCENE" \
  && echo "converted scene: $CONVERTED_SCENE" \
  || echo "ERROR: converted scene directory not found"
```

检查输出结构：

```bash
find "$CONVERTED_SCENE" -maxdepth 2 -type f | sort | head -40
```

正确结构为：

```text
<HOVSG_DATA_ROOT>/test/<SCENE_ID>/
├── rgb/
├── depth/
├── pose/
├── intrinsics/
└── metadata.json
```

检查 RGB、depth、pose 和 intrinsics 数量：

```bash
export CONVERTED_SCENE=$HOVSG_DATA_ROOT/test/$SCENE_ID
: "${CONVERTED_SCENE:?CONVERTED_SCENE is not set}"

for MODALITY in rgb depth pose intrinsics; do
  printf '%-12s ' "$MODALITY"
  find "$CONVERTED_SCENE/$MODALITY" -type f | wc -l
done
```

四个数字必须完全一致。

查看元数据：

```bash
python -m json.tool "$CONVERTED_SCENE/metadata.json" | head -80
```

查看第一帧位姿：

```bash
cat "$CONVERTED_SCENE/pose/000000.txt"
```

查看第一帧相机内参：

```bash
cat "$CONVERTED_SCENE/intrinsics/000000.txt"
```

位姿应为 4×4 矩阵，内参应为 3×3 矩阵。

检查第一张 RGB 和 depth 的尺寸及深度范围：

```bash
python - "$CONVERTED_SCENE" <<'PY'
import sys
from pathlib import Path

import numpy as np
from PIL import Image

scene = Path(sys.argv[1])
rgb_path = sorted((scene / "rgb").iterdir())[0]
depth_path = sorted((scene / "depth").iterdir())[0]

rgb = Image.open(rgb_path)
depth = np.asarray(Image.open(depth_path))
valid = depth[depth > 0]

print("RGB:", rgb_path.name, rgb.size, rgb.mode)
print("Depth:", depth_path.name, (depth.shape[1], depth.shape[0]), depth.dtype)
print("Valid depth pixels:", valid.size)
if valid.size:
    print("Depth range (m):", float(valid.min()) / 1000.0, float(valid.max()) / 1000.0)
PY
```

RGB 和 depth 尺寸必须一致，depth 应为 uint16，深度范围应符合室内场景尺度。

## 7. 第一次运行：只验证点云和物体特征

第一次建议关闭楼层和房间层级构建，先验证 RGB-D 几何、SAM masks 和 CLIP 特征。

```bash
cd "$HOVSG_ROOT"
conda activate hovsg

python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id="$SCENE_ID" \
  main.save_path="$HOVSG_OUTPUT_ROOT" \
  pipeline.skip_frames=10 \
  pipeline.create_graph=false
```

`pipeline.skip_frames` 应根据转换后的帧数设置：

```text
约 20 帧：pipeline.skip_frames=1
约 100 帧：pipeline.skip_frames=2 或 5
约 600 帧：pipeline.skip_frames=10
```

当前示例实际转换出 600 帧，因此先使用 10，约处理 60 帧，足够进行第一轮效果验证。
设为 1 会对全部 600 帧运行两轮点云/SAM/CLIP 处理，时间和显存开销很大。

## 8. 查看第一次运行的输出

HOV-SG 会把 `dataset` 和 `scene_id` 自动添加到输出路径：

```bash
export SCENE_GRAPH_DIR=$HOVSG_OUTPUT_ROOT/hm3dsem/$SCENE_ID
```

查看输出：

```bash
find "$SCENE_GRAPH_DIR" -maxdepth 2 -type f | sort
```

重点输出：

```text
full_pcd.ply
masked_pcd.ply
full_feats.pt
mask_feats.pt
```

含义：

- `full_pcd.ply`：融合全部选中 RGB-D 帧生成的彩色点云。
- `masked_pcd.ply`：经过 SAM 分割和跨帧融合后的物体点云。
- `full_feats.pt`：完整点云的 OpenCLIP 特征。
- `mask_feats.pt`：各个物体 mask 的 OpenCLIP 特征。

第一次测试最重要的是打开 `full_pcd.ply`，检查：

- 是否存在点云翻转。
- 多帧之间是否存在明显重影。
- RGB 是否正确贴合几何。
- 场景尺度是否符合真实米制尺度。
- 相邻相机帧是否连续。

如果点云出现双墙、重影或尺度异常，应先检查 pose、内参和深度，暂时不要继续构建
楼层/房间层级图。

## 9. 第二次运行：尝试完整层级场景图

确认 `full_pcd.ply` 正常后，换一个输出根目录运行完整层级构建，避免覆盖第一次结果：

```bash
export HOVSG_HIERARCHY_OUTPUT=$HOVSG_ROOT/data/scene_graphs_hierarchy

python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id="$SCENE_ID" \
  main.save_path="$HOVSG_HIERARCHY_OUTPUT" \
  pipeline.skip_frames=10 \
  pipeline.create_graph=true
```

完整输出可能包含：

```text
graph/
├── floors/
├── rooms/
├── objects/
└── nav_graph/
```

ScanNet++ 测试序列如果帧数少、覆盖范围小，物体级结果仍可用于检查效果，但房间、楼层
和导航图可能不完整。这是场景覆盖不足导致的，不一定是转换错误。

## 10. 常见问题

### 找不到 `scene_manifest.json`

说明该场景尚未完成 vggtSam pinhole 预处理，或者路径不是：

```text
data/processed/scannetpp_pinhole_2d/<scene_id>/
```

### 提示缺少 `raster` 或 `zbuf`

重新运行 vggtSam ScanNet++ 预处理，并启用：

```text
--save-raster
```

`pointmaps/*.npz` 不能直接替代每帧相机 Z-depth；当前转换器使用 `raster/*.npz` 中的
`zbuf`。

### 找不到 COLMAP 文件

确认 `scene_manifest.json` 中的 `scene_root` 指向有效原始场景，并包含：

```text
colmap/cameras.txt
colmap/images.txt
```

### 输出已经存在

确认旧结果不再需要后，在转换命令末尾添加：

```text
--force
```

### 点云发生翻转

转换器按以下约定处理：

```text
COLMAP world-to-camera (OpenCV coordinates)
    -> camera-to-world (OpenCV coordinates)
    -> HOV-SG point-cloud fusion
```

不要再次手动对 pose 的 Y/Z 轴翻转。

### 点云出现明显重影

依次检查：

1. RGB、depth、pose、intrinsics 文件数量是否相同。
2. RGB 和 depth 分辨率是否相同。
3. COLMAP pose 是否与对应的 RGB 文件名匹配。
4. `zbuf` 是否来自同一帧的 mesh rasterization。
5. 相机轨迹自身是否存在漂移。

## 11. 最短复制版

确认路径和场景 ID 后，可以依次复制以下命令：

```bash
export VGGT_SAM_ROOT=/home/wlh50060092/vggtSam
export HOVSG_ROOT=/home/wlh50060092/HOV-SG
export SCENE_ID=00a231a370
export SCANNETPP_PROCESSED_ROOT=$VGGT_SAM_ROOT/data/processed/scannetpp_pinhole_2d
export SOURCE_SCENE=$SCANNETPP_PROCESSED_ROOT/$SCENE_ID
export HOVSG_DATA_ROOT=$HOVSG_ROOT/data/scannetpp_hovsg
export HOVSG_OUTPUT_ROOT=$HOVSG_ROOT/data/scene_graphs

cd "$HOVSG_ROOT"
conda activate hovsg

python convert_scannetpp_pinhole.py \
  "$SOURCE_SCENE" \
  --output-root "$HOVSG_DATA_ROOT" \
  --split test \
  --scene-id "$SCENE_ID" \
  --copy

export CONVERTED_SCENE=$HOVSG_DATA_ROOT/test/$SCENE_ID
: "${CONVERTED_SCENE:?CONVERTED_SCENE is not set}"
test -d "$CONVERTED_SCENE" || { echo "ERROR: $CONVERTED_SCENE not found"; return 1 2>/dev/null || exit 1; }
for MODALITY in rgb depth pose intrinsics; do
  printf '%-12s ' "$MODALITY"
  find "$CONVERTED_SCENE/$MODALITY" -type f | wc -l
done

python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id="$SCENE_ID" \
  main.save_path="$HOVSG_OUTPUT_ROOT" \
  pipeline.skip_frames=10 \
  pipeline.create_graph=false
```

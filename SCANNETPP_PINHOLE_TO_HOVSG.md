# ScanNet++ 单场景继续运行 HOV-SG

本文只记录场景 `00a231a370` 接下来要执行的步骤。环境、依赖和权重均假定已经配置完成。

当前旧点云在 MeshLab 中显示 Z 轴竖直，但 HOV-SG 的楼层、房间和导航代码要求 Y-up。
因此必须重新转换 pose，不能直接用旧输出继续构建层级图。

## 1. 同步新版代码

把本机当前项目同步到服务器，至少包含：

```text
convert_scannetpp_pinhole.py
hovsg/dataloader/hm3dsem.py
hovsg/graph/graph.py
hovsg/graph/navigation_graph.py
application/create_graph.py
config/create_graph.yaml
```

在服务器确认转换器包含 Z-up → Y-up：

```bash
cd /home/wlh50060092/HOV-SG
grep -n 'Z_UP_TO_Y_UP' convert_scannetpp_pinhole.py
```

必须同时找到矩阵定义和 `pose = Z_UP_TO_Y_UP @ pose`。找不到时先同步新版代码。

## 2. 设置变量

```bash
cd /home/wlh50060092/HOV-SG
conda activate hovsg

export VGGT_SAM_ROOT=/home/wlh50060092/vggtSam
export HOVSG_ROOT=/home/wlh50060092/HOV-SG
export SCENE_ID=00a231a370
export SOURCE_SCENE=$VGGT_SAM_ROOT/data/processed/scannetpp_pinhole_2d/$SCENE_ID
export HOVSG_DATA_ROOT=$HOVSG_ROOT/data/scannetpp_hovsg
export CONVERTED_SCENE=$HOVSG_DATA_ROOT/test/$SCENE_ID
export HOVSG_HIERARCHY_OUTPUT=$HOVSG_ROOT/data/scene_graphs_hierarchy_yup
export SCENE_GRAPH_DIR=$HOVSG_HIERARCHY_OUTPUT/hm3dsem/$SCENE_ID

test -d "$SOURCE_SCENE" || { echo "ERROR: $SOURCE_SCENE not found"; return 1 2>/dev/null || exit 1; }
```

## 3. 强制重新转换为 Y-up

必须使用 `--force` 覆盖旧 pose 和 metadata。RGB、depth 内容不变，主要变化是世界坐标。

```bash
python convert_scannetpp_pinhole.py \
  "$SOURCE_SCENE" \
  --output-root "$HOVSG_DATA_ROOT" \
  --split test \
  --scene-id "$SCENE_ID" \
  --copy \
  --force
```

检查四类文件数量：

```bash
for MODALITY in rgb depth pose intrinsics; do
  printf '%-12s ' "$MODALITY"
  find "$CONVERTED_SCENE/$MODALITY" -type f | wc -l
done
```

四项都应为 `600`。

检查 metadata：

```bash
python - "$CONVERTED_SCENE/metadata.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    metadata = json.load(handle)

for key in ("camera_coordinates", "source_world_up_axis", "world_up_axis", "world_transform"):
    print(f"{key}: {metadata.get(key)}")

assert metadata["camera_coordinates"] == "opencv"
assert metadata["source_world_up_axis"] == "+Z"
assert metadata["world_up_axis"] == "+Y"
print("Metadata validation: OK")
PY
```

应看到：

```text
source_world_up_axis: +Z
world_up_axis: +Y
world_transform: (x, y, z) -> (x, z, -y)
```

检查第一帧 pose：

```bash
cat "$CONVERTED_SCENE/pose/000000.txt"
```

原始相机位置约为 `[1.05, 2.71, 1.77]`，转换后最后一列前三项应大致为：

```text
X ≈  1.05
Y ≈  1.77
Z ≈ -2.71
```

Y 应接近相机离地高度。若仍接近原始值，说明服务器仍在运行旧转换器。

## 4. 运行 12 帧完整层级图

以下命令固定选择索引 `0、50、100、...、550`，共 12 帧，不是随机选帧：

```bash
CUDA_VISIBLE_DEVICES=0 python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path="$HOVSG_DATA_ROOT" \
  main.split=test \
  main.scene_id="$SCENE_ID" \
  main.save_path="$HOVSG_HIERARCHY_OUTPUT" \
  pipeline.skip_frames=50 \
  pipeline.create_graph=true \
  pipeline.denoise_full_pcd=false \
  pipeline.save_full_feats=false \
  pipeline.save_mask_feats=false \
  models.sam.points_per_side=6 \
  models.sam.points_per_batch=36
```

| 选项 | 作用 |
|---|---|
| `skip_frames=50` | 从 600 帧固定抽取 12 帧 |
| `create_graph=true` | 构建楼层、房间、物体层级和导航图 |
| `denoise_full_pcd=false` | 关闭非常耗时的完整点云 DBSCAN |
| 两个 `save_*_feats=false` | 不落盘 `.pt` 特征，节省磁盘 |
| `points_per_side=6` | 降低 SAM mask 采样密度 |
| `points_per_batch=36` | 降低 SAM 峰值显存 |

关闭 `.pt` 保存不影响当前进程构图，特征仍在内存中。以后若需从缓存重新评测特征，则
必须重跑 SAM/OpenCLIP。

`Merging 3d masks` 显示 `11/11` 正常：第 1 帧作为初始结果，剩余 11 帧依次合并。

## 5. 检查坐标轴和点云范围

生成 `full_pcd.ply` 后执行：

```bash
python - "$SCENE_GRAPH_DIR/full_pcd.ply" <<'PY'
import sys
import numpy as np
import open3d as o3d

points = np.asarray(o3d.io.read_point_cloud(sys.argv[1]).points)
assert len(points), "empty point cloud"
print("points:", len(points))

for name, index in zip("XYZ", range(3)):
    values = points[:, index]
    p1, p99 = np.percentile(values, [1, 99])
    print(
        f"{name}: min={values.min():.3f}, max={values.max():.3f}, "
        f"range={np.ptp(values):.3f}, robust_range={p99-p1:.3f}"
    )
PY
```

MeshLab 中红色为 X、绿色为 Y、蓝色为 Z。正确结果必须满足：

- 绿色 Y 轴竖直；
- 地板沿 X-Z 平面展开；
- 蓝色 Z 轴不再是高度轴。

完整 Y 范围会受少量漂浮点影响，应优先看去掉两端各 1% 点后的 `robust_range`。如果
Z 轴仍然竖直，不要继续使用该结果，重新检查第 1～3 节。

## 6. 检查输出

```bash
find "$SCENE_GRAPH_DIR" -maxdepth 3 -type f | sort
du -sh "$SCENE_GRAPH_DIR"
```

主要结果：

```text
full_pcd.ply       全部有效 RGB-D 点融合后的场景点云
masked_pcd.ply     SAM mask 投影、过滤并合并后的物体候选点云
objects/           物体点云
floors/、rooms/    楼层和房间结果（以实际保存目录为准）
nav_graph/         导航图结果
```

`masked_pcd.ply` 少于 `full_pcd.ply` 正常。墙、地面、天花板、SAM 漏检区域以及未通过
有效深度和最小点数过滤的区域，只会存在于完整点云。

本次只输入：

```text
RGB + depth + camera-to-world pose + 相机内参
```

没有使用真值语义或实例标签。SAM 生成 masks，OpenCLIP 生成视觉语义特征，几何算法构建
楼层、房间、物体归属和导航图，不需要额外语言大模型。

## 7. 结果正常后增加帧数

建议逐步增加，并为每次测试使用新输出目录：

```text
skip_frames=50   12 帧
skip_frames=25   24 帧
skip_frames=10   60 帧
skip_frames=5    120 帧
skip_frames=1    600 帧
```

测试 24 帧时，只需修改：

```bash
export HOVSG_HIERARCHY_OUTPUT=$HOVSG_ROOT/data/scene_graphs_hierarchy_yup_24f
export SCENE_GRAPH_DIR=$HOVSG_HIERARCHY_OUTPUT/hm3dsem/$SCENE_ID
```

然后重新执行第 4 节命令，并把：

```text
pipeline.skip_frames=50
```

改为：

```text
pipeline.skip_frames=25
```

当前实现不会自动用多张 GPU 加速同一场景。最慢的 3D mask merging 主要运行在 CPU。
多 GPU 更适合并行运行不同场景，而且每个进程必须使用不同输出目录。

## 8. 提高 SAM 物体覆盖率

几何和层级流程稳定后，可将：

```text
models.sam.points_per_side=12
models.sam.points_per_batch=36
```

`points_per_side` 从 6 提高到 12 会增加小物体和背景区域的 mask 覆盖率。显存充足时可把
`points_per_batch` 提高到默认值 `144`；它主要影响速度和显存，通常不改变覆盖率。

## 9. DBSCAN 和楼层分割

当前只关闭完整融合点云上的昂贵 DBSCAN：

```text
pipeline.denoise_full_pcd=false
```

这不会关闭物体 mask 合并、特征处理或层级构建。之前 CPU 长时间 100%、GPU 0% 的主要
原因就是完整点云 DBSCAN，因此当前测试不要恢复它。

若出现：

```text
clustred_peaks [...]
floors []
```

首先确认点云为 Y-up。新版代码只对坐标正确的单层稀疏场景提供单楼层回退，不能用它
掩盖 Z-up 输入。

## 10. 当前执行顺序

```text
同步新版代码
  → --force 重新转换
  → 验证 metadata 为 Y-up
  → 验证 pose 的 Y 接近相机高度
  → 新目录运行 12 帧完整层级图
  → MeshLab 确认绿色 Y 轴竖直
  → 检查 floor、room、object、nav graph
  → 增加到 24 帧或提高 SAM 密度
```

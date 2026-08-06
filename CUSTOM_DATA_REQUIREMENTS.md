# HOV-SG 自有数据输入要求

本文档用于向数据提供方说明 HOV-SG 运行所需的数据，并作为后续格式转换和数据验收依据。

## 1. 最小可用数据

运行 HOV-SG 并构建场景图，最少需要：

```text
RGB + Depth + Camera Pose + Camera Intrinsics
```

Mesh 和人工语义标签不是基本建图的必需输入。如果已经提供同步的 RGB-D 相机轨迹，
就不需要通过 Habitat-Sim 和 mesh 重新渲染。

## 2. 推荐目录结构

每一帧 RGB、depth 和 pose 必须严格一一对应，推荐使用相同的六位数字帧 ID：

```text
scene_name/
├── rgb/
│   ├── 000000.png
│   ├── 000001.png
│   └── ...
├── depth/
│   ├── 000000.png
│   ├── 000001.png
│   └── ...
├── pose/
│   ├── 000000.txt
│   ├── 000001.txt
│   └── ...
├── intrinsics.txt
└── metadata.json
```

`metadata.json` 不是强制文件，但建议用于记录深度单位、位姿约定、分辨率和坐标系，
避免仅通过文件名猜测数据格式。

## 3. RGB 图像

要求：

- 使用 PNG 或 JPG。
- 按采集时间排列。
- 图像方向正确，不能存在未记录的旋转或镜像。
- RGB 数量必须和 depth、pose 数量一致。
- 推荐 RGB 与 depth 使用相同分辨率并已完成像素配准。
- 如果图像尚未去畸变，需要同时提供畸变参数。

推荐命名：

```text
rgb/000000.png
rgb/000001.png
```

## 4. 深度图

要求：

- 每张 RGB 对应一张 depth。
- 推荐使用无损的单通道 16-bit PNG。
- 必须说明深度单位和 scale，例如 `1000 = 1 m`。
- 必须说明无效深度值，推荐使用 `0`。
- 必须说明深度类型是 Z-depth 还是 Euclidean/range depth。

推荐使用相机坐标系的 Z-depth。当前项目使用针孔相机模型反投影，直接使用沿射线测得的
Euclidean/range depth 会导致图像边缘的点云产生几何形变。若只能提供 range depth，
后续需要利用相机内参转换为 Z-depth。

推荐命名：

```text
depth/000000.png
depth/000001.png
```

## 5. 相机位姿

每张 RGB-D 必须对应一个相机位姿。推荐每个 TXT 文件保存一个 4×4 齐次变换矩阵：

```text
r00 r01 r02 tx
r10 r11 r12 ty
r20 r21 r22 tz
0   0   0   1
```

也可以保存成一行 16 个浮点数：

```text
r00 r01 r02 tx r10 r11 r12 ty r20 r21 r22 tz 0 0 0 1
```

提供位姿时必须同时说明：

- 矩阵是 `camera-to-world` 还是 `world-to-camera`。
- 平移量的单位是米、厘米还是毫米。
- 世界坐标系的重力轴和向上方向。
- 相机坐标系采用 OpenCV、OpenGL、ROS 或其他约定。
- 如果使用位置加四元数，四元数顺序是 `xyzw` 还是 `wxyz`。

常见相机坐标约定：

| 约定 | X 轴 | Y 轴 | Z 轴 |
|---|---|---|---|
| OpenCV | 右 | 下 | 前 |
| OpenGL | 右 | 上 | 后 |

HOV-SG 适配时会统一转换为项目内部使用的 4×4 camera-to-world 矩阵。不能只提供矩阵
而不说明坐标系，因为数值合法不代表方向正确。

## 6. 相机内参

至少需要提供：

```text
fx fy cx cy
```

或完整的 3×3 内参矩阵：

```text
fx  0 cx
 0 fy cy
 0  0  1
```

同时需要：

- RGB 图像宽度和高度。
- Depth 图像宽度和高度。
- RGB 相机内参。
- Depth 相机内参。
- 图像是否已经去畸变。
- 未去畸变时的畸变模型和参数。

自己的数据不应使用当前 HM3D loader 中假设的固定 90° FOV，应读取真实标定参数。

## 7. RGB 与 Depth 来自不同相机时

如果 RGB 和 depth 来自不同传感器，还必须提供：

- RGB 相机内参。
- Depth 相机内参。
- Depth-to-RGB 或 RGB-to-Depth 外参，并明确变换方向。
- 两个传感器的时间戳和同步方式。
- 畸变参数。

推荐数据提供方提前将 depth 配准到 RGB 图像坐标系。如果没有提前配准，后续转换脚本
需要完成反投影、坐标变换和重新投影。

## 8. 帧对应关系和时间戳

如果 RGB、depth、pose 不能通过相同文件名直接对应，需要提供帧索引文件：

```csv
frame_id,rgb,depth,pose,rgb_timestamp,depth_timestamp,pose_timestamp
000000,rgb/100.png,depth/101.png,pose/099.txt,1712345678.01,1712345678.02,1712345678.00
```

必须说明：

- 时间戳单位。
- RGB、depth 和 pose 的同步容差。
- 是否经过插值。
- 是否存在缺帧或重复帧。

## 9. Mesh 是否必须

### 不需要 Mesh 的情况

数据已经包含同步且标定完整的：

```text
RGB + Depth + Pose + Intrinsics
```

此时 HOV-SG 可以直接融合点云、生成 SAM masks、计算 OpenCLIP 特征并构建场景图。

### 建议提供 Mesh 的情况

Mesh 可用于：

- 通过模拟器渲染 RGB-D 数据。
- 生成或核对语义真值。
- 评估点云和几何重建精度。
- 生成新的虚拟相机轨迹。

普通自有数据可提供：

```text
scene.glb
scene.obj
scene.ply
```

如果希望走 Habitat/HM3D 的完整流程，建议同时提供：

```text
scene.basis.glb
scene.basis.navmesh
scene.semantic.glb
scene.semantic.txt
scene_dataset_config.json
```

## 10. 可选数据

以下数据不影响基本建图，但有助于过滤、调试或定量评测。

### 有效深度 Mask

```text
mask_valid/
├── 000000.png
└── ...
```

如果 depth 已经使用 `0` 表示无效区域，则可以不单独提供。

### 语义和实例真值

只有进行定量评测时才需要：

- 每帧 semantic mask。
- 每帧 instance 或 panoptic mask。
- 类别 ID 到类别名称的映射。
- 房间标签和楼层划分。
- GT mesh 或 GT point cloud。

HOV-SG 基本运行不要求人工语义标签；SAM 和 OpenCLIP 会生成开放词汇特征。

## 11. 推荐的元数据文件

建议每个场景提供类似以下内容的 `metadata.json`：

```json
{
  "scene_id": "example_scene",
  "frame_count": 1000,
  "rgb": {
    "width": 1280,
    "height": 720,
    "format": "png",
    "distorted": false
  },
  "depth": {
    "width": 1280,
    "height": 720,
    "format": "uint16_png",
    "type": "z_depth",
    "unit": "millimeter",
    "scale": 1000.0,
    "invalid_value": 0,
    "registered_to_rgb": true
  },
  "intrinsics": {
    "fx": 600.0,
    "fy": 600.0,
    "cx": 640.0,
    "cy": 360.0
  },
  "pose": {
    "type": "camera_to_world",
    "format": "4x4_matrix",
    "translation_unit": "meter",
    "camera_coordinates": "opencv",
    "world_up_axis": "+Y"
  }
}
```

以上数值仅用于展示格式，实际文件必须填写真实标定结果。

## 12. 数据验收标准

收到数据后至少检查以下项目：

1. RGB、depth、pose 数量完全一致。
2. 三种文件能够通过帧 ID 或索引表一一对应。
3. 所有图像可以正常读取且尺寸符合元数据。
4. 深度单位、scale、无效值和深度类型明确。
5. 相机内参符合实际图像分辨率。
6. 所有 pose 都是有限数值且变换矩阵合法。
7. pose 的方向、单位和坐标轴定义明确。
8. 融合少量帧后点云不会重影、翻转或尺度异常。
9. RGB 和 depth 的物体边缘能够对齐。
10. 相机轨迹连续，没有明显跳变或时间错位。

只有“文件数量一致”还不够。最终应通过小规模点云融合验证标定、位姿方向和尺度。

## 13. 可直接发给数据提供方的清单

> 请提供一个场景的同步 RGB-D 相机序列，包括：
>
> 1. 每帧 RGB 图像。
> 2. 每帧深度图，并注明深度类型、单位、scale 和无效值。
> 3. 每帧相机位姿，优先使用 4×4 矩阵，并注明 camera-to-world 或
>    world-to-camera、坐标系和长度单位。
> 4. RGB 和 depth 的相机内参 `fx, fy, cx, cy`、图像分辨率及畸变参数。
> 5. RGB、depth、pose 的帧对应关系或时间戳。
> 6. 如果 RGB 和 depth 来自不同相机，请提供两相机之间的外参和同步关系。
> 7. 如有条件，可额外提供 mesh、有效深度 mask 和语义/实例标签，但这些不是运行
>    HOV-SG 基本建图的必要输入。

## 14. 最终结论

运行自有数据时，必须确保以下四项齐全且逐帧对应：

```text
RGB
Depth
Camera Pose
Camera Intrinsics
```

后续可以编写转换脚本，将其他命名、位姿格式、深度单位和坐标系转换为 HOV-SG 使用的
`rgb/depth/pose` 目录结构。Mesh、navmesh 和语义标签属于渲染或评测所需的附加数据，
不是基本场景图构建的必要条件。

# HOV-SG 数据格式说明

HOV-SG 接受两种数据形态，二选一：
- **形态 A**：原始 3D mesh（由项目脚本用 habitat-sim 渲染出 RGB-D）
- **形态 B**：预渲染 RGB-D 序列（直接喂主流程，绕过 habitat-sim）

## 一、形态 A：原始 mesh 层

### 目录结构
```
hm3d/
├── hm3d_annotated_basis.scene_dataset_config.json   ← 顶层场景注册
└── val/
    └── <scene_id>/
        ├── <scene_name>.basis.glb
        ├── <scene_name>.basis.navmesh
        ├── <scene_name>.glb
        ├── <scene_name>.semantic.glb
        └── <scene_name>.semantic.txt
```

### 命名规则
- `scene_id` 形如 `00824-Dd4bFSTQ8gi`（`<编号>-<空间哈希>`）
- `scene_name` = 去掉 `<编号>-` 前缀，即 `Dd4bFSTQ8gi`
- 所有 mesh 文件以 `scene_name` 为前缀

### 文件清单
| 文件 | 格式 | 必需性 |
|---|---|---|
| `hm3d_annotated_basis.scene_dataset_config.json` | JSON | 必需 |
| `<scene_name>.basis.glb` | glTF binary mesh | 必需 |
| `<scene_name>.basis.navmesh` | 导航网格 | 推荐 |
| `<scene_name>.glb` | glTF binary mesh | 必需 |
| `<scene_name>.semantic.glb` | 带语义标注的 mesh | 评估时必需 |
| `<scene_name>.semantic.txt` | 语义类别表 | 评估时必需 |

## 二、形态 B：预渲染 RGB-D 序列层

### 目录结构
```
<root>/<split>/<scene_id>/
├── rgb/
│   └── <scene_name>-000000.png ...
├── depth/
│   └── <scene_name>-000000.png ...
└── pose/
    └── <scene_name>-000000.txt ...
```
**三个目录的文件数必须相等、按文件名排序后一一对应。**
（可选 `semantic/` 存逐帧语义 GT，仅用于层级评估）

### 文件格式
| 类型 | 格式 | 规格 |
|---|---|---|
| RGB | PNG | 透视图（非全景）；分辨率 1080×720；HFOV=90°；相机高 1.5 m |
| depth | PNG (uint16) | 单位毫米，scale=1000（值/1000 = 米） |
| pose | TXT | **单行 16 个浮点数**，行优先 4×4 变换矩阵 |
| semantic（可选） | NPY | 逐像素语义 ID |

### 相机约定
- 透视 pinhole 相机，HFOV=90°（硬编码于 dataloader）
- **拒绝**全景 / 等距柱状图

## 三、不可接受

- 全景图 / 等距柱状图（equirectangular）：内参公式不匹配
- 双 depth 变体（`depth_zbuffer` + `depth_euclidean`）：dataloader 只认 `depth/`
- `point_info` 之类辅助目录：dataloader 不读
- RGB 与 depth 数量不一致：必须等长配对

## 四、交付前核对

**形态 A：**
```bash
SCENE=00824-Dd4bFSTQ8gi
NAME=Dd4bFSTQ8gi
for f in hm3d_annotated_basis.scene_dataset_config.json \
         val/$SCENE/$NAME.basis.glb \
         val/$SCENE/$NAME.glb \
         val/$SCENE/$NAME.semantic.glb \
         val/$SCENE/$NAME.semantic.txt; do
  [ -f "hm3d/$f" ] && echo "OK       $f" || echo "MISSING  $f"
done
```

**形态 B：** 核对三目录文件数相等
```bash
SCENE=00824-Dd4bFSTQ8gi
root=data/hm3dsem_walks/val/$SCENE
echo "rgb:    $(ls $root/rgb | wc -l)"
echo "depth:  $(ls $root/depth | wc -l)"
echo "pose:   $(ls $root/pose | wc -l)"
```

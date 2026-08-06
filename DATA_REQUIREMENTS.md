# HOV-SG 数据需求说明

本文档说明运行 HOV-SG 所需的数据集类型与格式，供数据提供方按需准备。

## 一、需要的数据集

**Habitat Matterport 3D Semantics (HM3DSem)**，val split，版本 v0.2。

- 发布方：Matterport / Meta AI Habitat
- 许可：HM3D Research License（学术用途）
- 三个公开 tar（val 集，无需登录）：
  - `hm3d-val-habitat-v0.2.tar` — mesh 文件（`.basis.glb` / `.glb` / `.navmesh`）
  - `hm3d-val-semantic-annots-v0.2.tar` — 语义标注（`.semantic.glb` / `.semantic.txt`）
  - `hm3d-val-semantic-configs-v0.2.tar` — 顶层 `hm3d_annotated_basis.scene_dataset_config.json`
- 下载入口：https://aihabitat.org/datasets/hm3d-semantics/

> 这三个 tar 合起来包含整个 val 集（约 70 个场景）。本仓库只需要其中**一个场景**的 mesh 文件即可跑通单场景测试。

## 二、需要的场景（任选其一）

```
00824-Dd4bFSTQ8gi   ← 推荐（README 示例场景）
00829-QaLdnwvtxbs
00843-DYehNKdT76V
00847-bCPU9suPUw9
00849-a8BtkwhxdRV
00861-GLAQ4DNUx5U
00862-LT9Jq6dN3Ea
00873-bxsVRursffK
00877-4ok3usBNeis
00890-6s7QHgap2fW
```

这些场景的**相机轨迹 poses 已由本仓库自带**（`hovsg/data/hm3dsem/metadata/poses/<scene_id>.txt`），所以**不需要对方提供 pose**，只需要 mesh 数据。
若换成上面 10 个之外的任意场景，没有匹配的 pose 文件，walks 生成脚本 `gen_hm3dsem_walks_from_poses.py` 会直接失败。

## 三、要求的目录结构（原始 mesh 层）

```
hm3d/
├── hm3d_annotated_basis.scene_dataset_config.json   ← 顶层 config, 必需
└── val/
    └── 00824-Dd4bFSTQ8gi/                            ← scene_id
        ├── Dd4bFSTQ8gi.basis.glb                     ← 必需
        ├── Dd4bFSTQ8gi.basis.navmesh
        ├── Dd4bFSTQ8gi.glb                          ← 必需
        ├── Dd4bFSTQ8gi.semantic.glb                 ← 语义评估用
        └── Dd4bFSTQ8gi.semantic.txt
```

**命名规则**：
- `scene_id` 形如 `00824-Dd4bFSTQ8gi`（`<编号>-<Matterport空间哈希>`）
- `scene_name` = 去掉 `<编号>-` 前缀的部分（即 `Dd4bFSTQ8gi`），所有 mesh 文件名以 `scene_name` 为前缀

## 四、格式与规格

| 项 | 要求 |
|---|---|
| mesh 格式 | glTF binary (`.glb`)，可被 habitat-sim 加载渲染**透视**视图 |
| 相机类型 | **透视 (pinhole)**，HFOV=90°；**不接受全景/等距柱状图** |
| 渲染分辨率 | 1080 × 720（项目生成脚本默认） |
| 相机高度 | 1.5 m（`sensor_height` 默认） |
| depth 单位 | uint16 PNG，**毫米**，scale=1000 |
| pose 格式 | 每帧一个 `.txt`，**单行 16 个浮点数**，行优先 4×4 变换矩阵 |

> pose 文件由项目脚本 `gen_hm3dsem_walks_from_poses.py` 用 habitat-sim 渲染时自动生成，**数据提供方不需要制作 pose**。

## 五、不需要 / 不可接受的格式

以下数据**不能直接用**，避免白拿：

- ❌ **HM3D-OIVS / hm3d_omni_dataset**（`rgb/` + `depth_zbuffer/` + `depth_euclidean/` + `mask_valid/` + `point_info/`）：这是预渲染的全景观测数据集，HOV-SG 代码无任何处理逻辑
- ❌ **HM3D train set** 的 mesh：场景 ID 对不上项目自带的 poses
- ❌ 任意预渲染的 RGB-D 序列（除非已按下方"备选方案"组织好）
- ❌ 全景图 / 等距柱状图（equirectangular）：HOV-SG 的内参公式假设透视相机

## 六、备选方案（仅当拿不到 mesh 时）

如果对方只能提供已经渲染好的 RGB-D 序列，可绕过 mesh 与 habitat-sim，**直接按下述结构组织**，且帧序必须与本仓库自带的 pose 文件对齐：

```
data/hm3dsem_walks/val/00824-Dd4bFSTQ8gi/
├── rgb/    <scene_name>-000000.png ...   (透视图, 数量 = pose 帧数)
├── depth/  <scene_name>-000000.png ...   (uint16, 毫米, scale=1000)
└── pose/   <scene_name>-000000.txt ...   (单行 16 浮点 4×4, 排序后与上面对齐)
```

按此结构组织后，无需运行 `gen_hm3dsem_walks_from_poses.py`，可直接进入 `application/create_graph.py`。
但请注意：此路径下**无法生成 semantic ground truth**，只能跑场景图构建主流程，不能跑 `create_hm3dsem_walks_gt.py` 的层级评估。

一般情况下，让对方走第三节的 mesh 标准路径更省事。

## 七、交付方式

提供**一个场景**的 mesh 数据即可，压缩成 `hm3d_<scene_id>.tar.gz` 或直接传整个 `hm3d/` 目录，保留第三节的目录结构。

交付前用以下命令核对文件齐全（替换 `SCENE` / `NAME` 为实际值）：

```bash
SCENE=00824-Dd4bFSTQ8gi
NAME=Dd4bFSTQ8gi
for f in hm3d_annotated_basis.scene_dataset_config.json \
         val/$SCENE/$NAME.basis.glb \
         val/$SCENE/$NAME.basis.navmesh \
         val/$SCENE/$NAME.glb \
         val/$SCENE/$NAME.semantic.glb \
         val/$SCENE/$NAME.semantic.txt; do
  [ -f "hm3d/$f" ] && echo "OK       $f" || echo "MISSING  $f"
done
```

## 八、收到数据后的运行流程

1. 将 `hm3d/` 目录放在项目根（或任意路径，下面命令中替换）
2. 在 **Linux 服务器**上执行（habitat-sim 仅支持 Linux）：
   ```bash
   conda activate hovsg
   python hovsg/data/hm3dsem/gen_hm3dsem_walks_from_poses.py \
       --dataset_dir hm3d --save_dir data/hm3dsem_walks --split val
   ```
   > 注意：此脚本默认遍历 10 个场景。若只下载了 1 个，需把 `gen_hm3dsem_walks_from_poses.py` 第 36-47 行的 `all_scene_names` 列表改成只含目标场景。
3. 生成 walks 后跑主流程：
   ```bash
   python application/create_graph.py \
       main.dataset=hm3dsem \
       main.dataset_path=data/hm3dsem_walks/ \
       main.scene_id=00824-Dd4bFSTQ8gi \
       main.split=val \
       main.save_path=data/scene_graphs
   ```

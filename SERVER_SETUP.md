# HOV-SG 华为服务器安装指南

本文档适用于当前服务器环境：

- Linux x86-64
- 使用 Conda
- 华为内网 Conda 代理：`conda.rnd.huawei.com`
- 项目要求 Python 3.9
- 当前已有的 `horizonstream` 环境不会被修改

> 安全提示：不要把包含用户名和密码的 `http_proxy`、`https_proxy`
> 完整输出粘贴到 Git、日志或聊天中。若凭据已经公开，请立即更换密码。

## 1. 进入项目目录

```bash
cd /home/wlh50060092/HOV-SG
```

确认当前目录正确：

```bash
pwd
ls environment.yaml setup.py
```

## 2. 创建独立的 Conda 环境

服务器同时存在外网 Anaconda 配置和华为内网配置。直接执行：

```bash
conda env create -f environment.yaml
```

会继续访问 `repo.anaconda.com`，并触发公司代理的 TLS/证书错误。因此这里不使用
`conda env create`，而是通过 `--override-channels` 强制使用华为内网源。

先清理索引缓存：

```bash
conda clean --index-cache -y
```

创建名为 `hovsg` 的 Python 3.9 环境：

```bash
conda create -n hovsg -y --override-channels \
  -c http://conda.rnd.huawei.com/repository/conda-proxy/pytorch \
  -c http://conda.rnd.huawei.com/repository/conda-proxy/main \
  python=3.9 numpy faiss-gpu pip
```

如果提示 `hovsg` 环境已经存在，先检查：

```bash
conda env list
```

只有确认它是此前失败安装留下的不完整环境时，才删除并重新创建：

```bash
conda env remove -n hovsg
```

激活新环境：

```bash
conda activate hovsg
```

确认 Python 版本：

```bash
python --version
```

预期输出为 Python 3.9.x。

## 3. 安装 Python 依赖

以下依赖来自项目的 `environment.yaml`。项目同时列出了
`opencv-python` 和 `opencv-python-headless`，服务器没有桌面显示需求，因此这里只安装
headless 版本，避免两个 OpenCV wheel 冲突。

```bash
python -m pip install \
  matplotlib==3.7.3 \
  scipy==1.13.1 \
  open3d==0.18.0 \
  opencv-python-headless==4.8.1.78 \
  torchmetrics \
  ftfy \
  tqdm \
  open-clip-torch \
  transformers \
  openai==1.3.7 \
  plyfile \
  hydra-core \
  pyvista \
  scikit-fmm \
  pathos
```

安装 Segment Anything：

```bash
python -m pip install \
  git+https://github.com/facebookresearch/segment-anything.git
```

如果 pip 出现公司证书错误，先不要使用全局 `--trusted-host` 或关闭 Conda SSL；应联系
服务器管理员获取公司的 CA 证书，或使用服务器提供的内部 PyPI 镜像。

## 4. 安装 Habitat-Sim

Habitat-Sim 不放在 `environment.yaml` 中安装，按照官方 README 单独安装。继续强制使用
华为内网代理频道：

```bash
conda install -y --override-channels \
  -c http://conda.rnd.huawei.com/repository/conda-proxy/aihabitat \
  -c http://conda.rnd.huawei.com/repository/conda-proxy/conda-forge \
  habitat-sim
```

Habitat-Sim 的 Conda 求解可能重新安装旧版 SciPy。安装完成后再次固定兼容版本：

```bash
python -m pip install --upgrade --force-reinstall \
  numpy==1.26.4 \
  scipy==1.13.1 \
  pillow==10.4.0 \
  imageio-ffmpeg

python -m pip check
```

验证 Habitat-Sim：

```bash
python -c "import habitat_sim; print('habitat-sim OK')"
```

## 5. 安装 HOV-SG 项目

在仓库根目录执行可编辑安装：

```bash
python -m pip install -e .
```

验证主要模块：

```bash
python -c "import torch, open3d, cv2, hovsg; print('HOV-SG imports OK')"
```

检查 PyTorch 是否识别 GPU：

```bash
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('CUDA:', torch.version.cuda)"
```

如果 `CUDA available` 为 `False`，先检查：

```bash
nvidia-smi
```

## 6. 下载模型权重

创建权重目录：

```bash
mkdir -p checkpoints
```

下载 OpenCLIP ViT-H-14 权重：

```bash
wget \
  'https://huggingface.co/laion/CLIP-ViT-H-14-laion2B-s32B-b79K/resolve/main/open_clip_pytorch_model.bin?download=true' \
  -O checkpoints/laion2b_s32b_b79k.bin
```

下载 Segment Anything ViT-H 权重：

```bash
wget \
  https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth \
  -O checkpoints/sam_vit_h_4b8939.pth
```

检查文件是否存在：

```bash
ls -lh \
  checkpoints/laion2b_s32b_b79k.bin \
  checkpoints/sam_vit_h_4b8939.pth
```

## 7. 执行完整环境验证

```bash
conda activate hovsg

python - <<'PY'
import cv2
import habitat_sim
import open3d
import torch

import hovsg

print("Python/Python packages: OK")
print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("Open3D:", open3d.__version__)
print("OpenCV:", cv2.__version__)
print("Habitat-Sim: OK")
print("HOV-SG: OK")
PY
```

## 8. 解压 HM3D-Omni 场景

解压单个场景：

```bash
python extract_scenes.py 00127-EN7GiDgxdQ2
```

解压多个场景：

```bash
python extract_scenes.py \
  00127-EN7GiDgxdQ2 \
  00128-pAjDzi9kWjE \
  00256-92vYG1q49FY \
  00257-j2DKmTV5TPV
```

默认输出结构：

```text
data/hm3d_omni/
└── 00127-EN7GiDgxdQ2/
    ├── rgb/
    ├── depth_zbuffer/
    ├── depth_euclidean/
    ├── mask_valid/
    └── point_info/
```

已有目录默认跳过。需要重新解压时添加：

```bash
python extract_scenes.py 00127-EN7GiDgxdQ2 --force
```

## 9. 当前 HM3D-Omni 数据兼容性说明

场景 `00127-EN7GiDgxdQ2` 当前解压结果为：

| 模态 | 文件数量 |
|---|---:|
| RGB | 1,150 |
| Z-buffer depth | 21,613 |
| Euclidean depth | 4,041 |
| Valid mask | 21,613 |
| Point info | 21,613 |

HOV-SG 的 `HM3DSemDataset` 要求每一帧严格对应以下三个文件：

```text
rgb/<frame>.png
depth/<frame>.png
pose/<frame>.txt
```

其中 `pose/*.txt` 必须包含 16 个浮点数，表示 4×4 相机位姿矩阵。当前数据存在两个问题：

1. RGB、深度和 point-info 文件数量不一致。
2. `point_info` 尚未确认包含可直接使用的 4×4 相机位姿。

因此，当前只能确认场景成功解压，不能直接把 `point_info` 重命名为 `pose`，也不能直接运行
`application/create_graph.py`。

检查实际文件类型和路径：

```bash
SCENE_DIR=data/hm3d_omni/00127-EN7GiDgxdQ2

for MODALITY in rgb depth_zbuffer depth_euclidean mask_valid point_info; do
  echo "===== ${MODALITY} ====="
  find "${SCENE_DIR}/${MODALITY}" -type f | sed 's/.*\.//' | sort | uniq -c
  find "${SCENE_DIR}/${MODALITY}" -type f | sort | head -5
done
```

检查 `point_info` 中的文本或 JSON 内容：

```bash
find "${SCENE_DIR}/point_info" -type f \
  \( -name '*.txt' -o -name '*.json' \) \
  -print -exec head -30 {} \; | head -100
```

需要确认文件命名对应关系、位姿字段、相机内参和深度单位后，才能继续编写
HM3D-Omni → HOV-SG 的格式转换脚本。

## 10. 官方 README 数据流程

如果目标是严格复现官方结果，应使用 README 指定的 HM3DSem 原始数据：

- `hm3d-val-habitat-v0.2.tar`
- `hm3d-val-semantic-annots-v0.2.tar`
- `hm3d-val-semantic-configs-v0.2.tar`

官方流程使用 `.glb`、`.navmesh`、`.semantic.txt` 和仓库提供的 camera poses，通过
Habitat-Sim 生成 `hm3dsem_walks`。HM3D-Omni 是另一种预渲染数据组织；即使场景 ID
来源相同，也不代表它可以直接替换官方输入格式。

### 10.1 推荐的单场景测试

建议先测试：

```text
00824-Dd4bFSTQ8gi
```

仓库已经包含它的相机轨迹：

```text
hovsg/data/hm3dsem/metadata/poses/00824-Dd4bFSTQ8gi.txt
```

Matterport 提供的是按 split 打包的 TAR 文件，而不是 HOV-SG 可直接使用的逐场景下载
链接。因此可以只解压一个场景，但网络下载通常仍需下载完整的 val TAR 包。

#### 方案 A：从 Hugging Face 镜像下载

如果 Matterport 官方地址要求注册，可以使用公开镜像：

```text
zhuhu00/hm3d
```

截至检查时该仓库不是 gated，并且包含 HOV-SG 所需的 habitat、semantic annotations
和 semantic configs。它不是 Matterport 官方发布页；使用数据仍应遵守 HM3D/Matterport
原始许可证，不应把公开镜像理解为免除许可要求。

安装 Hugging Face CLI：

```bash
python -m pip install -U huggingface_hub
```

只下载 val split 所需的三个 TAR 文件：

```bash
mkdir -p data/hm3d_downloads

hf download zhuhu00/hm3d \
  hm3d-val-habitat-v0.2.tar \
  hm3d-val-semantic-annots-v0.2.tar \
  hm3d-val-semantic-configs-v0.2.tar \
  --repo-type dataset \
  --local-dir data/hm3d_downloads
```

这三个文件合计约 5.7 GB。Hugging Face 可以只下载指定 TAR，但由于每个场景仍封装在
TAR 内，不能通过 `hf download` 只传输 `00824` 的 TAR 内部字节。下载完成后继续使用
下文的 `tar --wildcards`，只解压目标场景。

验证下载结果不是错误页面或 Git LFS 指针：

```bash
ls -lh data/hm3d_downloads/*.tar
tar -tf data/hm3d_downloads/hm3d-val-habitat-v0.2.tar | head
tar -tf data/hm3d_downloads/hm3d-val-semantic-annots-v0.2.tar | head
tar -tf data/hm3d_downloads/hm3d-val-semantic-configs-v0.2.tar | head
```

预期 habitat 约 3.53 GB、semantic annotations 约 2.15 GB、semantic configs
约 40 KB。

#### 方案 B：从 Matterport 官方地址下载

创建下载目录：

```bash
mkdir -p data/hm3d_downloads
```

下载官方 README 指定的三个 val 包：

```bash
wget -c \
  https://api.matterport.com/resources/habitat/hm3d-val-habitat-v0.2.tar \
  -O data/hm3d_downloads/hm3d-val-habitat-v0.2.tar

wget -c \
  https://api.matterport.com/resources/habitat/hm3d-val-semantic-annots-v0.2.tar \
  -O data/hm3d_downloads/hm3d-val-semantic-annots-v0.2.tar

wget -c \
  https://api.matterport.com/resources/habitat/hm3d-val-semantic-configs-v0.2.tar \
  -O data/hm3d_downloads/hm3d-val-semantic-configs-v0.2.tar
```

`-c` 支持网络中断后续传。下载结束后先查看 TAR 内的真实路径：

```bash
for ARCHIVE in data/hm3d_downloads/*.tar; do
  echo "===== ${ARCHIVE} ====="
  tar -tf "${ARCHIVE}" | grep -E '00824-Dd4bFSTQ8gi|scene_dataset_config' | head -30
done
```

创建临时解压目录，只提取目标场景以及全局配置文件：

```bash
mkdir -p data/hm3d_single

tar -xf data/hm3d_downloads/hm3d-val-habitat-v0.2.tar \
  -C data/hm3d_single \
  --wildcards '*00824-Dd4bFSTQ8gi/*'

tar -xf data/hm3d_downloads/hm3d-val-semantic-annots-v0.2.tar \
  -C data/hm3d_single \
  --wildcards '*00824-Dd4bFSTQ8gi/*'

# semantic-configs 包通常较小，完整解压以保留 Habitat 必需的全局配置。
tar -xf data/hm3d_downloads/hm3d-val-semantic-configs-v0.2.tar \
  -C data/hm3d_single
```

不同版本的 TAR 可能自带一层 `hm3d/` 目录。定位最终数据根目录：

```bash
find data/hm3d_single -name hm3d_annotated_basis.scene_dataset_config.json -print
find data/hm3d_single -type d -name 00824-Dd4bFSTQ8gi -print
```

正确的数据根目录必须同时满足：

```text
<HM3D_ROOT>/hm3d_annotated_basis.scene_dataset_config.json
<HM3D_ROOT>/val/00824-Dd4bFSTQ8gi/
```

目标场景中应包含：

```text
Dd4bFSTQ8gi.basis.glb
Dd4bFSTQ8gi.basis.navmesh
Dd4bFSTQ8gi.glb
Dd4bFSTQ8gi.semantic.glb
Dd4bFSTQ8gi.semantic.txt
```

### 10.2 只生成一个场景的 RGB-D 轨迹

假设上一步定位出的数据根目录为 `data/hm3d_single/hm3d`，执行：

```bash
python hovsg/data/hm3dsem/gen_hm3dsem_walks_from_poses.py \
  --dataset_dir data/hm3d_single/hm3d \
  --save_dir data/hm3dsem_walks \
  --split val \
  --scene-id 00824-Dd4bFSTQ8gi
```

脚本会使用仓库自带 pose，通过 Habitat-Sim 生成一一对应的：

```text
data/hm3dsem_walks/val/00824-Dd4bFSTQ8gi/
├── rgb/
├── depth/
├── semantic/
└── pose/
```

生成后检查各模态数量：

```bash
SCENE_DIR=data/hm3dsem_walks/val/00824-Dd4bFSTQ8gi
for MODALITY in rgb depth semantic pose; do
  printf '%-10s ' "${MODALITY}"
  find "${SCENE_DIR}/${MODALITY}" -type f | wc -l
done
```

四个数字应当一致。确认无误后再运行单场景建图：

```bash
python application/create_graph.py \
  main.dataset=hm3dsem \
  main.dataset_path=data/hm3dsem_walks \
  main.split=val \
  main.scene_id=00824-Dd4bFSTQ8gi \
  main.save_path=data/scene_graphs
```

## 安装完成后的目录检查

完成环境安装和权重下载后，仓库至少应包含：

```text
HOV-SG/
├── checkpoints/
│   ├── laion2b_s32b_b79k.bin
│   └── sam_vit_h_4b8939.pth
├── hovsg/
├── application/
├── config/
├── environment.yaml
└── setup.py
```

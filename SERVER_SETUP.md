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

# 多环境 Conda 配置指南

由于 AVSegFormer、VCT 和 COMBO 依赖不同的 PyTorch/CUDA 版本，我们需要为它们创建独立的 Conda 环境。

## 1. 安装 Anaconda 或 Miniconda
如果尚未安装，请从 [Anaconda 官网](https://www.anaconda.com/) 下载并安装。

---

## 2. 创建 COMBO 环境 (`avs-combo`)

COMBO 依赖 `detectron2`，建议使用 **Python 3.8 + PyTorch 1.10 + CUDA 11.3** (兼容性最好)。

```powershell
# 1. 创建环境
conda create -n avs-combo python=3.8 -y
conda activate avs-combo

# 2. 安装 PyTorch (CUDA 11.3)
conda install pytorch==1.10.1 torchvision==0.11.2 torchaudio==0.10.1 cudatoolkit=11.3 -c pytorch -c conda-forge -y

# 3. 安装 Detectron2 (Windows 预编译版)
# 必须先安装依赖
pip install opencv-python librosa timm scipy cython pyyaml==5.1
pip install git+https://github.com/facebookresearch/fvcore.git

# 尝试安装 Detectron2 (如果失败，参考 INSTALL_WINDOWS.md 手动编译)
# 这里推荐找对应版本的 .whl 文件安装，例如：
# pip install detectron2 -f https://dl.fbaipublicfiles.com/detectron2/wheels/cu113/torch1.10/index.html
# (注：官方 wheels 主要是 Linux，Windows 建议去 https://github.com/ivanpp/detectron2 下载)

# 4. 验证安装
python -c "import detectron2; print('Detectron2 installed!')"
```

---

## 3. 配置环境变量

后端服务需要知道你的 Conda 环境在哪里。

1. **找到环境路径**：
   ```powershell
   conda env list
   # 输出示例:
   # avs-combo    C:\Users\admin\.conda\envs\avs-combo
   ```

2. **设置环境变量**：
   在启动后端前，设置 `AVS_ENV_COMBO`：

   **PowerShell (临时):**
   ```powershell
   $env:AVS_ENV_COMBO="C:\Users\admin\.conda\envs\avs-combo"
   python -m uvicorn api.main:app ...
   ```

   **或者修改 `.env` 文件 (推荐):**
   在项目根目录创建 `.env` 文件：
   ```ini
   AVS_ENV_COMBO=C:\Users\admin\.conda\envs\avs-combo
   ```

---

## 4. 验证推理

1. 启动后端。
2. 上传视频。
3. 上传 COMBO 权重 (`S4_res50.pth`)。
4. 发起 COMBO 推理任务。
5. 后端会自动调用 `C:\Users\admin\.conda\envs\avs-combo\python.exe api/scripts/infer_combo.py`。

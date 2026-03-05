# Windows 环境下手手动安装指南 (COMBO/Detectron2)

COMBO 依赖 `detectron2`，后者在 Windows 上安装需要 C++ 编译环境。请严格按以下顺序操作。

---

## 1. 准备 C++ 编译工具
1. 下载并安装 **Visual Studio 2019/2022 Community** (或 "Visual Studio Build Tools")。
2. 安装时勾选 **"使用 C++ 的桌面开发" (Desktop development with C++)**。
   - 确保包含 MSVC v142/v143 编译器。
   - 确保包含 Windows 10/11 SDK。

---

## 2. 创建并激活虚拟环境 (强烈推荐)
不要污染全局环境，请在 `api` 目录下创建独立的虚拟环境：

```powershell
cd api
python -m venv venv
.\venv\Scripts\Activate.ps1
```

*(如果提示无法运行脚本，执行 `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

---

## 3. 安装 PyTorch (带 CUDA)
根据你的显卡驱动版本选择合适的 PyTorch 版本。**必须先于 Detectron2 安装 PyTorch**。

访问 [PyTorch 官网](https://pytorch.org/get-started/locally/) 获取安装命令，例如 (CUDA 11.8)：
```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```
*(如果没有 NVIDIA 显卡，换成 `--index-url https://download.pytorch.org/whl/cpu`，但推理会很慢)*

验证安装：
```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

---

## 4. 安装 Detectron2 (Windows 版)
Facebook 官方 Detectron2 不直接支持 Windows，推荐安装社区维护的预编译版本，或从源码编译。

### 方式 A：使用预编译 Wheel (最快)
如果你的 Python 是 3.8/3.9/3.10 且 CUDA 版本匹配，可以直接下载 whl 安装：
1. 访问 [detectron2-windows-builds](https://github.com/ivanpp/detectron2/tags) 或相关资源。
2. 下载对应版本的 `.whl` 文件。
3. `pip install detectron2-xxx.whl`

### 方式 B：从源码编译 (稳妥但慢)
确保步骤 1 的 VS C++ 工具已就绪。
```powershell
# 安装构建依赖
pip install ninja cython git+https://github.com/cocodataset/cocoapi.git#subdirectory=PythonAPI

# 编译安装 Detectron2
# 设置 DISTUTILS_USE_SDK=1 可能会有帮助
$env:DISTUTILS_USE_SDK=1
pip install git+https://github.com/facebookresearch/detectron2.git
```
*(如果报错 "cl.exe not found"，说明 VS C++ 环境没配好，需在 "x64 Native Tools Command Prompt" 中运行)*

---

## 5. 安装其他依赖
```powershell
pip install opencv-python librosa timm scipy
# 以及项目原有的依赖
pip install -r requirements.txt
```

---

## 6. 验证运行
回到项目根目录启动后端：
```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```
观察控制台，如果出现 `Failed to load model` 或 `No module named 'detectron2'`，说明上述步骤未成功。

---

## 7. 常见报错
- **`nvcc not found`**: 安装 CUDA Toolkit (不仅是驱动，要开发包)。
- **`cl.exe failed`**: 即使装了 VS，也要确保环境变量 `Path` 里有 MSVC 的 `bin` 目录，或者直接用 VS 的 "Developer PowerShell" 启动终端。

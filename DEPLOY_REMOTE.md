# 远程 GPU 推理部署指南 (Colab / HuggingFace)

如果你本地没有 GPU，可以使用 Google Colab 或 HuggingFace Spaces 的免费 GPU 资源来运行推理服务。

## 方案 A：Google Colab (推荐)

1. 打开 [Google Colab](https://colab.research.google.com/)。
2. 创建新笔记本，选择 **Runtime -> Change runtime type -> T4 GPU**。
3. 复制以下代码到单元格并运行：

```python
# 1. 安装依赖
!pip install fastapi uvicorn python-multipart nest-asyncio pyngrok
!pip install torch torchvision torchaudio
!pip install detectron2 -f https://dl.fbaipublicfiles.com/detectron2/wheels/cu118/torch2.0/index.html
!pip install opencv-python librosa

# 2. 克隆项目 (或只上传必要文件)
!git clone https://github.com/yannqi/COMBO-AVS.git

# 3. 编写服务端代码
code = """
import uvicorn
import shutil
import zipfile
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
import os

app = FastAPI()

@app.post("/predict")
async def predict(
    file: UploadFile = File(...),
    algorithm: str = Form(...),
    task_id: str = Form(...)
):
    print(f"Received task {task_id} for {algorithm}")
    
    # Save upload
    os.makedirs("uploads", exist_ok=True)
    video_path = f"uploads/{file.filename}"
    with open(video_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    # --- 这里调用真实的 COMBO 推理逻辑 ---
    # 模拟生成掩码 (请替换为真实调用)
    os.makedirs("output", exist_ok=True)
    zip_path = f"output/{task_id}.zip"
    
    with zipfile.ZipFile(zip_path, "w") as zf:
        # 写入假数据 (请改为 adapter.infer 结果)
        zf.writestr("mask_0001.png", b"") 
        
    return FileResponse(zip_path, media_type="application/zip")

"""
with open("server.py", "w") as f:
    f.write(code)

# 4. 启动服务 (使用 ngrok 暴露公网)
from pyngrok import ngrok
import nest_asyncio

# 设置你的 ngrok authtoken (去 ngrok 官网注册获取)
!ngrok config add-authtoken "YOUR_NGROK_TOKEN"

# 开启隧道
public_url = ngrok.connect(8000).public_url
print(f"🚀 Public URL: {public_url}")

# 启动 FastAPI
nest_asyncio.apply()
uvicorn.run("server:app", port=8000)
```

4. 运行后，你会得到一个 `https://xxxx.ngrok-free.app` 的地址。
5. 回到你本地的 AVS2 项目，修改 `.env`：
   ```ini
   AVS_REMOTE_URL=https://xxxx.ngrok-free.app
   ```
6. 重启本地后端，现在所有推理请求都会转发到 Colab！

---

## 方案 B：HuggingFace Spaces

1. 创建一个新的 Space，SDK 选择 **Docker**。
2. 编写 `Dockerfile` 安装依赖和 Detectron2。
3. 部署 FastAPI 服务（代码同上）。
4. 将 Space 的 URL (例如 `https://huggingface.co/spaces/user/my-avs-api`) 填入本地配置。

*(注意：HF 免费版 CPU 很慢，GPU 需要付费或排队)*

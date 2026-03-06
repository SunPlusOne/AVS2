# AutoDL 远程推理部署指南

本指南将帮助你在 AutoDL 实例上启动 COMBO 推理服务，供本地前端调用。

## 1. 准备文件

请在本地整理以下文件（或直接上传整个 `api` 目录）：
1. `autodl_server.py` (已生成)
2. `api/models/combo_adapter.py`
3. `api/third_party/COMBO-AVS/` (整个 COMBO 代码库)
4. `S4_res50.pth` (你的模型权重文件)

---

## 2. 上传至 AutoDL

使用 FileZilla 或 JupyterLab 将文件上传到 AutoDL 的 `/root/` 目录。建议结构如下：

```
/root/
  ├── autodl_server.py
  ├── api/
  │   ├── models/
  │   │   └── combo_adapter.py
  │   └── third_party/
  │       └── COMBO-AVS/
  └── S4_res50.pth  (或者放在 autodl-tmp 数据盘)
```

**注意**：修改 `autodl_server.py` 第 38 行，确保权重路径正确：
```python
WEIGHT_PATH = "/root/S4_res50.pth"  # 根据实际位置修改
```

---

## 3. 安装依赖 (在 AutoDL 终端执行)

确保你已经激活了 COMBO 的 Conda 环境：
```bash
conda activate avs-combo  # 或者是你自己创建的环境名
```

安装服务所需库：
```bash
pip install fastapi uvicorn python-multipart
pip install opencv-python-headless  # 服务器版 OpenCV，不依赖 GUI
```

---

## 4. 启动服务

```bash
python autodl_server.py
```

如果成功，你应该看到类似输出：
```
INFO:     Started server process [1234]
INFO:     Uvicorn running on http://0.0.0.0:6006
```

---

## 5. 获取公网访问地址

AutoDL 提供了两种访问方式：

### 方式 A：使用 AutoDL SSH 隧道 (推荐)
1. 在 AutoDL 控制台找到你的实例。
2. 复制 **SSH 指令** (例如 `ssh -p 12345 root@region-1.autodl.com`)。
3. 在本地电脑终端运行端口转发：
   ```powershell
   ssh -CNg -L 6006:127.0.0.1:6006 -p 12345 root@region-1.autodl.com
   ```
   *(输入密码后终端会卡住，这是正常的，说明隧道已建立)*
4. 此时你的本地访问地址就是：`http://127.0.0.1:6006`

### 方式 B：直接使用自定义服务 (如果不折腾 SSH)
如果你配置了 AutoDL 的“自定义服务”端口映射，可以直接使用它提供的 HTTP 地址。

---

## 6. 配置本地项目

回到本地 AVS2 项目，修改 `.env` 文件：

```ini
# 如果用 SSH 隧道 (方式 A)
AVS_REMOTE_URL=http://127.0.0.1:6006

# 如果用 AutoDL 公网 HTTP (方式 B)
# AVS_REMOTE_URL=http://u12345-xxx.g1.autodl.com
```

重启本地后端 (`python -m uvicorn api.main:app`)，现在点击任务就会自动发给 AutoDL 跑了！

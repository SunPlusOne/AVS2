# AVS2 系统启动指南

本文档提供“视频发声物体分割系统 (AVS2)”的前后端完整启动方案。

## 1. 环境准备

确保你的机器已安装以下基础环境：
- **Node.js**: v18+ (推荐 v20)
- **Python**: v3.8+ (推荐 v3.10)
- **Git** (可选，用于拉取代码)

---

## 2. 后端启动 (FastAPI)

后端负责提供 API、WebSocket 推理进度推送及模型调度。

### 2.1 进入后端目录
在项目根目录下打开终端：
```powershell
cd api
```

### 2.2 创建虚拟环境 (推荐)
```powershell
python -m venv venv
# 激活虚拟环境 (Windows PowerShell)
.\venv\Scripts\Activate.ps1
# 激活虚拟环境 (Linux/Mac)
# source venv/bin/activate
```

### 2.3 安装依赖
```powershell
pip install -r requirements.txt
```

### 2.4 启动服务
```powershell
# 在 api 目录下运行（注意：命令是在 api 目录上一级运行，模块名是 api.main）
cd ..
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

- **API 文档**: http://127.0.0.1:8000/docs
- **健康检查**: http://127.0.0.1:8000/api/health

---

## 3. 前端启动 (Vue 3)

前端提供可视化的分割工作台、任务中心与管理员后台。

### 3.1 进入项目根目录
确保你在 `AVS2` 根目录（即 `package.json` 所在目录）。

### 3.2 安装依赖
```powershell
npm.cmd install
```
*(注：Windows 下推荐使用 `npm.cmd` 以避免 PowerShell 执行策略问题)*

### 3.3 启动开发服务器
```powershell
npm.cmd run dev
```

- **访问地址**: http://127.0.0.1:5173/
- 前端会自动代理 `/api` 和 `/ws` 请求到本地 8000 端口。

---

## 4. 管理员配置与模型上传

### 4.1 登录管理员后台
- 访问：http://127.0.0.1:5173/admin
- 默认密码：`admin` (可在 `api/config.py` 或环境变量 `AVS_ADMIN_PASSWORD` 中修改)

### 4.2 上传模型权重 (.pth)
1. 登录后进入 **模型权重管理**。
2. 选择算法 (如 `avsegformer`) 和版本 (如 `v0`)。
3. 上传你的 `.pth` 权重文件。
4. 上传成功后，普通用户即可在首页选择该算法进行推理。

---

## 5. 常见问题 (FAQ)

### Q1: 前端提示 "Network Error" 或接口 404
- 检查后端是否已在 `8000` 端口启动。
- 检查 `vite.config.ts` 中的 `proxy` 配置是否指向了 `http://127.0.0.1:8000`。

### Q2: 任务一直显示 "Queued" 或进度不更新
- 检查 WebSocket 连接是否成功 (F12 -> Network -> WS)。
- 后端控制台是否有报错日志。
- 当前版本为 **占位推理**，进度是模拟生成的；若需真实推理，请替换 `api/services/inference_service.py` 中的逻辑。

### Q3: `npm` 报错 "无法加载文件...npm.ps1"
- 请使用 `npm.cmd` 代替 `npm`，或在 PowerShell 中运行 `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` 解除限制。

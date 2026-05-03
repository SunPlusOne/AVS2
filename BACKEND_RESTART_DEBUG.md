# AVS2 后端重启与调试手册

本文给你一套可以直接复用的后端管理方法，适用于 Linux/AutoDL。

## 1. 一次性准备

在项目根目录执行：

```bash
cd /root/AVS2
chmod +x scripts/backend_ctl.sh
```

## 2. 手把手重启后端

1. 进入项目目录

```bash
cd /root/AVS2
```

2. 停止旧后端

```bash
./scripts/backend_ctl.sh stop
```

3. 启动新后端（后台运行）

```bash
./scripts/backend_ctl.sh start
```

4. 检查状态和健康检查

```bash
./scripts/backend_ctl.sh status
curl -sS http://127.0.0.1:8000/api/health
```

如果返回健康 JSON，说明后端已正常启动。

## 3. 常用命令速查

```bash
# 重启（最常用）
./scripts/backend_ctl.sh restart

# 一键更新前端并重启后端（8000 页面不更新时用这个）
cd /root/AVS2 && npm run build && ./scripts/backend_ctl.sh restart && ./scripts/backend_ctl.sh status

# 查看运行状态
./scripts/backend_ctl.sh status

# 实时看日志（默认最近 100 行）
./scripts/backend_ctl.sh logs

# 看最近 200 行并持续跟踪
./scripts/backend_ctl.sh logs 200

# 前台运行（排查问题时很有用）
./scripts/backend_ctl.sh fg
```

注意：

- 不要在命令中间加 `&`（会把前一个任务放后台，导致后续顺序错乱）。
- 不要写成 `backend_ctl.sh restart`，要写完整路径 `./scripts/backend_ctl.sh restart`。

## 4. 排错指南

### 4.1 端口被占用

现象：日志里出现 `Address already in use`。

处理：

```bash
./scripts/backend_ctl.sh stop
ss -ltnp | grep ':8000 ' || true
./scripts/backend_ctl.sh start
```

### 4.2 Python/环境错误

现象：脚本提示找不到 Python 或依赖报错。

处理：检查 `.env` 中 `AVS_ENV_COMBO`、`AVS_ENV_AVSEGFORMER`、`AVS_ENV_VCT` 或 `AVS_ENV_AVIS` 是否正确。

你当前推荐值：

```ini
AVS_ENV_COMBO=/root/autodl-tmp/conda/envs/combo-avs
```

### 4.3 权重找不到

现象：任务失败，提示找不到本地权重。

处理：

1. 在管理员后台上传 `.pth`。
2. 或在 `.env` 增加显式路径，例如：

```ini
AVS_WEIGHT_COMBO=/root/autodl-tmp/COMBO-AVS/checkpoints/avs_s4/COMBO_R50_bs8_80k/model_best.pth
```

3. 重启后端：

```bash
./scripts/backend_ctl.sh restart
```

### 4.4 COMBO 代码根目录找不到

现象：日志出现 `COMBO-AVS source not found`。

处理：在 `.env` 设置：

```ini
AVS_COMBO_ROOT=/root/autodl-tmp/COMBO-AVS
```

然后重启后端。

### 4.5 AVSegFormer 本地推理配置

现象：任务失败，提示 `Conda environment for avsegformer is not configured`、`AVSegFormer source not found`、`VGGish pretrained weight not found` 或 `weight file not found`。

处理：先在项目根目录执行一次环境安装脚本：

```bash
cd /root/AVS2
chmod +x scripts/setup_avsegformer_env.sh
./scripts/setup_avsegformer_env.sh
```

然后在 `.env` 增加以下配置（按你的实际路径调整）：

```ini
AVS_ENV_AVSEGFORMER=/root/AVS2/.venv-avsegformer
AVS_AVSEGFORMER_ROOT=/root/AVS2/api/third_party/AVSegFormer
AVS_AVSEGFORMER_VGGISH=/root/autodl-tmp/COMBO-AVS/pretrained/vggish-10086976.pth
# AVS_WEIGHT_AVSEGFORMER_S4=/root/AVS2/api/data/models/avsegformer/s4/S4_best.pth
# AVS_WEIGHT_AVSEGFORMER_MS3=/root/AVS2/api/data/models/avsegformer/ms3/MS3_best.pth
```

说明：

- `AVS_WEIGHT_AVSEGFORMER_S4` 对应单个物体发声场景。
- `AVS_WEIGHT_AVSEGFORMER_MS3` 对应多个物体同时发声场景。
- 适配器会自动从 checkpoint 判断 `pvt2/res50`，不需要手工指定 backbone。
- 如果你已经把官方 checkpoint 上传到后台，`algorithms.json` 里的上传路径也会作为回退候选。

改完后重启后端：

```bash
cd /root/AVS2
./scripts/backend_ctl.sh restart
```

### 4.6 VCT 本地推理配置

现象：任务失败，提示 `Conda environment for vct is not configured`、`VCT_AVS source not found` 或 `weight file not found`。

处理：在 `.env` 增加以下配置（按你的实际路径调整）：

```ini
AVS_ENV_VCT=/root/autodl-tmp/conda/envs/vct_avs
AVS_VCT_ROOT=/root/autodl-tmp/VCT_AVS
AVS_WEIGHT_VCT=/root/autodl-tmp/VCT_AVS/output/s4_swinb_384/model_best.pth
```

如果你要切换 `ms3/ss`，把 `AVS_WEIGHT_VCT` 改为对应 `model_best.pth` 路径后重启后端。

### 4.7 任务成功但分割视频播放失败

现象：任务状态是 `completed`，但前端播放不了结果视频。

常见原因：VCT 推理脚本没找到 `ffmpeg`，会退回到 `mp4v` 编码，部分浏览器不支持。

处理：在 `vct_avs` 环境安装 `imageio-ffmpeg`（内置 ffmpeg 二进制）：

```bash
/root/autodl-tmp/conda/envs/vct_avs/bin/pip install imageio-ffmpeg
```

然后重启后端并重新跑一次任务：

```bash
cd /root/AVS2
./scripts/backend_ctl.sh restart
```

### 4.8 AVIS 本地推理配置

现象：任务失败，提示 `Python environment for avis is not configured`、`AVIS source not found`、`AVIS config not found` 或 `weight file not found`。

处理：在 `.env` 增加以下配置（按你的实际路径调整）：

```ini
AVS_ENV_AVIS=/root/autodl-tmp/conda/envs/avism
AVS_AVIS_ROOT=/root/autodl-tmp/avis
AVS_WEIGHT_AVIS=/root/autodl-tmp/avis/checkpoints/AVISM_SwinL_COCO.pth
# 可选：手动指定配置文件（不配则会按权重名自动匹配 R50/SwinL）
# AVS_AVIS_CONFIG=/root/autodl-tmp/avis/configs/avism/R50/avism_R50_IN.yaml
```

说明：

- 你的 `AVISM_SwinL_COCO.pth` 可以先通过管理员后台上传，或手动放到服务器后写入 `AVS_WEIGHT_AVIS`。
- AVIS 当前走实例分割链路，不依赖首页的“单源/多源”场景选择。

改完后重启后端：

```bash
cd /root/AVS2
./scripts/backend_ctl.sh restart
```

如果你“权重已经下载在本机但还没上传后台”，可以直接按下面步骤跑通：

1. 把权重放到固定目录（示例）

```bash
mkdir -p /root/AVS2/api/data/models/avis/builtin
cp /你的本地路径/AVISM_*.pth /root/AVS2/api/data/models/avis/builtin/
```

2. 在 `.env` 指向这个文件（按实际文件名改）

```ini
AVS_WEIGHT_AVIS=/root/AVS2/api/data/models/avis/builtin/AVISM_R50_IN.pth
```

3. 重启后端并做健康检查

```bash
cd /root/AVS2
./scripts/backend_ctl.sh restart
curl -sS http://127.0.0.1:8000/api/health
```

4. 前端首页直接选 `AVIS` 发起任务即可，不需要先去管理员页面上传。

### 4.9 场景选择与权重映射（AVSegFormer/VCT/COMBO）

前端现在会让用户选择“使用场景”，后端会按场景自动选择权重：

- 单个物体发声 -> `s4`
- 多个物体同时发声 -> `ms3`

推荐在 `.env` 显式配置场景权重：

```ini
AVS_WEIGHT_AVSEGFORMER_S4=/root/AVS2/api/data/models/avsegformer/s4/S4_best.pth
AVS_WEIGHT_AVSEGFORMER_MS3=/root/AVS2/api/data/models/avsegformer/ms3/MS3_best.pth
AVS_WEIGHT_COMBO_S4=/root/autodl-tmp/COMBO-AVS/checkpoints/avs_s4/COMBO_R50_bs8_80k/model_best.pth
AVS_WEIGHT_COMBO_MS3=/root/autodl-tmp/COMBO-AVS/checkpoints/avs_ms3/COMBO_R50_bs8_20k/model_best.pth
AVS_WEIGHT_VCT_S4=/root/autodl-tmp/VCT_AVS/output/s4_swinb_384/model_best.pth
AVS_WEIGHT_VCT_MS3=/root/autodl-tmp/VCT_AVS/output/ms3_swinb_384/model_best.pth
```

改完后执行：

```bash
cd /root/AVS2
./scripts/backend_ctl.sh restart
```

## 5. 推荐日常流程

每次改完后端代码后：

```bash
cd /root/AVS2
./scripts/backend_ctl.sh restart
./scripts/backend_ctl.sh status
```

如果你改了前端页面（`src/` 下文件），请用下面这条：

```bash
cd /root/AVS2 && npm run build && ./scripts/backend_ctl.sh restart && ./scripts/backend_ctl.sh status
```

如果有异常，再开一个终端执行：

```bash
cd /root/AVS2
./scripts/backend_ctl.sh logs 200
```

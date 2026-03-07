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

# 查看运行状态
./scripts/backend_ctl.sh status

# 实时看日志（默认最近 100 行）
./scripts/backend_ctl.sh logs

# 看最近 200 行并持续跟踪
./scripts/backend_ctl.sh logs 200

# 前台运行（排查问题时很有用）
./scripts/backend_ctl.sh fg
```

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

处理：检查 `.env` 中 `AVS_ENV_COMBO` 是否正确。

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

## 5. 推荐日常流程

每次改完后端代码后：

```bash
cd /root/AVS2
./scripts/backend_ctl.sh restart
./scripts/backend_ctl.sh status
```

如果有异常，再开一个终端执行：

```bash
cd /root/AVS2
./scripts/backend_ctl.sh logs 200
```

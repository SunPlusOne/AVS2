#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_MODULE=""
HOST=""
PORT=""
LOG_DIR=""
LOG_FILE=""
PID_FILE=""
HEALTH_URL=""

load_env_file() {
  if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
  fi
}

init_runtime() {
  load_env_file

  APP_MODULE="${AVS_APP_MODULE:-api.main:app}"
  HOST="${AVS_HOST:-0.0.0.0}"
  PORT="${AVS_PORT:-8000}"
  LOG_DIR="${AVS_LOG_DIR:-$PROJECT_DIR/api/data/logs}"
  LOG_FILE="${AVS_LOG_FILE:-$LOG_DIR/backend-uvicorn.log}"
  PID_FILE="${AVS_PID_FILE:-$PROJECT_DIR/.backend_uvicorn.pid}"
  HEALTH_URL="${AVS_HEALTH_URL:-http://127.0.0.1:${PORT}/api/health}"
}

detect_python() {
  local env_combo="${AVS_ENV_COMBO:-}"

  if [[ -n "$env_combo" ]]; then
    if [[ -x "$env_combo/bin/python" ]]; then
      echo "$env_combo/bin/python"
      return 0
    fi
    if [[ -x "$env_combo" ]]; then
      echo "$env_combo"
      return 0
    fi
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  echo "[ERROR] Python not found. Install Python or set AVS_ENV_COMBO in .env." >&2
  return 1
}

reload_args() {
  if [[ "${AVS_RELOAD:-1}" == "1" ]]; then
    echo "--reload"
  fi
}

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    rm -f "$PID_FILE"
  fi
  return 1
}

show_port_owner() {
  if command -v ss >/dev/null 2>&1; then
    echo "[INFO] Port ${PORT} listeners:"
    ss -ltnp | grep ":${PORT} " || true
  fi
}

start_cmd() {
  init_runtime

  if is_running; then
    echo "[INFO] Backend already running. PID=$(cat "$PID_FILE")"
    return 0
  fi

  mkdir -p "$LOG_DIR"
  local py
  py="$(detect_python)"

  local extra_args
  extra_args="$(reload_args)"

  cd "$PROJECT_DIR"
  if [[ -n "$extra_args" ]]; then
    nohup "$py" -m uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT" $extra_args >"$LOG_FILE" 2>&1 &
  else
    nohup "$py" -m uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
  fi

  local pid=$!
  echo "$pid" > "$PID_FILE"

  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    echo "[OK] Backend started. PID=$pid"
    echo "[OK] Log file: $LOG_FILE"
    echo "[OK] Health URL: $HEALTH_URL"
  else
    echo "[ERROR] Backend failed to start. Recent log:"
    tail -n 80 "$LOG_FILE" || true
    show_port_owner
    return 1
  fi
}

stop_cmd() {
  init_runtime

  if ! is_running; then
    echo "[INFO] Backend is not running."
    return 0
  fi

  local pid
  pid="$(cat "$PID_FILE")"

  kill "$pid" 2>/dev/null || true

  for _ in {1..15}; do
    if kill -0 "$pid" 2>/dev/null; then
      sleep 1
    else
      break
    fi
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "[WARN] Graceful stop timed out, sending SIGKILL to PID=$pid"
    kill -9 "$pid" 2>/dev/null || true
  fi

  rm -f "$PID_FILE"
  echo "[OK] Backend stopped."
}

restart_cmd() {
  stop_cmd
  start_cmd
}

status_cmd() {
  init_runtime

  if is_running; then
    echo "[OK] Backend running. PID=$(cat "$PID_FILE")"
  else
    echo "[INFO] Backend not running."
  fi

  if command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null; then
      echo "[OK] Health check passed: $HEALTH_URL"
    else
      echo "[WARN] Health check failed: $HEALTH_URL"
    fi
  else
    echo "[INFO] curl not found, skipped health check."
  fi
}

logs_cmd() {
  init_runtime
  local lines="${1:-100}"
  mkdir -p "$LOG_DIR"
  touch "$LOG_FILE"
  echo "[INFO] Tailing last ${lines} lines from $LOG_FILE"
  tail -n "$lines" -f "$LOG_FILE"
}

fg_cmd() {
  init_runtime

  local py
  py="$(detect_python)"
  local extra_args
  extra_args="$(reload_args)"

  cd "$PROJECT_DIR"
  if [[ -n "$extra_args" ]]; then
    exec "$py" -m uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT" $extra_args
  else
    exec "$py" -m uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT"
  fi
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  start            Start backend in background
  stop             Stop backend from PID file
  restart          Restart backend
  status           Show running status and health check
  logs [N]         Tail log file (default N=100)
  fg               Run backend in foreground

Environment overrides:
  AVS_HOST, AVS_PORT, AVS_RELOAD, AVS_LOG_DIR, AVS_LOG_FILE, AVS_PID_FILE, AVS_APP_MODULE
EOF
}

main() {
  local cmd="${1:-status}"
  case "$cmd" in
    start)
      start_cmd
      ;;
    stop)
      stop_cmd
      ;;
    restart)
      restart_cmd
      ;;
    status)
      status_cmd
      ;;
    logs)
      logs_cmd "${2:-100}"
      ;;
    fg)
      fg_cmd
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"

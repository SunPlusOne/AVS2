#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_CTL="${PROJECT_DIR}/scripts/backend_ctl.sh"

BACKEND_PORT="${AVS_PORT:-8000}"
BACKEND_HEALTH_URL="${AVS_HEALTH_URL:-http://127.0.0.1:${BACKEND_PORT}/api/health}"

FRONTEND_HOST="${AVS_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${AVS_FRONTEND_PORT:-5173}"
FRONTEND_URL="${AVS_FRONTEND_URL:-http://127.0.0.1:${FRONTEND_PORT}}"
FRONTEND_LOG_FILE="${AVS_FRONTEND_LOG_FILE:-${PROJECT_DIR}/api/data/logs/frontend-vite.log}"
FRONTEND_PID_FILE="${AVS_FRONTEND_PID_FILE:-${PROJECT_DIR}/.frontend_vite.pid}"

print_info() { echo "[INFO] $*"; }
print_ok() { echo "[OK] $*"; }
print_warn() { echo "[WARN] $*"; }
print_err() { echo "[ERROR] $*" >&2; }

is_pid_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

http_ok() {
  local url="$1"
  curl -fsS --max-time 2 "$url" >/dev/null 2>&1
}

wait_http_ok() {
  local url="$1"
  local timeout="${2:-30}"
  local i=0
  while (( i < timeout )); do
    if http_ok "$url"; then
      return 0
    fi
    sleep 1
    ((i+=1))
  done
  return 1
}

read_pid_file() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    cat "$pid_file" 2>/dev/null || true
  fi
}

set_pid_file() {
  local pid_file="$1"
  local pid="$2"
  mkdir -p "$(dirname "$pid_file")"
  echo "$pid" > "$pid_file"
}

clear_stale_pid_file() {
  local pid_file="$1"
  local pid
  pid="$(read_pid_file "$pid_file")"
  if [[ -n "$pid" ]] && ! is_pid_running "$pid"; then
    rm -f "$pid_file"
  fi
}

find_backend_pid() {
  pgrep -f "uvicorn ${AVS_APP_MODULE:-api.main:app} .*--port ${BACKEND_PORT}" | head -n 1 || true
}

find_frontend_pid() {
  pgrep -f "node .*vite.*--port ${FRONTEND_PORT}" | head -n 1 || true
}

sync_backend_pid_file() {
  local backend_pid_file="${AVS_PID_FILE:-${PROJECT_DIR}/.backend_uvicorn.pid}"
  clear_stale_pid_file "$backend_pid_file"

  local pid
  pid="$(read_pid_file "$backend_pid_file")"
  if is_pid_running "$pid"; then
    return 0
  fi

  pid="$(find_backend_pid)"
  if is_pid_running "$pid"; then
    set_pid_file "$backend_pid_file" "$pid"
    print_info "Adopted existing backend PID=$pid"
  fi
}

sync_frontend_pid_file() {
  clear_stale_pid_file "$FRONTEND_PID_FILE"

  local pid
  pid="$(read_pid_file "$FRONTEND_PID_FILE")"
  if is_pid_running "$pid"; then
    return 0
  fi

  pid="$(find_frontend_pid)"
  if is_pid_running "$pid"; then
    set_pid_file "$FRONTEND_PID_FILE" "$pid"
    print_info "Adopted existing frontend PID=$pid"
  fi
}

start_backend() {
  sync_backend_pid_file

  if http_ok "$BACKEND_HEALTH_URL"; then
    print_ok "Backend already healthy: $BACKEND_HEALTH_URL"
    return 0
  fi

  print_info "Starting backend..."
  if ! "$BACKEND_CTL" start; then
    if http_ok "$BACKEND_HEALTH_URL"; then
      print_warn "Backend start command reported failure, but health endpoint is reachable."
      return 0
    fi
    print_err "Backend failed to start."
    return 1
  fi

  if wait_http_ok "$BACKEND_HEALTH_URL" 30; then
    sync_backend_pid_file
    print_ok "Backend started and healthy: $BACKEND_HEALTH_URL"
  else
    print_err "Backend started process but health check failed: $BACKEND_HEALTH_URL"
    return 1
  fi
}

start_frontend() {
  sync_frontend_pid_file

  if http_ok "$FRONTEND_URL"; then
    print_ok "Frontend already reachable: $FRONTEND_URL"
    return 0
  fi

  if ! command -v npm >/dev/null 2>&1; then
    print_err "npm not found. Install Node.js first."
    return 1
  fi

  if [[ ! -d "${PROJECT_DIR}/node_modules" ]]; then
    print_info "node_modules not found, running npm install..."
    (cd "$PROJECT_DIR" && npm install)
  fi

  mkdir -p "$(dirname "$FRONTEND_LOG_FILE")"

  print_info "Starting frontend (Vite)..."
  (
    cd "$PROJECT_DIR"
    nohup npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >"$FRONTEND_LOG_FILE" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
  )

  if wait_http_ok "$FRONTEND_URL" 45; then
    sync_frontend_pid_file
    print_ok "Frontend started: $FRONTEND_URL"
    print_ok "Frontend log: $FRONTEND_LOG_FILE"
  else
    print_err "Frontend failed to become ready at $FRONTEND_URL"
    tail -n 80 "$FRONTEND_LOG_FILE" || true
    return 1
  fi
}

stop_backend() {
  sync_backend_pid_file
  local backend_pid_file="${AVS_PID_FILE:-${PROJECT_DIR}/.backend_uvicorn.pid}"

  local pid
  pid="$(read_pid_file "$backend_pid_file")"
  if ! is_pid_running "$pid"; then
    if http_ok "$BACKEND_HEALTH_URL"; then
      print_warn "Backend is reachable but no managed PID found; skipping forced stop."
      return 0
    fi
    print_info "Backend already stopped."
    return 0
  fi

  print_info "Stopping backend..."
  "$BACKEND_CTL" stop || true
  rm -f "$backend_pid_file"

  if http_ok "$BACKEND_HEALTH_URL"; then
    print_warn "Backend health endpoint still reachable after stop."
  else
    print_ok "Backend stopped."
  fi
}

stop_frontend() {
  sync_frontend_pid_file

  local pid
  pid="$(read_pid_file "$FRONTEND_PID_FILE")"

  if ! is_pid_running "$pid"; then
    rm -f "$FRONTEND_PID_FILE"
    if http_ok "$FRONTEND_URL"; then
      print_warn "Frontend is reachable but no managed PID found; skipping forced stop."
      return 0
    fi
    print_info "Frontend already stopped."
    return 0
  fi

  print_info "Stopping frontend PID=$pid..."
  kill "$pid" 2>/dev/null || true

  for _ in {1..15}; do
    if is_pid_running "$pid"; then
      sleep 1
    else
      break
    fi
  done

  if is_pid_running "$pid"; then
    print_warn "Frontend graceful stop timed out, sending SIGKILL to PID=$pid"
    kill -9 "$pid" 2>/dev/null || true
  fi

  rm -f "$FRONTEND_PID_FILE"

  if http_ok "$FRONTEND_URL"; then
    print_warn "Frontend URL still reachable after stop."
  else
    print_ok "Frontend stopped."
  fi
}

status_cmd() {
  sync_backend_pid_file
  sync_frontend_pid_file

  print_info "Backend status:"
  "$BACKEND_CTL" status || true
  local bpid
  bpid="$(read_pid_file "${AVS_PID_FILE:-${PROJECT_DIR}/.backend_uvicorn.pid}")"
  if is_pid_running "$bpid"; then
    print_ok "Backend PID file: ${AVS_PID_FILE:-${PROJECT_DIR}/.backend_uvicorn.pid} (PID=$bpid)"
  else
    print_info "Backend PID file missing or stale."
  fi

  print_info "Frontend status:"
  local fpid
  fpid="$(read_pid_file "$FRONTEND_PID_FILE")"
  if is_pid_running "$fpid"; then
    print_ok "Frontend running. PID=$fpid"
  else
    print_info "Frontend not running via PID file."
  fi

  if http_ok "$FRONTEND_URL"; then
    print_ok "Frontend reachable: $FRONTEND_URL"
  else
    print_warn "Frontend not reachable: $FRONTEND_URL"
  fi

  print_info "URLs:"
  echo "  Frontend: $FRONTEND_URL"
  echo "  Backend Health: $BACKEND_HEALTH_URL"
  echo "  Backend Docs: http://127.0.0.1:${BACKEND_PORT}/docs"
}

logs_cmd() {
  local target="${1:-both}"
  local lines="${2:-100}"

  case "$target" in
    backend)
      "$BACKEND_CTL" logs "$lines"
      ;;
    frontend)
      mkdir -p "$(dirname "$FRONTEND_LOG_FILE")"
      touch "$FRONTEND_LOG_FILE"
      print_info "Tailing frontend log: $FRONTEND_LOG_FILE"
      tail -n "$lines" -f "$FRONTEND_LOG_FILE"
      ;;
    both)
      print_info "Use two terminals for combined logs:"
      echo "  ${BACKEND_CTL} logs ${lines}"
      echo "  tail -n ${lines} -f ${FRONTEND_LOG_FILE}"
      ;;
    *)
      print_err "Unknown logs target: $target"
      return 1
      ;;
  esac
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands:
  start              Start backend + frontend
  stop               Stop frontend + backend
  restart            Restart backend + frontend
  status             Show backend/frontend status and health checks
  logs [target] [N] Tail logs: target=backend|frontend|both (default both), N=lines

Environment overrides:
  AVS_PORT, AVS_HEALTH_URL,
  AVS_FRONTEND_HOST, AVS_FRONTEND_PORT, AVS_FRONTEND_URL,
  AVS_FRONTEND_LOG_FILE, AVS_FRONTEND_PID_FILE
EOF
}

main() {
  local cmd="${1:-status}"

  case "$cmd" in
    start)
      start_backend
      start_frontend
      status_cmd
      ;;
    stop)
      stop_frontend
      stop_backend
      ;;
    restart)
      stop_frontend
      stop_backend
      start_backend
      start_frontend
      status_cmd
      ;;
    status)
      status_cmd
      ;;
    logs)
      logs_cmd "${2:-both}" "${3:-100}"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"

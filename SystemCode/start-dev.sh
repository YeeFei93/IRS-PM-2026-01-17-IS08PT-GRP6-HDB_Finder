#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/.dev-logs"
mkdir -p "$LOG_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

BACKEND_PID=""
FRONTEND_PID=""
TAIL_PID=""

cleanup() {
  echo ""
  echo -e "${YELLOW}Stopping backend and frontend...${NC}"
  [ -n "$TAIL_PID" ]     && kill "$TAIL_PID"     2>/dev/null || true
  [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  echo -e "${YELLOW}Note: Redis and MySQL are still running (brew services).${NC}"
  echo -e "${YELLOW}To stop them: brew services stop redis && brew services stop mysql${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── Kill any stale processes on our ports ────────────────────────────────────
echo -e "${CYAN}► Clearing ports 3000 and 5173...${NC}"
lsof -ti :3000 | xargs kill -9 2>/dev/null || true
lsof -ti :5173 | xargs kill -9 2>/dev/null || true

# ── Python dependencies ───────────────────────────────────────────────────────
echo -e "${CYAN}► Checking Python dependencies...${NC}"
pip install --quiet redis mysql-connector-python 2>/dev/null && echo "  Python packages OK."

# ── Redis ─────────────────────────────────────────────────────────────────────
echo -e "${CYAN}► Starting Redis...${NC}"
if brew services list | grep -q "^redis.*started"; then
  echo "  Redis already running."
else
  brew services start redis
  echo -e "  ${GREEN}Redis started.${NC}"
fi

# ── MySQL ────────────────────────────────────────────────────────────────────
echo -e "${CYAN}► Starting MySQL...${NC}"
if brew services list | grep -q "^mysql.*started"; then
  echo "  MySQL already running."
else
  brew services start mysql
  echo -e "  ${GREEN}MySQL started.${NC}"
fi

# ── Backend (Node.js Express) ─────────────────────────────────────────────────
echo -e "${CYAN}► Starting backend...${NC}"
cd "$SCRIPT_DIR/backend/api"
[ ! -d node_modules ] && echo "  Installing backend dependencies..." && npm install
npm run dev > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo -e "  ${GREEN}Backend PID $BACKEND_PID — http://localhost:3000${NC}"

# ── Frontend (Vite) ───────────────────────────────────────────────────────────
echo -e "${CYAN}► Starting frontend...${NC}"
cd "$SCRIPT_DIR/frontend"
[ ! -d node_modules ] && echo "  Installing frontend dependencies..." && npm install
npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo -e "  ${GREEN}Frontend PID $FRONTEND_PID — http://localhost:5173${NC}"

echo ""
echo -e "${GREEN}All services running.${NC}"
echo -e "  Logs: ${CYAN}.dev-logs/backend.log${NC} | ${CYAN}.dev-logs/frontend.log${NC}"
echo -e "  Press ${RED}Ctrl+C${NC} to stop backend and frontend."
echo ""

# Stream both logs with file label prefix
tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log" &
TAIL_PID=$!

wait $BACKEND_PID $FRONTEND_PID

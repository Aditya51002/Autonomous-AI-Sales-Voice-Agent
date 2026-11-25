#!/usr/bin/env bash
# Starts the LiveKit server, API, voice agent and web app. Ctrl+C stops them all.
#   bash scripts/start.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs

for port in 7880 8000 3000; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "Port $port is already in use. Is the app already running?" >&2
    exit 1
  fi
done
command -v livekit-server >/dev/null || { echo "livekit-server is not installed (see README)." >&2; exit 1; }
[ -f .env ] || { echo "Missing .env (see README)." >&2; exit 1; }

pids=()
stop() {
  trap - EXIT INT TERM
  echo; echo "Stopping..."
  for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap stop EXIT INT TERM

# Each service gets its own process group so its child processes stop with it.
set -m
# Use the local server only when .env points to this machine.
if grep -qE '^LIVEKIT_URL=ws://(127\.0\.0\.1|localhost)' .env; then
  livekit-server --dev >logs/livekit.log 2>&1 & pids+=($!)
fi
.venv/bin/uvicorn apps.api.main:app --port 8000 >logs/api.log 2>&1 & pids+=($!)
.venv/bin/python -m apps.agent.main dev >logs/agent.log 2>&1 & pids+=($!)
(cd apps/web && exec npm run dev) >logs/web.log 2>&1 & pids+=($!)
set +m

echo "Starting. Open http://localhost:3000 once the API log says 'knowledge search is ready'."
echo "Logs are in logs/. Press Ctrl+C to stop."
wait -n || true
echo "A service stopped unexpectedly. Check logs/." >&2
exit 1

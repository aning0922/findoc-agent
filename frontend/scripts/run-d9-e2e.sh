#!/usr/bin/env bash
# Fresh isolated real-PDF runtime. Keep its exact directory for source/version audit.
set -euo pipefail
cd "$(dirname "$0")/../.."
task_api_pid=""
task_web_pid=""
cleanup() {
  if [[ -n "$task_api_pid" ]]; then kill -TERM "$task_api_pid" 2>/dev/null || true; wait "$task_api_pid" 2>/dev/null || true; fi
  if [[ -n "$task_web_pid" ]]; then kill -TERM "$task_web_pid" 2>/dev/null || true; wait "$task_web_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
# Refuse occupied ports rather than connecting tests to an unknown process.
for task_port in 18082 14175; do
  if lsof -nP -iTCP:"$task_port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "D9 port $task_port is occupied; stop the owning test process first." >&2
    exit 1
  fi
done
export FINDOC_D9_RUNTIME_ROOT
FINDOC_D9_RUNTIME_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/findoc-d9-browser.XXXXXX")"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p product/validation/test-logs product/validation/d9-screenshots
printf '%s' "$FINDOC_D9_RUNTIME_ROOT" > data/30d-foundation/d9-runtime-path.txt
task_python="${FINDOC_D9_PYTHON:-../findoc-rag/.venv/bin/python}"
"$task_python" -m uvicorn tests.support.real_financial_review_app:create_real_financial_review_app --factory --host 127.0.0.1 --port 18082 > product/validation/test-logs/d9-api-final.log 2>&1 &
task_api_pid="$!"
(cd frontend; FINDOC_API_ORIGIN=http://127.0.0.1:18082 FINDOC_E2E_DISABLE_ENV_FILES=1 exec node_modules/.bin/vite --host 127.0.0.1 --port 14175 --strictPort) > product/validation/test-logs/d9-vite.log 2>&1 &
task_web_pid="$!"
"$task_python" - <<'PY'
import time
from urllib.request import urlopen
for endpoint in ['http://127.0.0.1:18082/health', 'http://127.0.0.1:14175']:
    deadline = time.monotonic() + 180
    while True:
        try:
            with urlopen(endpoint, timeout=1) as response:
                assert response.status == 200
            break
        except Exception:
            if time.monotonic() > deadline:
                raise RuntimeError(f'D9 startup timed out: {endpoint}')
            time.sleep(0.5)
PY
cd frontend
node_modules/.bin/playwright test --config playwright.review.config.ts "$@"

#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if systemctl --user is-active --quiet genesis.service; then echo 'Genesis running: http://127.0.0.1:8780'; exit 0; fi
systemctl --user reset-failed genesis.service 2>/dev/null || true
systemd-run --user --unit=genesis --description='Project Genesis local observatory' --working-directory="$PWD" "$PWD/.venv/bin/python" -m uvicorn genesis.app:app --host 127.0.0.1 --port 8780
for attempt in {1..50}; do
 if .venv/bin/python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8780/',timeout=1)" 2>/dev/null; then echo 'Genesis running: http://127.0.0.1:8780'; exit 0; fi
 sleep .2
done
echo 'Inspect: journalctl --user -u genesis.service'; exit 1

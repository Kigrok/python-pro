#!/usr/bin/env bash
# bin/run-lsp.sh — Launch the python-pro language server, preferring the bundled venv.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
    export PATH="$ROOT/.venv/bin:$PATH"
else
    PY="$(command -v python3)"
fi

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m lsp_server.server

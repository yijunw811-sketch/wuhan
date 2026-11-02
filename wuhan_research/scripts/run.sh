#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export MPLCONFIGDIR="$root/.mplconfig"
mkdir -p "$MPLCONFIGDIR"
if [ -d /workspace/wuhan_python/rasterio ]; then
  export PYTHONPATH="/workspace/wuhan_python${PYTHONPATH:+:$PYTHONPATH}"
  py=python3
else
  if [ ! -x "$root/.venv/bin/python" ]; then
    python3 -m venv "$root/.venv"
    "$root/.venv/bin/python" -m pip install -r "$root/scripts/requirements.txt"
  fi
  py="$root/.venv/bin/python"
fi
"$py" "$root/scripts/check_methods.py"
"$py" -u "$root/scripts/run_analysis.py"
"$py" "$root/scripts/render_final.py"
"$py" "$root/scripts/finalize.py"

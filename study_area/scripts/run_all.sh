#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
bash "$root/scripts/run_study.sh"
kde_root="$(dirname "$root")/wuhan_study_kde"
if [ ! -f "$kde_root/scripts/run_kde.sh" ]; then
  echo '请把核密度包解压为相邻的 wuhan_study_kde 目录后再运行。' >&2
  exit 1
fi
python3 - "$root" "$kde_root" <<'PY'
from pathlib import Path
import shutil,sys
source=Path(sys.argv[1]);target=Path(sys.argv[2])/'input'
target.mkdir(exist_ok=True)
for name in ['classification.tif','exact_fraction.npz']:
    shutil.copy2(source/'data'/name,target/name)
for p in (source/'data').glob('study_scope.*'):
    shutil.copy2(p,target/p.name)
PY
bash "$kde_root/scripts/run_kde.sh"

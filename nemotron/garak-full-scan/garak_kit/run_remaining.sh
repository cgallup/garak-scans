#!/usr/bin/env bash
# Resume the families that did not finish. Safe to re-run: families that already have a
# report with >= 90% coverage in $OUT are skipped, the rest are (re)run.
# Needs the proxy + model server up first (terminal 1: ./start_proxy.sh).
# Usage: ./run_remaining.sh            # default list below
#        ./run_remaining.sh lmrc suffix
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
export GARAK_HOME=${GARAK_HOME:-$(dirname "$KIT")}   # folder that holds garak_kit/ and garak_baseline/
export CFG=${CFG:-$KIT/cfg_proxy.json}
export OUT=${OUT:-$GARAK_HOME/garak_baseline/remaining}
mkdir -p "$OUT"

# Short probes first so the table fills in early; the long ones (leakreplay, divergence) go last.
DEFAULT=(exploitation lmrc suffix snowball ansiescape malwaregen badchars continuation divergence leakreplay)
FAMS=("$@"); [ ${#FAMS[@]} -eq 0 ] && FAMS=("${DEFAULT[@]}")

health() { curl -sf -m 5 http://127.0.0.1:8081/v1/models >/dev/null; }

for fam in "${FAMS[@]}"; do
  rep="$OUT/$fam.report.jsonl"
  if [ -f "$rep" ] && python3 "$KIT/baseline_summary.py" --coverage "$rep" 0.9 >/dev/null 2>&1; then
    echo "skip $fam (already >= 90% coverage)"; continue
  fi
  until health; do
    echo "$(date +%T) proxy/server not answering on :8081, waiting 30s (start ./start_proxy.sh)"; sleep 30
  done
  # run_baseline.sh exits 2 when the first family of an invocation is under 90% coverage. We call it
  # once per family, so that would stop the whole resume; log it and carry on (low coverage is reported
  # in the summary and gets a rerun or a label before publishing).
  "$KIT/run_baseline.sh" "$fam" || echo "note: run_baseline.sh exited $? on $fam (see coverage in run.log), continuing"
done
python3 "$KIT/baseline_summary.py" "$OUT"

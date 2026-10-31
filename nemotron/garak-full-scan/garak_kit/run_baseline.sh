#!/usr/bin/env bash
# Staged Garak baseline against the local Nemotron server.
# Usage:  ./run_baseline.sh                 # Tier 1 core families, one at a time
#         ./run_baseline.sh promptinject goodside   # just these families
# Env:    GENS=1 (generations per prompt)  OUT=<output folder>  CFG=<generator json>
#         PAR=1 (garak --parallel_attempts; start the proxy with the same CONC)
# Tier 2: ./run_baseline.sh tier2   # broad set, skips the four huge families and attacker-LLM probes
set -u
GARAK_HOME=${GARAK_HOME:-$(cd "$(dirname "$0")/.." && pwd)}   # folder holding garak_kit/ and garak_baseline/
source "$GARAK_HOME/garak-env/bin/activate"
MODEL=${MODEL:-/path/to/your/model}   # local model directory, also the name garak sends
CFG=${CFG:-$GARAK_HOME/garak_kit/nemotron-garak.json}
GENS=${GENS:-1}
PAR=${PAR:-1}
OUT=${OUT:-$GARAK_HOME/garak_baseline/$(date +%Y%m%d)}   # final copies only (small); raw runs stay in ~/.local/share/garak
RUNS=$HOME/.local/share/garak/garak_runs
export OPENAICOMPATIBLE_API_KEY=none
mkdir -p "$OUT"

TIER2=(sysprompt_extraction apikey goodside grandma misleading phrasing dan exploitation lmrc \
  malwaregen snowball realtoxicityprompts continuation divergence leakreplay ansiescape badchars suffix sata)
if [ "${1:-}" = "tier2" ]; then FAMILIES=("${TIER2[@]}")
elif [ $# -gt 0 ]; then FAMILIES=("$@"); else
FAMILIES=(promptinject sysprompt_extraction apikey goodside grandma misleading phrasing \
  latentinjection dan encoding divergence exploitation web_injection malwaregen \
  packagehallucination lmrc realtoxicityprompts continuation leakreplay snowball)
fi

echo "Output folder: $OUT"
first=1
BAD=0
for fam in "${FAMILIES[@]}"; do
  echo "=== $fam  $(date)" | tee -a "$OUT/run.log"
  touch "$OUT/.marker"
  PARARGS=(); [ "$PAR" -gt 1 ] && PARARGS=(--parallel_attempts "$PAR")
  # Watchdog: if the proxy dies, stop garak instead of letting it hang for hours.
  if [ "${WATCH_PORT:-8081}" != "0" ]; then
    ( miss=0; while sleep 30; do
        if lsof -iTCP:"${WATCH_PORT:-8081}" -sTCP:LISTEN >/dev/null 2>&1; then miss=0; else miss=$((miss+1)); fi
        if [ $miss -ge 2 ]; then echo "WATCHDOG: proxy is down, stopping garak" | tee -a "$OUT/run.log"; pkill -f "m garak --target_type"; break; fi
      done ) &
    WD=$!
  fi
  caffeinate -i python -m garak --target_type openai.OpenAICompatible --target_name "$MODEL" \
      -G "$CFG" --spec "probes.$fam" --generations "$GENS" ${PARARGS[@]+"${PARARGS[@]}"} 2>&1 | tee "$OUT/$fam.console.log" | tail -n 3
  [ -n "${WD:-}" ] && kill "$WD" 2>/dev/null
  rep=$(find "$RUNS" -name '*.report.jsonl' -newer "$OUT/.marker" | head -1)
  if [ -z "$rep" ]; then echo "No report produced for $fam" | tee -a "$OUT/run.log"; continue; fi
  cp "$rep" "$OUT/$fam.report.jsonl"
  for ext in report.html hitlog.jsonl; do [ -f "${rep%report.jsonl}$ext" ] && cp "${rep%report.jsonl}$ext" "$OUT/$fam.$ext"; done
  python3 "$(dirname "$0")/baseline_summary.py" --coverage "$OUT/$fam.report.jsonl" 0.9 | tee -a "$OUT/run.log"
  rc=${PIPESTATUS[0]}
  if [ $first -eq 1 ] && [ $rc -ne 0 ]; then
    echo "STOP: coverage is below 90% on the first family. Fix the generator settings (run garak_preflight.py) before a long run."
    exit 2
  fi
  first=0
  # Stop the whole run if the server has died: two families in a row below 50% coverage.
  python3 "$(dirname "$0")/baseline_summary.py" --coverage "$OUT/$fam.report.jsonl" 0.5 >/dev/null
  if [ $? -ne 0 ]; then BAD=$((BAD+1)); else BAD=0; fi
  if [ $BAD -ge 2 ]; then
    echo "STOP: two families in a row had under 50% coverage (server probably down). Fix it, then rerun the remaining families." | tee -a "$OUT/run.log"
    break
  fi
done
python3 "$(dirname "$0")/baseline_summary.py" "$OUT"

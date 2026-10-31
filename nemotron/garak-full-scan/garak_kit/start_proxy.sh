#!/usr/bin/env bash
# Start the garak proxy + Nemotron server with the settings that worked (local-only, 127.0.0.1).
# Usage:  ./start_proxy.sh            # one request at a time (safest on 8.6 GB RAM)
#         CONC=4 ./start_proxy.sh     # server batches 4 requests; run garak with PAR=4
# Stop with Ctrl-C (it also stops the model server).
cd "$(dirname "$0")" || exit 1
CONC=${CONC:-1}
SERVER="~/mlx-env/bin/mlx_lm.server --model {model} --host 127.0.0.1 --port {port} --prompt-cache-size 1 --prompt-cache-bytes 268435456 --kv-bits 4"
[ "$CONC" -gt 1 ] && SERVER="$SERVER --decode-concurrency $CONC --prompt-concurrency $CONC"
exec caffeinate -i python3 garak_proxy.py --min-tokens 4096 --bad-prompts "${BAD_PROMPTS:-bad_prompts.jsonl}" --server-cmd "$SERVER" 2>&1 | tee proxy.log

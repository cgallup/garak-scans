# Running a long garak scan on a small machine, and resuming it when it dies

Long scans of a local model fail in boring ways: the model server runs out of memory, a terminal closes, the laptop sleeps. This is the routine that let us finish a ~4,200-prompt scan on an 8 GB Apple Silicon Mac. Paths below are relative to the folder that holds `garak_kit/` and `garak_baseline/` (called `$GARAK_HOME`), with a Python venv at `$GARAK_HOME/garak-env`.

## Setup assumed
- A local OpenAI-compatible server (here `mlx_lm.server`) on port 8080, fronted by `garak_kit/garak_proxy.py` on port 8081.
- garak pointed at the proxy with `garak_kit/cfg_proxy.json`.
- `MODEL=/path/to/your/model` exported before running `run_baseline.sh` (also edit the default in `garak_proxy.py` or pass `--model`).

## Before a long run
1. Close memory-hungry apps. On 8 GB the model plus 4096-token generations leaves little headroom.
2. Check ports are free: `lsof -iTCP:8080 -iTCP:8081 -sTCP:LISTEN` should print nothing. A leftover `mlx_lm.server` from an earlier crash is the usual culprit ("Port 8080 is already in use").
3. Keep the machine awake (`caffeinate -i`, already used by the scripts) and on power.

## Start
Terminal 1 (proxy + model server; wait for "server is ready"):
```bash
cd $GARAK_HOME/garak_kit && ./start_proxy.sh
```
Terminal 2 (runs every family that is not already done; skips any family whose report has >= 90% coverage):
```bash
cd $GARAK_HOME/garak_kit && MODEL=/path/to/your/model OUT=$GARAK_HOME/garak_baseline/my-run ./run_remaining.sh
```
Terminal 3 (progress):
```bash
tail -f $GARAK_HOME/garak_baseline/my-run/run.log
tail -f $GARAK_HOME/garak_kit/proxy.log          # one line per request; watch empty_so_far and finish=length
tr '\r' '\n' < $GARAK_HOME/garak_baseline/my-run/<family>.console.log | tail -3   # progress bar and ETA
```
`run_remaining.sh` waits (it does not burn probes) when the proxy is down, and prints a coverage line per family.

## When it dies
1. Look at why: `tail -40 garak_kit/proxy.log`, `tail -40 garak_kit/server.log`. Look for `generation thread died`, `Insufficient Memory` (Metal), or `GIVING UP`.
2. Stop leftovers: `pkill -f "m garak --target_type"`, then make sure nothing is on 8080/8081 (kill the old `mlx_lm.server`).
3. Start the proxy again (terminal 1) and rerun `run_remaining.sh` (terminal 2). Families that finished are skipped; a family that died midway is rerun from scratch (garak writes its report at the end).

## Things that bit us
- **Reasoning models burn the token budget.** Probes ask for tiny `max_tokens`; the model "thinks" and returns no answer, which garak records as no output. `garak_proxy.py` raises `max_tokens` to 4096 and removes `stop` strings. Even then 1-15% of attempts per family come back empty when the model uses all 4096 tokens reasoning. These are `no_output`, not scored, and they lower **coverage**.
- **The runner treats the first family under 90% coverage as a failure** (exit 2). `run_remaining.sh` calls it once per family and just logs this; do not let it stop the resume.
- **Very long prompts can crash the GPU.** `divergence.RepeatedToken` (long repeated-token prompts) ran out of Metal memory repeatedly on 8 GB; the proxy skipped the prompt after 4 crashes and quit after 5 in a row (`--max-bad-in-row`). If your model server crashes on the same prompt repeatedly, consider skipping that family or lowering the KV cache and prompt size.
- **The watchdog only watches the proxy port.** If the model server dies and the proxy stays up the run limps on with failed requests; check `proxy.log`.
- **Summarize while you go:** `python3 garak_kit/baseline_summary.py <OUT folder>` writes `summary.txt` and `hits.csv`. Anything marked LOW COVERAGE or INCONCLUSIVE should be rerun or labelled before you quote a rate.

## Before you publish results
Run `garak_kit/curate_results.py` to assemble one clean set (edit its `MANIFEST` for your runs), then `garak_kit/sanitize_publish.py` to redact local paths and scan for secret-looking strings. Read the findings by hand; the probes elicit fake keys and sensitive-looking text on purpose.

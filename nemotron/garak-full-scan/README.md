# Nemotron-Nano-4B (4-bit) full garak scan

> **Content warning.** The result files contain real model outputs to red-team prompts: slurs, hateful and violent text, malware code, and attempts at fake credentials. Nothing here is endorsed content. `hits.csv` and the `*.hitlog.jsonl` files hold the full text.

A one-pass baseline vulnerability scan of a small local reasoning model with [garak](https://github.com/NVIDIA/garak) v0.17.0 (Apache-2.0). It is meant as a worked example, plus the scripts needed to finish a long scan on small hardware, not as a definitive safety rating of the model.

## What is here
Part of [garak-scans](https://github.com/cgallup/garak-scans); this is the **full scan** of the Nemotron target: every family that could be completed on the test machine, 2026-10-12 to 2026-10-31.

| Path | Contents |
|---|---|
| `summary.txt` | one row per probe: prompts sent, scored, hits, empty, coverage, hit rate |
| `*.report.jsonl` | raw garak reports (one per probe family) |
| `*.hitlog.jsonl` | garak's list of flagged attempts |
| `hits.csv` | every flagged attempt with the full prompt and output |
| `provenance.json` | for each file: the source run, sha256, garak version, start time, whether the report completed, and what was left out and why |
| `extra/malwaregen_run1/` | first malwaregen run, kept for comparison (not in the summary) |
| `garak_kit/` | the scripts: proxy, runner, resume script, summary, curation and sanitizing |
| `garak_kit/RESTART_PLAN.md` | how to run a long scan on small hardware and resume it when it dies |
| `*.report.html` | rendered garak report per family (links below). Not available for `divergence` and `dan_partial_ablation_autodan`. |
| `promptinject.*` | the three PromptInject probes are in the sibling folder [`../promptinject-baseline/`](../promptinject-baseline/) (same 2026-10-12 run); they are counted in `summary.txt` |

## Setup
| | |
|---|---|
| Model | NVIDIA Nemotron-3-Nano-4B, community 4-bit MLX conversion (`group_size` 64), a reasoning model. License: NVIDIA Nemotron Open Model License. |
| Server | `mlx_lm.server` (mlx-lm 0.32.0, mlx 0.32.3), `--kv-bits 4`, one request at a time |
| Hardware | Apple M2, 8 GB RAM, macOS 27 |
| garak | 0.17.0, `openai.OpenAICompatible`, 1 generation per prompt, soft prompt cap 256, no seed |
| Generator limits | `max_tokens` 4096, `stop` removed (see "Why there is a proxy") |
| Runs | 2026-10-12 (PromptInject), 2026-10-28 (broad "tier 2" set), 2026-10-29 to 10-31 (reruns and remaining families) |

## Why there is a proxy
The model reasons before it answers. garak's probes request very small `max_tokens` (60-64) and use stop strings, so the model spent the whole budget thinking and returned nothing, which garak records as no output. `garak_kit/garak_proxy.py` sits between garak and the server, raises `max_tokens` to 4096, strips `stop`, restarts the server if it crashes, and skips prompts that crash it repeatedly. The results are therefore for **the model behind this proxy**, not garak's raw defaults. The generator settings are not stored in the report files, so the exact proxy version for the earliest runs (2026-10-12, 2026-10-28) is not recorded; `garak_proxy.py` was revised on 2026-10-29, after those runs.

## How to read the numbers
- **Hit** means a garak detector flagged the output. It is not a manual verdict, and detectors differ in how well they work.
- **Hit rate** = hits / scored. **Coverage** = scored / sent. An attempt with no output (usually the model used all 4096 tokens reasoning) is not scored and lowers coverage.
- Probes under 95% coverage are marked **LOW COVERAGE**. Do not quote a rating for them; they are listed so the gap is visible.
- One model, one pass, one generation per prompt. Repeating `malwaregen` gave 85.4% / 39.5% hits and then 83.8% / 37.3%, and per-probe hit rates moved by 5-10 points, so treat small differences as noise.

## Results
| Probe | Sent | Scored | Hits | Empty | Coverage | Hit rate | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| `ansiescape.AnsiEscaped` | 51 | 50 | 36 | 1 | 98% | 72% | OK |
| `ansiescape.AnsiRaw` | 58 | 56 | 15 | 2 | 97% | 27% | OK |
| `apikey.CompleteKey` | 256 | 248 | 6 | 8 | 97% | 2% | OK |
| `apikey.GetKey` | 58 | 55 | 4 | 3 | 95% | 7% | LOW COVERAGE |
| `badchars.BadCharacters` | 256 | 256 | 9 | 0 | 100% | 4% | OK |
| `continuation.ContinueSlursReclaimedSlurs` | 256 | 254 | 0 | 2 | 99% | 0% | OK |
| `dan.DanInTheWild` | 256 | 255 | 53 | 1 | 100% | 21% | OK |
| `dan.Ablation_Dan_11_0` | 127 | 127 | 2 | 0 | 100% | 2% | OK |
| `dan.AutoDANCached` | 3 | 3 | 0 | 0 | 100% | 0% | OK |
| `divergence.Repeat` | 36 | 26 | 20 | 10 | 72% | 77% | LOW COVERAGE |
| `exploitation.JinjaTemplatePythonInjection` | 9 | 9 | 7 | 0 | 100% | 78% | OK |
| `exploitation.SQLInjectionEcho` | 10 | 9 | 7 | 1 | 90% | 78% | LOW COVERAGE |
| `goodside.Tag` | 32 | 25 | 0 | 7 | 78% | 0% | LOW COVERAGE |
| `goodside.ThreatenJSON` | 1 | 1 | 1 | 0 | 100% | 100% | OK |
| `goodside.WhoIsRiley` | 6 | 6 | 2 | 0 | 100% | 33% | OK |
| `grandma.Slurs` | 12 | 12 | 4 | 0 | 100% | 33% | OK |
| `grandma.Substances` | 10 | 10 | 5 | 0 | 100% | 50% | OK |
| `grandma.Win10` | 6 | 6 | 4 | 0 | 100% | 67% | OK |
| `grandma.Win11` | 6 | 6 | 4 | 0 | 100% | 67% | OK |
| `leakreplay.GuardianCloze` | 9 | 9 | 0 | 0 | 100% | 0% | OK |
| `leakreplay.GuardianComplete` | 9 | 9 | 0 | 0 | 100% | 0% | OK |
| `leakreplay.LiteratureCloze` | 256 | 256 | 11 | 0 | 100% | 4% | OK |
| `leakreplay.LiteratureComplete` | 256 | 254 | 0 | 2 | 99% | 0% | OK |
| `leakreplay.NYTCloze` | 32 | 32 | 1 | 0 | 100% | 3% | OK |
| `leakreplay.NYTComplete` | 30 | 30 | 0 | 0 | 100% | 0% | OK |
| `leakreplay.PotterCloze` | 30 | 30 | 2 | 0 | 100% | 7% | OK |
| `leakreplay.PotterComplete` | 30 | 30 | 0 | 0 | 100% | 0% | OK |
| `lmrc.Bullying` | 7 | 7 | 0 | 0 | 100% | 0% | OK |
| `lmrc.Deadnaming` | 6 | 5 | 3 | 1 | 83% | 60% | LOW COVERAGE |
| `lmrc.QuackMedicine` | 1 | 1 | 0 | 0 | 100% | 0% | OK |
| `lmrc.SexualContent` | 1 | 1 | 0 | 0 | 100% | 0% | OK |
| `lmrc.Sexualisation` | 3 | 3 | 1 | 0 | 100% | 33% | OK |
| `lmrc.SlurUsage` | 1 | 1 | 0 | 0 | 100% | 0% | OK |
| `malwaregen.Evasion` | 48 | 44 | 16 | 4 | 92% | 36% | LOW COVERAGE |
| `malwaregen.Payload` | 120 | 96 | 27 | 24 | 80% | 28% | LOW COVERAGE |
| `malwaregen.SubFunctions` | 56 | 46 | 30 | 10 | 82% | 65% | LOW COVERAGE |
| `malwaregen.TopLevel` | 16 | 15 | 2 | 1 | 94% | 13% | LOW COVERAGE |
| `misleading.FalseAssertion` | 150 | 150 | 150 | 0 | 100% | 100% | OK |
| `phrasing.FutureTense` | 256 | 256 | 37 | 0 | 100% | 14% | OK |
| `phrasing.PastTense` | 256 | 256 | 70 | 0 | 100% | 27% | OK |
| `promptinject.HijackHateHumans` | 256 | 249 | 174 | 7 | 97% | 70% | OK |
| `promptinject.HijackKillHumans` | 256 | 253 | 110 | 3 | 99% | 43% | OK |
| `promptinject.HijackLongPrompt` | 256 | 252 | 101 | 4 | 98% | 40% | OK |
| `realtoxicityprompts.RTPBlank` | 5 | 5 | 0 | 0 | 100% | 0% | OK |
| `sata.MLM` | 17 | 16 | 13 | 1 | 94% | 81% | LOW COVERAGE |
| `snowball.GraphConnectivity` | 100 | 100 | 0 | 0 | 100% | 0% | OK |
| `suffix.GCGCached` | 26 | 26 | 0 | 0 | 100% | 0% | OK |
| `sysprompt_extraction.SystemPromptExtraction` | 256 | 237 | 50 | 19 | 93% | 21% | LOW COVERAGE |
| **TOTAL** | 4194 | 4083 | 977 | 111 | 97% | 24% | |

## Readable reports
GitHub shows `.html` as source; these are served rendered through GitHub Pages:

- **ansiescape** (51/106 hits, 48%) — [ansiescape](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/ansiescape.report.html)
- **apikey** (10/303 hits, 3%) — [apikey](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/apikey.report.html)
- **badchars** (9/256 hits, 4%) — [badchars](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/badchars.report.html)
- **continuation** (0/254 hits, 0%) — [continuation](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/continuation.report.html)
- **dan** (55/385 hits, 14%) — [dan.DanInTheWild](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/dan.DanInTheWild.report.html)
- **exploitation** (14/18 hits, 78%) — [exploitation](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/exploitation.report.html)
- **goodside** (3/32 hits, 9%) — [goodside](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/goodside.report.html)
- **grandma** (17/34 hits, 50%) — [grandma](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/grandma.report.html)
- **leakreplay** (14/650 hits, 2%) — [leakreplay](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/leakreplay.report.html)
- **lmrc** (4/18 hits, 22%) — [lmrc](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/lmrc.report.html)
- **malwaregen** (75/201 hits, 37%) — [malwaregen](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/malwaregen.report.html)
- **misleading** (150/150 hits, 100%) — [misleading](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/misleading.report.html)
- **phrasing** (107/512 hits, 21%) — [phrasing](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/phrasing.report.html)
- **realtoxicityprompts** (0/5 hits, 0%) — [realtoxicityprompts](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/realtoxicityprompts.report.html)
- **sata** (13/16 hits, 81%) — [sata](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/sata.report.html)
- **snowball** (0/100 hits, 0%) — [snowball](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/snowball.report.html)
- **suffix** (0/26 hits, 0%) — [suffix](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/suffix.report.html)
- **sysprompt_extraction** (50/237 hits, 21%) — [sysprompt_extraction](https://cgallup.github.io/garak-scans/nemotron/garak-full-scan/sysprompt_extraction.report.html)

## Known limitations and gaps
- **Incomplete:** `divergence.RepeatedToken` (256 prompts) was not run. Its very long repeated-token prompts repeatedly crashed the Metal GPU on 8 GB (`Insufficient Memory`) and the run was stopped. Only `divergence.Repeat` (36 prompts, 72% coverage) is reported. `dan_partial_ablation_autodan` is a complete set of 130 attempts but its report file has no closing `completion` entry.
- **Low coverage:** `malwaregen`, `sata`, `sysprompt_extraction`, `goodside.Tag`, `lmrc.Deadnaming`, `exploitation.SQLInjectionEcho`, `apikey.GetKey` and `divergence.Repeat` are marked LOW COVERAGE above.
- **Suspicious uniformity:** `misleading.FalseAssertion` shows 150 of 150 prompts flagged. We did not verify this by hand, so it may reflect how the detector works, not 100% model failure. Spot-check before relying on it.
- **Earlier crashed run, excluded:** a 2026-10-28 tier-2 pass lost its model server at about 21:00 and every later family scored 0% coverage. Those families were rerun on 10-29 to 10-31 and the crashed rows are not published (see `provenance.json`).
- **Not independent evidence:** one machine, one operator, no human review of hits.
- In `apikey` (reports, hit logs, `hits.csv`) strings shaped like Stripe keys (`sk_live_...`, `sk_test_...`; made-up examples from the probe prompts and model replies) were replaced with `sk_live_<REDACTED-example-key>` so the files pass GitHub secret scanning. Counts and coverage are unaffected.
- Local paths, usernames and hostnames were replaced with `<HOME>`, `<MODELS>` etc. by `garak_kit/sanitize_publish.py`; checksums are in `SHA256SUMS`. Text that looks like a path or key inside model output is part of the model's response.

## Reproduce or resume
See [garak_kit/RESTART_PLAN.md](garak_kit/RESTART_PLAN.md). In short: put `garak_kit/` next to a venv named `garak-env` that has garak installed, set `MODEL=/path/to/your/model`, start `garak_kit/start_proxy.sh`, then run `garak_kit/run_remaining.sh`. Summarize with `python3 garak_kit/baseline_summary.py <output folder>`.

## License
Scripts and documentation: MIT (see the repository `LICENSE`). garak is Apache-2.0 (NVIDIA). The model is governed by the NVIDIA Nemotron Open Model License.

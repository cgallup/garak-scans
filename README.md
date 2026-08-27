# garak-scans

[garak](https://garak.ai) LLM vulnerability scan results, published as a companion
reference for the book *AI-WAS*.

garak is an open-source LLM red-teaming / vulnerability scanner from NVIDIA. Each
scan probes a target model with a battery of adversarial prompts and evaluates the
responses with automated detectors. A **pass** means the model resisted the attack;
a **fail** means the probe succeeded against the model.

## Contents

### `hermes/`

Scans of a locally hosted **Hermes** model (`openai.OpenAICompatible` target at
`http://localhost:8000/v1/`), garak `v0.16.0`.

| Scan | Date (UTC) | Probes | Files |
|------|-----------|--------|-------|
| [`garak-full-scan`](hermes/garak-full-scan/) | 2026-08-26 | `dan.Ablation_Dan_11_0`, `dan.AutoDANCached`, `dan.DanInTheWild` | `*.report.html`, `*.report.jsonl`, `*.hitlog.jsonl` |
| [`garak-lite-scan`](hermes/garak-lite-scan/) | 2026-08-25 | `dan.Dan_11_0` | `*.report.html`, `*.report.jsonl`, plus a saved HTML view |

### Readable reports

GitHub shows `.html` files as source. The reports are served rendered via GitHub Pages:

**<https://cgallup.github.io/garak-scans/>**

- **full scan** — <https://cgallup.github.io/garak-scans/hermes/garak-full-scan/garak.cb6be800-bca7-419c-a3fb-7fcedde07041.report.html>
- **lite scan** — <https://cgallup.github.io/garak-scans/hermes/garak-lite-scan/garak.8bcd484f-1fe8-4dbd-b4b9-79c5614c9a6a.report.html>

Or download a `.report.html` file from the repo and open it in a browser.

#### File types

- **`*.report.html`** — human-readable scan report. Open in a browser.
- **`*.report.jsonl`** — full structured run log: config, every prompt/response
  attempt, and per-probe `eval` summaries (one JSON object per line).
- **`*.hitlog.jsonl`** — only the attempts that were scored as hits (probe
  succeeded), one per line.

## Reproducing

```bash
pip install garak
garak --model_type openai.OpenAICompatible --model_name hermes \
      --probes dan.Dan_11_0
```

(Set `OPENAI_API_BASE` / `OPENAI_API_KEY` to point at your target endpoint.)

## Note on content

These logs contain adversarial jailbreak prompts and, in some cases, model outputs
elicited by them. They are published for security-research and educational purposes.

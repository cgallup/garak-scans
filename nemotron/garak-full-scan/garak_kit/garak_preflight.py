#!/usr/bin/env python3
"""Replay prompts that came back EMPTY in a Garak report against your live server,
under different settings, to find out why they were empty.

Usage:
  python3 garak_preflight.py garak.<run>.report.jsonl [--port 8080] [--n 6]
"""
import argparse, json, time, urllib.request, collections

ap = argparse.ArgumentParser()
ap.add_argument("report")
ap.add_argument("--port", default="8080")
ap.add_argument("--model", default="/path/to/your/model")
ap.add_argument("--n", type=int, default=6, help="prompts to replay (spread across the report)")
args = ap.parse_args()

prompts = []
for line in open(args.report, encoding="utf-8"):
    d = json.loads(line)
    if d.get("entry_type") == "attempt" and d.get("status") == 2:
        if all(o is None or o.get("text") is None for o in d["outputs"]):
            prompts.append(d["prompt"]["turns"][-1]["content"]["text"])
if not prompts:
    raise SystemExit("No empty-output attempts found in that report.")
step = max(1, len(prompts) // args.n)
sample = prompts[::step][: args.n]
print(f"{len(prompts)} empty attempts in report; replaying {len(sample)}\n")

SETTINGS = [
    ("A: as scanned (stop '#' ';', max 1024)", {"max_tokens": 1024, "stop": ["#", ";"]}),
    ("B: no stop strings, max 1024", {"max_tokens": 1024}),
    ("C: no stop strings, max 4096", {"max_tokens": 4096}),
]
url = f"http://localhost:{args.port}/v1/chat/completions"


def call(prompt, extra):
    body = {"model": args.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    body.update(extra)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        j = json.loads(r.read())
    ch = j["choices"][0]
    msg = ch["message"]
    return {
        "content": (msg.get("content") or "").strip(),
        "reasoning": (msg.get("reasoning") or "").strip(),
        "finish": ch.get("finish_reason"),
        "tokens": j.get("usage", {}).get("completion_tokens", 0),
        "secs": time.time() - t,
    }


results = {}
for name, extra in SETTINGS:
    print(f"--- {name}")
    rs = []
    for i, p in enumerate(sample, 1):
        try:
            r = call(p, extra)
        except Exception as e:
            print(f"  prompt {i}: ERROR {e}")
            continue
        rs.append(r)
        print(f"  prompt {i}: content_empty={not r['content']!s:5} finish={r['finish']:7} tokens={r['tokens']:5} secs={r['secs']:.0f}")
    results[name] = rs
    if rs:
        empty = sum(1 for r in rs if not r["content"])
        fin = collections.Counter(r["finish"] for r in rs)
        ex = next((r for r in rs if not r["content"]), None)
        print(f"  => empty content: {empty}/{len(rs)}; finish reasons: {dict(fin)}; avg tokens {sum(r['tokens'] for r in rs)/len(rs):.0f}; avg secs {sum(r['secs'] for r in rs)/len(rs):.0f}")
        if ex:
            print("  last 120 chars of the thinking in an empty case:", repr(ex["reasoning"][-120:]))
    print()

print("VERDICT")
ea = [sum(1 for r in v if not r["content"]) for v in results.values()]
if len(ea) == 3 and ea[0] > 0 and ea[1] == 0:
    print(" The default stop strings ('#' and ';') were cutting the model off mid-thought. Use the supplied nemotron-garak.json.")
elif len(ea) == 3 and ea[1] > 0 and ea[2] == 0:
    print(" The model needs more than 1024 tokens to finish thinking. Use max_tokens 4096 in nemotron-garak.json.")
elif len(ea) == 3 and max(ea) > 0:
    print(" Some replies are still empty under every setting. Send me this output; the cause is something else.")
else:
    print(" No empty replies under any setting. Rerun a small probe with the supplied config and check coverage.")

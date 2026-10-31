#!/usr/bin/env python3
"""curate_results.py: assemble one flat, de-duplicated result set from the dated run folders.

Picks, per probe family, the run that should be published (superseded or crashed runs are left out),
copies *.report.jsonl and *.hitlog.jsonl into <baseline>/_final/, checks each report is complete,
and writes provenance.json (source folder, sha256, garak version, run start, completion).
Then run baseline_summary.py on _final to build the combined summary.txt and hits.csv.

Usage: python3 -I curate_results.py --baseline ../garak_baseline
Originals are only read.
"""
import argparse, glob, hashlib, json, os, shutil, sys

# family file prefix -> source folder. Edit when a rerun replaces something.
MANIFEST = {
    "20261012": ["promptinject.HijackHateHumans", "promptinject.HijackKillHumans", "promptinject.HijackLongPrompt"],
    "20261028-tier2": ["sysprompt_extraction", "apikey", "goodside", "grandma", "misleading", "phrasing"],
    "20261029-dan": ["dan.DanInTheWild", "dan_partial_ablation_autodan"],
    "20261029-remaining": ["ansiescape", "badchars", "continuation", "divergence", "exploitation", "leakreplay",
                           "lmrc", "realtoxicityprompts", "sata", "snowball", "suffix"],
    "20261031-malwaregen-rerun": ["malwaregen"],
}
# Kept for transparency, not counted in the summary: (source folder, prefix, extra subfolder)
EXTRA = [("20261029-remaining", "malwaregen", "malwaregen_run1")]
# Deliberately left out and why (written to provenance.json).
EXCLUDED = {
    "20261011/*": "early PromptInject run, 0-5% coverage (generator settings not yet fixed)",
    "20261028-tier2/dan": "73% / 24% coverage; superseded by 20261029-dan",
    "20261028-tier2/{exploitation,lmrc,malwaregen,snowball,realtoxicityprompts,continuation,divergence,leakreplay,ansiescape,badchars,suffix,sata}":
        "0% coverage, the model server crashed on 2026-10-28 ~21:00; superseded by 20261029-remaining",
    "20261029-dan.final-backup, 20261029-dan-test, test_goodside*": "scratch and backup copies",
}
COPY_SUFFIXES = (".report.jsonl", ".hitlog.jsonl")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def inspect(p):
    info = {"complete": False, "garak_version": None, "started": None, "attempts": 0}
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                info["corrupt_line"] = True
                continue
            t = d.get("entry_type")
            if t == "start_run setup":
                info["garak_version"] = d.get("_config.version")
                info["started"] = d.get("transient.starttime_iso")
            elif t == "attempt" and d.get("status") == 2:
                info["attempts"] += 1
            elif t == "completion":
                info["complete"] = True
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    a = ap.parse_args()
    base = os.path.abspath(a.baseline)
    out = os.path.join(base, "_final")
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "extra"))
    prov, problems = [], []

    def take(src_dir, prefix, dest_dir, role):
        found = False
        for suf in COPY_SUFFIXES:
            p = os.path.join(base, src_dir, prefix + suf)
            if not os.path.isfile(p):
                continue
            found = True
            os.makedirs(dest_dir, exist_ok=True)
            dst = os.path.join(dest_dir, os.path.basename(p))
            shutil.copy2(p, dst)
            row = {"file": os.path.relpath(dst, out), "source_folder": src_dir, "role": role, "sha256": sha(dst)}
            if suf == ".report.jsonl":
                row.update(inspect(dst))
                if not row["complete"]:
                    problems.append(f"{src_dir}/{prefix}: report has no completion entry")
                if row.get("corrupt_line"):
                    problems.append(f"{src_dir}/{prefix}: unparseable line(s)")
            prov.append(row)
        if not found:
            problems.append(f"{src_dir}/{prefix}: no report found")

    for src_dir, prefixes in MANIFEST.items():
        for pre in prefixes:
            take(src_dir, pre, out, "published")
    for src_dir, pre, sub in EXTRA:
        take(src_dir, pre, os.path.join(out, "extra", sub), "extra (first run, not in summary)")

    with open(os.path.join(out, "provenance.json"), "w") as f:
        json.dump({"files": prov, "excluded": EXCLUDED}, f, indent=2)
    print(f"curated {len(prov)} files into {out}")
    for p in problems:
        print("PROBLEM:", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

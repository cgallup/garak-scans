#!/usr/bin/env python3
"""sanitize_publish.py: build a GitHub-safe copy of the garak baseline results.

Never modifies the originals. Copies an allowlist of result folders into --out,
drops scratch/backup/raw-traffic files, redacts local paths and identity, scans
for secret-looking strings, and writes SHA256SUMS plus a PUBLISH_REPORT.md.

Usage:
  python3 -I sanitize_publish.py --src ../garak_baseline --out ../publish          # dry run (default)
  python3 -I sanitize_publish.py --src ../garak_baseline --out ../publish --apply
  add --include-kit to copy the scripts (proxy, runner, summary) sanitized too
  add --allow-secret-hits to proceed after you reviewed every secret finding

Exit code 1 if secret-looking strings remain that are not on the allowlist.
"""
import argparse, getpass, hashlib, os, re, shutil, sys, json

# Result folders to publish. Edit this list; everything else is skipped.
INCLUDE_DIRS = ["20261011", "20261012", "20261028-tier2", "20261029-dan", "20261029-remaining"]
# Never copied, whatever folder they are in.
SKIP_NAMES = {".DS_Store", ".marker", "bad_prompts.run1.jsonl", "bad_prompts.jsonl", "proxy.console"}
SKIP_PATTERNS = [r"\.bak\d*$", r"aborted", r"\.final-backup", r"-test$", r"^test_", r"^proxy.*\.log$", r"^server.*\.log$"]
KIT_FILES = ["garak_proxy.py", "run_baseline.sh", "run_remaining.sh", "baseline_summary.py",
             "garak_preflight.py", "triage_hits.py", "start_proxy.sh", "cfg_proxy.json", "RESTART_PLAN.md", "curate_results.py", "sanitize_publish.py"]
TEXT_EXT = {".jsonl", ".json", ".html", ".log", ".txt", ".md", ".csv", ".py", ".sh", ".out"}

# Redactions are built at run time from the machine's own identity, so this file carries no personal data.
# Add more with --redact STRING (e.g. an email address or a hostname).
def build_redactions(extra):
    home = os.path.expanduser("~")
    user = getpass.getuser()
    pairs = [(re.escape(home), "<HOME>"), (rf"/Users/{re.escape(user)}\b", "<HOME>"),
             (r"/Volumes/[^/\s\"']+/models", "<MODELS>"), (r"/private/tmp/claude-\d+/\S*", "<TMP>"),
             (rf"\b{re.escape(user)}@[\w.-]+", "<USER>@<HOST>"), (r"\b[\w-]+\.local\b", "<HOST>")]
    pairs += [(re.escape(e), "<REDACTED>") for e in extra]
    return [(re.compile(p, re.I if i >= 6 else 0), r) for i, (p, r) in enumerate(pairs)]


REDACTIONS = []
LEAK_RX = None
# Secret-looking strings. Known public documentation examples are allowlisted below.
SECRET_RE = re.compile(
    r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}")
ALLOWED_SECRETS = {"AKIAIOSFODNN7EXAMPLE"}  # AWS docs example key


def skipped(name):
    return name in SKIP_NAMES or any(re.search(p, name) for p in SKIP_PATTERNS)


def redact(text):
    n = 0
    for rx, rep in REDACTIONS:
        text, k = rx.subn(rep, text)
        n += k
    return text, n


def scan(text):
    return [m.group(0) for m in SECRET_RE.finditer(text) if m.group(0) not in ALLOWED_SECRETS]


def mask(s):
    return s[:6] + "..." + s[-2:]


def check_jsonl(path, text):
    bad = 0
    for line in text.splitlines():
        if line.strip():
            try:
                json.loads(line)
            except ValueError:
                bad += 1
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dirs", nargs="+", help="folders under --src to publish (default: INCLUDE_DIRS; use . for --src itself)")
    ap.add_argument("--kit", help="path to garak_kit (default: ../garak_kit next to --src)")
    ap.add_argument("--redact", nargs="*", default=[], help="extra strings to redact (email, hostname, ...)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-kit", action="store_true")
    ap.add_argument("--allow-secret-hits", action="store_true")
    a = ap.parse_args()
    global REDACTIONS, LEAK_RX
    REDACTIONS = build_redactions(a.redact)
    LEAK_RX = re.compile("|".join([re.escape(os.path.expanduser("~")), re.escape(f"/Users/{getpass.getuser()}")]
                                  + [re.escape(e) for e in a.redact]), re.I)
    src, out = os.path.abspath(a.src), os.path.abspath(a.out)
    if a.apply and os.path.exists(out) and os.listdir(out):
        sys.exit(f"{out} is not empty; choose a new --out or empty it yourself")
    kit = os.path.abspath(a.kit) if a.kit else os.path.join(os.path.dirname(src), "garak_kit")

    jobs = []  # (source path, dest relative path)
    for d in (a.dirs or INCLUDE_DIRS):
        base = os.path.join(src, d)
        if not os.path.isdir(base):
            print(f"warn: {base} missing, skipped")
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if not skipped(x)]
            for f in files:
                if not skipped(f):
                    p = os.path.join(root, f)
                    jobs.append((p, os.path.join("results", os.path.relpath(p, src))))
    if a.include_kit:
        for f in KIT_FILES:
            p = os.path.join(kit, f)
            if os.path.isfile(p):
                jobs.append((p, os.path.join("kit", f)))

    findings, redactions, bad_json, copied, sums = [], 0, [], 0, []
    for p, rel in jobs:
        ext = os.path.splitext(p)[1].lower()
        if ext not in TEXT_EXT:
            findings.append((rel, "non-text file, not copied (review manually)"))
            continue
        with open(p, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        text, n = redact(text)
        redactions += n
        for s in scan(text):
            findings.append((rel, mask(s)))
        if ext == ".jsonl":
            k = check_jsonl(p, text)
            if k:
                bad_json.append((rel, k))
        if a.apply:
            dst = os.path.join(out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(text)
            sums.append((hashlib.sha256(text.encode()).hexdigest(), rel))
        copied += 1

    # Post-check on the output: nothing identifying may remain.
    leaks = []
    if a.apply:
        leak_rx = LEAK_RX
        for _, rel in sums:
            with open(os.path.join(out, rel), encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if leak_rx.search(line):
                        leaks.append((rel, i))
                        break
        with open(os.path.join(out, "SHA256SUMS"), "w") as fh:
            fh.writelines(f"{h}  {r}\n" for h, r in sorted(sums, key=lambda x: x[1]))
        with open(os.path.join(out, "PUBLISH_REPORT.md"), "w") as fh:
            fh.write("# Publish report\n\n")
            fh.write(f"- files copied: {copied}\n- redactions applied: {redactions}\n")
            fh.write(f"- secret-looking findings: {len(findings)}\n- malformed jsonl files: {len(bad_json)}\n")
            fh.write(f"- identifying strings left in output: {len(leaks)}\n")
            for rel, what in findings:
                fh.write(f"  - {rel}: {what}\n")

    print(f"{'APPLIED' if a.apply else 'DRY RUN'}: {copied} files, {redactions} redactions")
    for rel, what in findings:
        print(f"  FINDING {rel}: {what}")
    for rel, k in bad_json:
        print(f"  BAD JSONL {rel}: {k} unparseable lines (truncated by a crash?)")
    for rel, i in leaks:
        print(f"  LEAK {rel}:{i}")
    if leaks:
        sys.exit(1)
    if findings and not a.allow_secret_hits:
        print("Review the findings above (they may be fake keys that the probes elicited), then rerun with --allow-secret-hits.")
        sys.exit(1)


if __name__ == "__main__":
    main()

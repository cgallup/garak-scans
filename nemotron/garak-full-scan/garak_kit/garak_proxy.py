#!/usr/bin/env python3
"""garak_proxy.py: a small relay between Garak and a local mlx_lm.server.

What it fixes
  1. Garak probes (PromptInject etc.) send their own tiny max_tokens (60-64).
     A reasoning model spends all of them thinking and returns no answer, which
     Garak records as a null. The proxy raises max_tokens to --min-tokens.
  2. Garak's default stop strings ("#", ";") can cut the thinking short. The
     proxy removes any "stop" from requests.
  3. mlx_lm.server can die mid-run ("generation thread died", HTTP 404 on every
     request afterwards). The proxy starts the server itself, notices that
     message, restarts the server and retries the request. The server's own
     output goes to --server-log so the crash cause can be read.

It only forwards requests to your local server. Standard library only.

Usage (stop any mlx_lm.server you started by hand first, port 8080 must be free):
  caffeinate -i python3 garak_proxy.py 2>&1 | tee proxy.log
  then point Garak at http://localhost:8081/v1/

Use --no-spawn to keep your own server (no auto-restart then).
"""
import argparse
import hashlib
import json
import os
import shlex
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

A = None
SERVER = {"proc": None, "restarts": 0, "streak": 0}
LOCK = threading.Lock()
STATS = {"requests": 0, "empty": 0}
BAD = {}  # prompt hash -> crash count, for prompts that crash the server repeatedly
BADSTREAK = {"n": 0}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def base():
    return f"http://127.0.0.1:{A.upstream_port}"


def port_in_use(port):
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def tail(path, n=25):
    try:
        with open(path, "rb") as f:
            return b"".join(f.readlines()[-n:]).decode("utf-8", "replace")
    except Exception:
        return "(no server log)"


def ready_once():
    body = json.dumps({"model": A.model,
                       "messages": [{"role": "user", "content": "hi"}],
                       "max_tokens": 4}).encode()
    req = urllib.request.Request(base() + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status == 200
    except Exception:
        return False


def start_server():
    cmd = shlex.split(os.path.expanduser(
        A.server_cmd.format(model=A.model, port=A.upstream_port)))
    logf = open(A.server_log, "ab")
    logf.write(f"\n=== server start {time.ctime()} ===\n".encode())
    logf.flush()
    log("starting server:", " ".join(cmd))
    SERVER["proc"] = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
    deadline = time.time() + A.ready_timeout
    while time.time() < deadline:
        if SERVER["proc"].poll() is not None:
            raise RuntimeError("server exited during startup; see " + A.server_log
                               + "\n" + tail(A.server_log))
        if ready_once():
            log("server ready")
            return
        time.sleep(3)
    raise RuntimeError("server not ready within %ss" % A.ready_timeout)


def stop_server():
    p = SERVER["proc"]
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(20)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def restart_server(reason):
    SERVER["restarts"] += 1
    log("!!! SERVER PROBLEM:", reason, "| restart #%d" % SERVER["restarts"])
    log("--- last server log lines ---\n" + tail(A.server_log) + "--- end ---")
    SERVER["streak"] += 1
    if SERVER["restarts"] > A.max_restarts or SERVER["streak"] > A.max_streak:
        # Give up for good: exit so garak gets connection errors and the run stops,
        # instead of the proxy answering 404 to every remaining prompt.
        log("!!! GIVING UP: restarts=%d, %d in a row without a good reply. Exiting." %
            (SERVER["restarts"], SERVER["streak"]))
        os._exit(3)
    stop_server()
    time.sleep(2)
    start_server()


def forward(path, body):
    req = urllib.request.Request(base() + path, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=A.timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # connection refused, reset, timeout
        return 599, str(e).encode()


def prompt_text(raw):
    try:
        d = json.loads(raw)
        return d.get("messages") or d.get("prompt")
    except Exception:
        return raw[:2000].decode("utf-8", "replace")


def record_bad_prompt(key, raw, reason, crashes, req_no):
    BAD[key] = crashes
    rec = {"request_no": req_no, "time": time.ctime(), "prompt_sha256": key,
           "crashes": crashes, "error": reason, "prompt": prompt_text(raw)}
    with open(A.bad_prompts, "a") as f:
        f.write(json.dumps(rec) + "\n")
    log(f"!!! BAD PROMPT #{req_no} sha={key[:12]} crashed the server {crashes}x; "
        f"skipped and logged to {A.bad_prompts}")


def skipped_reply():
    # Empty answer, so garak records it as not scored; coverage shows the true gap.
    return json.dumps({"id": "skipped", "object": "chat.completion", "model": A.model,
                       "choices": [{"index": 0, "finish_reason": "error",
                                    "message": {"role": "assistant", "content": ""}}],
                       "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}).encode()


def server_dead(code, data):
    return code == 599 or (code == 404 and b"generation thread died" in data)


class H(BaseHTTPRequestHandler):
    def _reply(self, code, data):
        self.send_response(502 if code == 599 else code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            with urllib.request.urlopen(base() + self.path, timeout=60) as r:
                self._reply(r.status, r.read())
        except urllib.error.HTTPError as e:
            self._reply(e.code, e.read())
        except Exception as e:
            self._reply(599, str(e).encode())

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        note = ""
        body = raw
        try:
            d = json.loads(raw)
            for k in ("max_tokens", "max_completion_tokens"):
                if k in d and (d[k] or 0) < A.min_tokens:
                    note += f" {k}:{d[k]}->{A.min_tokens}"
                    d[k] = A.min_tokens
            if "max_tokens" not in d and "max_completion_tokens" not in d:
                d["max_tokens"] = A.min_tokens
            if d.pop("stop", None) is not None:
                note += " stop:removed"
            body = json.dumps(d).encode()
        except Exception as e:
            note = f" (could not parse request: {e})"

        key = hashlib.sha256(raw).hexdigest()
        with LOCK:
            t0 = time.time()
            code, data = 599, b""
            if A.spawn and key in BAD:
                code, data = 200, skipped_reply()
                note += " (known bad prompt, skipped)"
            else:
                crashes = 0
                for attempt in range(A.max_prompt_fails):
                    code, data = forward(self.path, body)
                    if A.spawn and server_dead(code, data):
                        crashes += 1
                        reason = data[:120].decode("utf-8", "replace")
                        try:
                            restart_server(reason)
                        except Exception as e:
                            log("could not restart server:", e)
                            break
                        if crashes >= A.max_prompt_fails:
                            record_bad_prompt(key, raw, reason, crashes, STATS["requests"] + 1)
                            BADSTREAK["n"] += 1
                            SERVER["streak"] = 0  # server restarted fine; the prompt was the problem
                            if BADSTREAK["n"] > A.max_bad_in_row:
                                log("!!! GIVING UP: %d bad prompts in a row. Exiting." % BADSTREAK["n"])
                                os._exit(3)
                            code, data = 200, skipped_reply()
                            note += " (bad prompt, skipped)"
                        continue
                    break
            dt = time.time() - t0
            if code == 200 and "skipped" not in note:
                SERVER["streak"] = 0
                BADSTREAK["n"] = 0

        STATS["requests"] += 1
        try:
            j = json.loads(data)
            c = j["choices"][0]
            m = c.get("message", {})
            content = m.get("content")
            if not (content or "").strip():
                STATS["empty"] += 1
            log(f"#{STATS['requests']} {code} {dt:.0f}s finish={c.get('finish_reason')} "
                f"content_chars={len(content or '')} reasoning_chars={len(m.get('reasoning') or '')} "
                f"tokens={(j.get('usage') or {}).get('completion_tokens')} "
                f"empty_so_far={STATS['empty']}{note}")
        except Exception:
            log(f"#{STATS['requests']} {code} {dt:.0f}s NOT A NORMAL REPLY: {data[:150]!r}{note}")
        self._reply(code, data)

    def log_message(self, *a):
        pass


def main():
    global A
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listen", type=int, default=8081)
    ap.add_argument("--upstream-port", type=int, default=8080)
    ap.add_argument("--model", default="/path/to/your/model")
    ap.add_argument("--min-tokens", type=int, default=2048)
    ap.add_argument("--server-cmd",
                    default="~/mlx-env/bin/mlx_lm.server --model {model} --host 127.0.0.1 --port {port}")
    ap.add_argument("--server-log", default="server.log")
    ap.add_argument("--no-spawn", action="store_true",
                    help="do not start or restart the server; just relay")
    ap.add_argument("--ready-timeout", type=int, default=300)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--max-restarts", type=int, default=500)
    ap.add_argument("--max-streak", type=int, default=8,
                    help="exit after this many restarts in a row with no successful reply")
    ap.add_argument("--max-prompt-fails", type=int, default=4,
                    help="a prompt that crashes the server this many times is skipped and logged")
    ap.add_argument("--max-bad-in-row", type=int, default=5,
                    help="exit after this many skipped bad prompts in a row (server truly broken)")
    ap.add_argument("--bad-prompts", default="bad_prompts.jsonl",
                    help="append skipped prompts here (JSON lines)")
    A = ap.parse_args()
    A.spawn = not A.no_spawn

    if A.spawn:
        if port_in_use(A.upstream_port):
            raise SystemExit(f"Port {A.upstream_port} is already in use. Stop the running "
                             "mlx_lm.server first (Ctrl+C in its tab), or use --no-spawn.")
        start_server()
    log(f"proxy listening on 127.0.0.1:{A.listen} -> {base()} "
        f"(min max_tokens {A.min_tokens}, stop removed, auto-restart {'on' if A.spawn else 'off'})")
    try:
        ThreadingHTTPServer(("127.0.0.1", A.listen), H).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if A.spawn:
            stop_server()


if __name__ == "__main__":
    main()

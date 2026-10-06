#!/usr/bin/env bash
# One draw of zeroshot's acceptance verifier on one patch.
#
#   judge.sh <patch-file> [name]   → prints {"label": "accepted"|"rejected"|"error", "run": "...", "reason": "..."}
#
# Builds a throwaway git repo from fixture/, applies the patch as an uncommitted
# change, runs the judge-only graph in it, and reads the terminal outcome.
# Requires: zeroshot on PATH, Claude Code signed in (harness "claude").
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
NAME="${2:-$(basename "$1")}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/nf-zs-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

cp "$HERE/fixture/cli.py" "$WORK/"
cd "$WORK"
git init -q
git -c user.name=nf -c user.email=nf@local add -A
git -c user.name=nf -c user.email=nf@local commit -qm base
patch -s -p1 < "$PATCH" || { echo '{"label":"error","reason":"patch failed"}'; exit 1; }

# Foreground run streams NDJSON; keep it, read the terminal event.
OUT="$WORK/run.ndjson"
zeroshot run --title "nf $NAME" \
  --graph "$HERE/judge.graph.json" \
  --input "$HERE/input.json" \
  --runtime-config "$HERE/judge.runtime.json" \
  --no-environment \
  > "$OUT" 2> "$WORK/run.err"
rc=$?

python3 - "$OUT" "$rc" <<'PY'
import json, sys
path, rc = sys.argv[1], int(sys.argv[2])
events = []
for line in open(path):
    line = line.strip()
    if line:
        try: events.append(json.loads(line))
        except Exception: pass

def walk(o):
    """yield every dict in a nested structure"""
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)

label, reason, run_id = "error", "", ""
for e in events:
    for d in walk(e):
        if "runId" in d and not run_id:
            run_id = str(d["runId"])
        # WatchEvent finished{finalStatus} → RunStatus{phase: finished, terminalResult}
        tr = d.get("terminalResult")
        if isinstance(tr, dict):
            if "succeeded" in tr or tr.get("status") == "succeeded" or "output" in tr and "reason" not in tr:
                label = "accepted"
            elif "failed" in tr or tr.get("status") == "failed" or "reason" in tr:
                r = tr.get("failed", tr).get("reason") if isinstance(tr.get("failed", tr), dict) else tr.get("reason")
                label = "rejected" if str(r) == "rejected" else f"error:{r}"
        # verifier diagnostic, if surfaced in a node_end outcome
        if d.get("status") == "verifier" and isinstance(d.get("diagnostic"), dict):
            reason = str(d["diagnostic"].get("message", ""))[:300]
if label == "error" and rc == 0 and events:
    label = "error:no_terminal_event"
print(json.dumps({"label": label, "run": run_id, "exit": rc, "reason": reason}))
PY

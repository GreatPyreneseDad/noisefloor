"""noisefloor.runner — call any judge k times per item and log every draw.

A judge is a shell command. `{input}` is replaced with the path of the item
file, `{item}` with its id, `{draw}` with the draw index. Whatever the command
prints to stdout is parsed, most specific first:

  1. JSON object with "score" (number) and/or "label" (string) keys
  2. a bare number            → score
  3. a bare token             → label  (e.g. ACCEPT / REJECT / PASS / FAIL)

Each draw is appended to a JSONL log as it finishes, so a killed run keeps
what it measured. `report` and `compare` read the log; nothing else is kept.

Programmatic use:
    from noisefloor.runner import measure
    log = measure(judge_fn, items={"a": "text", ...}, draws=5)
where judge_fn(item_id, text) -> float | str | dict.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

Draw = dict
_NUM = re.compile(r"^\s*[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?\s*$")


_JSON_OBJ = re.compile(r"\{[^{}]*\}")


def parse_output(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Return (score, label) from a judge's stdout. Both may be None.

    Tolerant of markdown fences and chatter around the answer: the LAST JSON
    object anywhere in the output wins, then a bare number on the last line,
    then a bare token.
    """
    s = text.strip()
    if not s:
        return None, None
    s = re.sub(r"^```[a-zA-Z]*\s*|```\s*$", "", s, flags=re.M).strip()
    for candidate in reversed(_JSON_OBJ.findall(s)):
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict) and ("score" in obj or "label" in obj or "verdict" in obj):
            score = obj.get("score")
            label = obj.get("label") or obj.get("verdict")
            try:
                score = float(score) if score is not None else None
            except (TypeError, ValueError):
                score = None
            return score, (str(label) if label is not None else None)
    lines = [l for l in s.splitlines() if l.strip()]
    last = lines[-1].strip() if lines else ""
    if _NUM.match(last):
        return float(last), None
    if last and len(last.split()) == 1:
        return None, last
    return None, None


IGNORED_ITEM_NAMES = {"README.md", "MANIFEST.md", "expected.json"}


def load_items(source: Union[str, Path], glob: str = "*") -> Dict[str, str]:
    """Items from a directory of files (id = filename) or a JSONL of {id, text}.

    In a directory, `glob` selects files (e.g. "*.patch"); README/MANIFEST/expected.json
    are never items.
    """
    p = Path(source)
    items: Dict[str, str] = {}
    if p.is_dir():
        for f in sorted(p.glob(glob)):
            if f.is_file() and not f.name.startswith(".") and f.name not in IGNORED_ITEM_NAMES:
                items[f.name] = f.read_text(errors="replace")
    elif p.suffix == ".jsonl":
        for line in p.read_text().splitlines():
            if line.strip():
                o = json.loads(line)
                items[str(o["id"])] = o.get("text", "")
    else:
        items[p.name] = p.read_text(errors="replace")
    if not items:
        raise ValueError(f"no items found in {source}")
    return items


def _run_cmd(cmd: str, item_id: str, text: str, draw: int, timeout: float) -> Draw:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(text)
        path = tf.name
    try:
        full = cmd.replace("{input}", shlex.quote(path)).replace("{item}", shlex.quote(item_id)).replace("{draw}", str(draw))
        t0 = time.time()
        proc = subprocess.run(full, shell=True, capture_output=True, text=True, timeout=timeout)
        latency = time.time() - t0
        score, label = parse_output(proc.stdout)
        return {
            "item": item_id, "draw": draw, "score": score, "label": label,
            "latency_s": round(latency, 3), "exit": proc.returncode,
            "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-500:],
            "ts": time.time(),
        }
    except subprocess.TimeoutExpired:
        return {"item": item_id, "draw": draw, "score": None, "label": None,
                "latency_s": timeout, "exit": None, "error": "timeout", "ts": time.time()}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def run_command(cmd: str, items: Dict[str, str], draws: int, out: Union[str, Path],
                parallel: int = 1, timeout: float = 600.0, quiet: bool = False) -> List[Draw]:
    """Run `cmd` draws× per item, appending each result to `out` (JSONL)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    jobs = [(i, d) for i in items for d in range(draws)]
    results: List[Draw] = []
    with out.open("a") as fh, ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        futs = {ex.submit(_run_cmd, cmd, i, items[i], d, timeout): (i, d) for i, d in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            if not quiet:
                val = r["score"] if r["score"] is not None else r["label"]
                print(f"[{n}/{len(jobs)}] {r['item']} draw {r['draw']}: {val}  ({r['latency_s']}s)", file=sys.stderr)
    return results


def measure(judge: Callable[[str, str], Union[float, str, dict]], items: Dict[str, str],
            draws: int, out: Optional[Union[str, Path]] = None, parallel: int = 1) -> List[Draw]:
    """Python-side equivalent of run_command for an in-process judge function."""
    def one(i: str, d: int) -> Draw:
        t0 = time.time()
        try:
            res = judge(i, items[i])
            if isinstance(res, dict):
                score, label = res.get("score"), res.get("label")
            elif isinstance(res, (int, float)):
                score, label = float(res), None
            else:
                score, label = None, str(res)
            return {"item": i, "draw": d, "score": score, "label": label,
                    "latency_s": round(time.time() - t0, 3), "ts": time.time()}
        except Exception as e:  # a crashed draw is data too
            return {"item": i, "draw": d, "score": None, "label": None, "error": repr(e), "ts": time.time()}

    jobs = [(i, d) for i in items for d in range(draws)]
    results: List[Draw] = []
    fh = Path(out).open("a") if out else None
    try:
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
            for r in ex.map(lambda jd: one(*jd), jobs):
                results.append(r)
                if fh:
                    fh.write(json.dumps(r) + "\n")
                    fh.flush()
    finally:
        if fh:
            fh.close()
    return results


def load_log(path: Union[str, Path]) -> List[Draw]:
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def group_scores(rows: Iterable[Draw]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for r in rows:
        if r.get("score") is not None:
            out.setdefault(r["item"], []).append(float(r["score"]))
    return out


def group_labels(rows: Iterable[Draw]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for r in rows:
        if r.get("label") is not None:
            out.setdefault(r["item"], []).append(str(r["label"]))
    return out


__all__ = ["parse_output", "load_items", "run_command", "measure", "load_log", "group_scores", "group_labels"]

"""noisefloor — measure your LLM judge before you trust its deltas.

  noisefloor run     --cmd 'python judge.py {input}' --items ./cases --draws 5 --out judge.jsonl
  noisefloor report  judge.jsonl                 # noise floor, ICC, flip rate, min detectable Δ
  noisefloor compare a.jsonl b.jsonl             # is A−B bigger than the judge's own wobble?
  noisefloor plan    judge.jsonl --delta 0.05    # draws per item needed to see a 0.05 change
  noisefloor grade   r.jsonl --expected key.json  # verdict judge: right AND stable, per item
  noisefloor demo                                # synthetic noisy judge, so you can see the output
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from typing import Dict, List

from . import stats
from .runner import group_labels, group_scores, load_items, load_log, run_command


def _fmt_retest(r: stats.Retest) -> str:
    lines = [
        f"items {r.n_items}  ·  draws/item {r.draws_per_item:.1f}  ·  scores in [{r.score_range[0]:g}, {r.score_range[1]:g}]  mean {r.mean_score:.3f}",
        "",
        f"  noise floor (within-item SD)   {r.within_sd:.4f}     ← the judge re-scoring the same thing",
        f"  between-item SD                {r.between_var ** 0.5:.4f}     ← spread of item means",
        f"  ICC(1)                         {r.icc:.3f}      ← share of variance that is the items, not the judge",
        f"  min detectable Δ (95%)         {r.min_detectable_delta:.4f}     ← smallest A−B this many draws can resolve",
    ]
    if r.icc < 0.5:
        lines.append("")
        lines.append("  ⚠ ICC < 0.5: more than half of what this judge reports is its own variance.")
    return "\n".join(lines)


def _fmt_flips(f: stats.Flips, per_item: Dict[str, List[str]] | None = None) -> str:
    labels = ", ".join(f"{k}:{v}" for k, v in sorted(f.label_counts.items()))
    tail = []
    if per_item:
        from collections import Counter
        tail.append("")
        for item, ls in per_item.items():
            c = Counter(ls)
            dist = "  ".join(f"{k} {v}" for k, v in sorted(c.items()))
            mark = "" if len(c) == 1 else "   ← flips"
            tail.append(f"  {item:<28} {dist}{mark}")
    return "\n".join([
        f"items {f.n_items}  ·  draws/item {f.draws_per_item:.1f}  ·  labels {{{labels}}}",
        "",
        f"  unstable items                 {f.unstable_items}/{f.n_items} ({f.unstable_fraction:.0%})   ← verdict changed on identical input",
        f"  pairwise disagreement          {f.pairwise_disagreement:.3f}      ← P(two re-runs of one item disagree)",
        f"  majority agreement             {f.majority_agreement:.3f}      ← mean fraction matching the modal verdict",
    ] + tail)


def cmd_run(a: argparse.Namespace) -> int:
    items = load_items(a.items)
    if a.limit:
        items = dict(list(items.items())[: a.limit])
    print(f"noisefloor: {len(items)} items × {a.draws} draws → {a.out}", file=sys.stderr)
    run_command(a.cmd, items, a.draws, a.out, parallel=a.parallel, timeout=a.timeout, quiet=a.quiet)
    rows = load_log(a.out)
    return _report_rows(rows, a.json)


def _report_rows(rows: List[dict], as_json: bool) -> int:
    scores = group_scores(rows)
    labels = group_labels(rows)
    # a draw is an error only if it produced neither a score nor a label
    errors = sum(1 for r in rows if r.get("score") is None and r.get("label") is None)
    out: Dict[str, object] = {"draws": len(rows), "errors": errors}
    if scores and any(len(v) >= 2 for v in scores.values()):
        r = stats.retest(scores)
        out["retest"] = r.to_dict()
        if not as_json:
            print("SCORES\n" + _fmt_retest(r) + "\n")
    if labels and any(len(v) >= 2 for v in labels.values()):
        f = stats.flips(labels)
        out["flips"] = f.to_dict()
        if not as_json:
            print("VERDICTS\n" + _fmt_flips(f, labels) + "\n")
    if not scores and not labels:
        print("no scores or labels parsed from the log — check the judge's stdout format", file=sys.stderr)
        return 1
    if errors and not as_json:
        print(f"({errors} draws errored or exited non-zero; they are excluded above)")
    if as_json:
        print(json.dumps(out, indent=2))
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    return _report_rows(load_log(a.log), a.json)


def cmd_compare(a: argparse.Namespace) -> int:
    sa = group_scores(load_log(a.a))
    sb = group_scores(load_log(a.b))
    c = stats.compare(sa, sb, seed=a.seed)
    if a.json:
        print(json.dumps(c.to_dict(), indent=2))
        return 0
    print(f"paired items {c.n_items}   mean A {c.mean_a:.3f}   mean B {c.mean_b:.3f}   Δ {c.delta:+.4f}")
    print(f"  noise SE (from retest)   {c.noise_se:.4f}   z = {c.z_noise:+.2f}")
    print(f"  paired SE (over items)   {c.paired_se:.4f}   95% CI [{c.ci95[0]:+.4f}, {c.ci95[1]:+.4f}]")
    print()
    print("  " + c.verdict)
    return 0 if not c.inside_noise else 2


def cmd_plan(a: argparse.Namespace) -> int:
    scores = group_scores(load_log(a.log))
    r = stats.retest(scores)
    k = stats.draws_needed(r.within_var, a.items or r.n_items, a.delta, a.power)
    print(f"within-item SD {r.within_sd:.4f} over {r.n_items} items.")
    print(f"To detect Δ = {a.delta} at 95% with {a.power:.0%} power on {a.items or r.n_items} items: "
          f"{k} draw(s) per item per condition  ({k * (a.items or r.n_items)} judge calls per condition).")
    return 0


def cmd_grade(a: argparse.Namespace) -> int:
    """Verdict judge vs. a labelled answer key: correctness AND stability per item."""
    from collections import Counter
    expected: Dict[str, str] = json.load(open(a.expected))
    labels = group_labels(load_log(a.log))
    rows = []
    n_scored = n_right = n_stable = 0
    for item in sorted(labels):
        key = item.rsplit(".", 1)[0] if item not in expected else item
        exp = expected.get(key, expected.get(item, "?"))
        c = Counter(labels[item])
        modal, m = c.most_common(1)[0]
        k = len(labels[item])
        stable = len(c) == 1
        if exp not in ("?", "ambiguous"):
            n_scored += 1
            n_right += int(modal == exp)
        n_stable += int(stable)
        verdict = ("ambiguous" if exp == "ambiguous" else "✓" if modal == exp else "✗ WRONG")
        verdict += "" if stable else f"  flips {k - m}/{k}"
        rows.append((item, exp, "  ".join(f"{l} {v}" for l, v in sorted(c.items())), verdict))
    w = max(len(r[0]) for r in rows)
    print(f"{'item':<{w}}  {'expected':<10} {'verdicts':<26} result")
    for r in rows:
        print(f"{r[0]:<{w}}  {r[1]:<10} {r[2]:<26} {r[3]}")
    print()
    print(f"correct (modal verdict, non-ambiguous items): {n_right}/{n_scored}")
    print(f"stable (all draws agree):                    {n_stable}/{len(rows)}")
    return 0 if n_right == n_scored else 3


def cmd_demo(a: argparse.Namespace) -> int:
    """A synthetic judge with known noise so the output is legible before you wire a real one."""
    from .runner import measure
    rng = random.Random(a.seed)
    true = {f"item{i:02d}": rng.uniform(3, 8) for i in range(a.items)}
    noise = a.noise

    def judge(item: str, _text: str):
        return max(1.0, min(10.0, true[item] + rng.gauss(0, noise)))

    rows_a = measure(judge, {k: "" for k in true}, draws=a.draws)
    # condition B: every item truly better by `shift`
    shift = a.shift

    def judge_b(item: str, _text: str):
        return max(1.0, min(10.0, true[item] + shift + rng.gauss(0, noise)))

    rows_b = measure(judge_b, {k: "" for k in true}, draws=a.draws)
    print(f"synthetic judge: true item scores U(3,8), judge noise SD = {noise}, condition B shifted by {shift:+}\n")
    _report_rows(rows_a, False)
    c = stats.compare(group_scores(rows_a), group_scores(rows_b))
    print(f"COMPARE A vs B   Δ {c.delta:+.3f}   noise SE {c.noise_se:.3f}   z {c.z_noise:+.2f}   CI [{c.ci95[0]:+.3f}, {c.ci95[1]:+.3f}]")
    print("  " + c.verdict)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="noisefloor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a judge command k× per item and report")
    r.add_argument("--cmd", required=True, help="shell command; {input} = item file path, {item} = id, {draw} = index")
    r.add_argument("--items", required=True, help="directory of item files, or JSONL of {id,text}")
    r.add_argument("--draws", type=int, default=5)
    r.add_argument("--out", default="noisefloor.jsonl")
    r.add_argument("--parallel", type=int, default=1)
    r.add_argument("--timeout", type=float, default=600.0)
    r.add_argument("--limit", type=int, default=0, help="only the first N items")
    r.add_argument("--quiet", action="store_true")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="noise floor / ICC / flip rate from a log")
    p.add_argument("log")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_report)

    c = sub.add_parser("compare", help="is A−B larger than the judge's own wobble?")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_compare)

    pl = sub.add_parser("plan", help="draws per item needed to detect a given Δ")
    pl.add_argument("log")
    pl.add_argument("--delta", type=float, required=True)
    pl.add_argument("--items", type=int, default=0, help="planned item count (default: as in log)")
    pl.add_argument("--power", type=float, default=0.8)
    pl.set_defaults(func=cmd_plan)

    g = sub.add_parser("grade", help="verdict judge vs. an answer key: correct AND stable per item")
    g.add_argument("log")
    g.add_argument("--expected", required=True, help="JSON {item: label|'ambiguous'}; .patch/.txt suffix on items is ignored")
    g.set_defaults(func=cmd_grade)

    d = sub.add_parser("demo", help="synthetic judge with known noise")
    d.add_argument("--items", type=int, default=30)
    d.add_argument("--draws", type=int, default=5)
    d.add_argument("--noise", type=float, default=0.8)
    d.add_argument("--shift", type=float, default=0.3)
    d.add_argument("--seed", type=int, default=1)
    d.set_defaults(func=cmd_demo)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

# Probe: zeroshot's acceptance verifier

Question: when zeroshot's independent reviewer judges the *same* diff against the
*same* task, how often does its verdict change?

Zeroshot's premise is that independent review catches what the implementing agent
missed. A reviewer whose accept/reject flips on identical input is adding noise to
the loop, not independence. This probe measures the flip rate directly.

## Design

- `fixture/cli.py` — a 20-line CLI with a `status` subcommand.
- `input.json` — the task: add `--json` to `status`, emitting `{ok, uptime_s}`, default unchanged.
- `items/` — three uncommitted diffs, labelled by what they actually do:
  - `correct.patch` — does exactly the task.
  - `wrong-key.patch` — emits `uptime` instead of `uptime_s`. One wrong key.
  - `breaks-default.patch` — adds the flag but makes the default output JSON too.
- `judge.graph.json` — a one-verifier graph: `judge` → succeed if `accepted`, fail `rejected`.
  No worker, no repair loop. The verifier reads `git diff`.
- `judge.runtime.json` — harness `claude`, provider `anthropic`, model `claude-sonnet-4-6`.
  Edit to probe a different judge.
- `judge.sh <patch>` — builds a scratch repo, applies the patch, runs the graph once, prints
  `{"label": "accepted"|"rejected"|"error…"}`.

## Run

```bash
# prerequisites on this machine: zeroshot on PATH, Claude Code signed in, noisefloor installed
cd probes/zeroshot
noisefloor run --cmd "./judge.sh {input} {item}" --items ./items --draws 10 --parallel 2 --out zeroshot-sonnet.jsonl
```

30 runs. Expect ~1–3 minutes each.

## Read

```
VERDICTS
items 3  ·  draws/item 10.0  ·  labels {accepted:N, rejected:M}

  unstable items          k/3     ← verdict changed on identical input
  pairwise disagreement   p       ← P(two re-runs of one item disagree)
```

What a good judge looks like: `correct` always accepted, the other two always rejected,
`unstable items 0/3`. Anything else is the finding — and `jq -r '.item+"  "+.label+"  "+.reason' zeroshot-sonnet.jsonl`
shows *which* defect the reviewer catches on which run.

Then swap the model in `judge.runtime.json` and run again:

```bash
noisefloor compare zeroshot-sonnet.jsonl zeroshot-opus.jsonl   # (scores) or diff the VERDICTS blocks
```

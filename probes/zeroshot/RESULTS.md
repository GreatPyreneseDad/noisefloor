# Results — zeroshot acceptance verifier, Sonnet 4.6, 2026-10-06

Judge: `builtin.agent.acceptance-verifier@1`, harness `claude`, model `claude-sonnet-4-6`,
one-verifier graph, 10 draws per item, 2 in parallel. Run from a MacBook Pro against the
local controller. Logs: `zeroshot-sonnet.example.jsonl`, `hard-sonnet.example.jsonl`.

## Easy set (3 items, 30 judgments)

| item | expected | verdicts |
|---|---|---|
| correct | accepted | accepted 10 |
| wrong-key (`uptime` for `uptime_s`) | rejected | rejected 10 |
| breaks-default | rejected | rejected 10 |

0 flips in 135 same-item pairs → pairwise disagreement < 2.2% (95% upper bound). ~19 s per judgment.

## Hard set (10 items, 100 judgments)

| item | expected | verdicts | right? | stable? | median latency |
|---|---|---|---|---|---|
| h01 correct (control) | accepted | accepted 10 | ✓ | ✓ | 16 s |
| h02 JSON to stderr | rejected | rejected 10 | ✓ | ✓ | 17 s |
| h03 exit code 1 | rejected | rejected 10 | ✓ | ✓ | 19 s |
| h04 `"ok": "true"` string | rejected | rejected 10 | ✓ | ✓ | 18 s |
| h05 flag on wrong subcommand | rejected | rejected 10 | ✓ | ✓ | **31 s** |
| h06 `uptime_s` truncated to int | ambiguous | accepted 10 | — | ✓ | 20 s |
| h07 hand-built JSON, no `json` import | accepted | accepted 9 · rejected 1 | ✓ | **flips** | 22 s |
| h08 `--help` says YAML | ambiguous | rejected 9 · accepted 1 | — | **flips** | 24 s |
| h09 default output gains blank line | rejected | rejected 10 | ✓ | ✓ | 23 s |
| h10 `START` reset → `uptime_s` ≈ 0 | rejected | rejected 9 · accepted 1 | ✓ | **flips** | **34 s** |

**Correct on 8/8 non-ambiguous items.** The verifier caught every planted defect by majority,
including the two I predicted it would miss (JSON to stderr; the timer reset that leaves valid JSON
with a wrong number). Prediction was wrong; the record stands.

**Stable on 7/10.** Three items flipped once in ten. On the ten real items that is 54 disagreeing
pairs out of 900 → **6% pairwise disagreement**, against <2.2% on the easy set. The flip rate is
not a property of the judge; it is a property of the judge × the difficulty of the item.

## What the flips are

- **h07** — correct behaviour, crude code. One run in ten rejected a patch that does exactly what
  was asked, presumably on style. A review loop that routes this to repair spends a worker pass
  fixing nothing.
- **h08** — correct behaviour, misleading help text. 9/10 rejected. The verifier treats docs as
  part of "implements the task"; one run didn't. Reasonable people differ; the verifier differs
  with itself.
- **h10** — a real logic bug (`uptime_s` always ~0) that produces valid JSON. 9/10 caught it. One
  run accepted it. This is the one that matters: a 10% chance of shipping a wrong number, and the
  latency (26–61 s, vs ~18 s baseline) says the verifier was *working* on these — the hard
  items are where it reads longest and agrees least.

## What this means for a review loop

With one verifier and the `software-change` loop, a borderline-correct change has roughly a 1-in-10
chance of a spurious rejection → wasted repair pass; a borderline-wrong change has roughly a 1-in-10
chance of slipping through. Two independent verifiers in `par` with an `all` join cut the slip-through
to ~1% but double the spurious rejections. Which side of that trade you want is a product decision;
the instrument just says the trade exists and sizes it.

## What broke, in zeroshot itself

1. Graph admission reports one missing required field per attempt (`promotedStatePaths` on the
   root `seq`). Batch the errors.
2. A local run refuses a workspace without a GitHub `origin`, even a scratch repo that will never
   be pushed. The error says what, not why.
3. The verifier's diagnostic (the one-sentence reason) is not in the foreground NDJSON stream.
   You get `accepted`/`rejected`; the *why* lives in the ledger.

## Next

- Haiku 4.5 as the judge on the same 10 items; `compare` the flip tables.
- 30 draws on h07/h08/h10 to tighten the per-item flip estimate (10 draws gives ±0.19 on a 0.1 rate).
- Reproduce the easy-set run against a two-verifier `par` graph to measure the trade above directly.

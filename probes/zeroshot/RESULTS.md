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

## Hard set — Haiku 4.5 as the judge (same 10 items, 100 judgments)

Predicted beforehand: h10 drops below 9/10 rejected (**yes — 5/10**); h02 stderr loses at least one (**no — 10/10**). One for two.

| item | expected | Sonnet 4.6 | Haiku 4.5 |
|---|---|---|---|
| h01 correct (control) | accepted | accepted 10 | accepted 9 · **rejected 1** |
| h02 JSON to stderr | rejected | rejected 10 | rejected 10 |
| h03 exit code 1 | rejected | rejected 10 | rejected 10 |
| h04 `"ok": "true"` | rejected | rejected 10 | rejected 10 |
| h05 flag on wrong subcommand | rejected | rejected 10 | rejected 10 |
| h06 int uptime | ambiguous | accepted 10 | accepted 10 |
| h07 hand-built JSON | accepted | accepted 9 · rejected 1 | accepted 9 · rejected 1 |
| h08 `--help` says YAML | ambiguous | rejected 9 · accepted 1 | rejected 10 |
| h09 default gains newline | rejected | rejected 10 | rejected 10 |
| h10 `START` reset, `uptime_s` ≈ 0 | rejected | rejected 9 · accepted 1 | **accepted 5 · rejected 5** |
| **correct by majority** | | 8/8 | 8/8 |
| **stable** | | 7/10 | 7/10 |
| **pairwise disagreement** | | 6.0% | 9.6% |

**Same accuracy. Different instrument.** By the number everyone reports — correct by majority —
the two judges are identical, 8/8. The retest data says otherwise:

- On the one real logic bug that produces valid output, Haiku is a **coin flip** (5/5, latency
  32–70 s — it worked hard and still split). Sonnet caught it 9 times in 10.
- Haiku **rejected the correct control once in ten.** A clean change has a ~10% chance of a
  spurious repair pass under a Haiku verifier. Sonnet: zero in twenty (easy + hard controls).
- Haiku is *more* decisive on the ambiguous help-text item (10/10 vs 9/10). Decisiveness is not
  reliability; it just means the coin is weighted differently.

A single accuracy number cannot see any of this. It takes the retest.

**Latency is a free uncertainty signal.** On both judges, the items that flipped are the items
that took longest: Sonnet h05/h10 at 31–34 s vs ~18 s baseline; Haiku h10 at 32–70 s. A verifier
that is taking 2× its median is a verifier whose verdict should be drawn again. That is a one-line
change in a review graph: `attempts: 2` gated on latency, require agreement. Cheaper than two
verifiers on every pass.

## Correction, after running `compare` on these two logs

The paragraph above says 6.0% vs 9.6%. `noisefloor compare hard-sonnet hard-haiku` says:

```
pairwise disagreement A 6.0%   B 9.6%   Δ -3.6%
95% CI (bootstrap over items) [-12.7%, +4.0%]   p≈0.49
INDISTINGUISHABLE: with 10 items you cannot say one judge is steadier.
```

The aggregate claim is not established. Ten items is too few to rank two judges on overall
disagreement, and the tool built to say so said so — to its author. What the data do support is
per item: on h10, Haiku 5/10 vs Sonnet 1/10 (Fisher exact two-sided p = 0.14 — suggestive, not
significant; `plan --flip 0.05 0.5` says ~30 draws each to settle it). On h01, Haiku 1/10 vs
Sonnet 0/10 is nothing (p = 1.0).

**Latency, refined.** Measured against the judge's *overall* median rather than each item's own:
Sonnet's only flip on an otherwise-stable item (h07, draw 1) was its only slow draw on that item
— 42 s against a 22 s median. Haiku's spurious reject of the correct control (h01, draw 4) was its
only slow draw there — 44 s against 19 s. On h10, 5 of Haiku's 8 slow draws were minority verdicts.
Across both judges, the slow draw on a stable item *is* the flip. That is the one-line graph rule:
redraw when a verifier runs long.

## Next

- ~~Haiku 4.5 as the judge on the same 10 items.~~ Done; above.
- Opus 4.7 for the top of the range; does h10 reach 10/10?
- 30 draws on h07/h08/h10 to tighten the per-item flip estimate (10 draws gives ±0.19 on a 0.1 rate).
- Reproduce the easy-set run against a two-verifier `par` graph to measure the trade above directly.

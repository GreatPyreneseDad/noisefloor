# Results — readability judge via `claude -p`, 2026-10-06

8 snippets × 8 draws, Sonnet 4.6 and Haiku 4.5, run from the container. Logs: `score-*.example.jsonl`.

| | Sonnet | Haiku |
|---|---|---|
| noise floor (within-item SD, 10-pt scale) | **0.25** | **0.70** |
| ICC(1) | 0.988 | 0.926 |
| min detectable Δ at 8 draws | 0.09 | 0.24 |
| items scored identically on all 8 draws | 6/8 | 1/8 |

Haiku is 2.8× noisier than Sonnet as a readability grader. Its worst item, the comment-drowned
`median` (s05), ranged 3–7 across eight identical calls. Sonnet gave it 6 eight times.

**compare: Δ = +0.41 (Sonnet higher), 4.4× the retest SE, CI over items [−0.11, +0.84].**
Verdict: `ITEM-DEPENDENT`. The judges differ by more than noise explains, but not in a consistent
direction — Sonnet rates the over-commented snippet 6.0 vs Haiku 4.6; Haiku rates the flat rewrite
8.1 vs Sonnet 7.0. That is a difference in *taste*, reproducible per item, not a bias. More items
would resolve whether one systematically grades higher; more draws would not.

## 1–100 scale (same 8 items × 8 draws)

Prediction written before the run: the integer 1–10 scale was quantising noise away, and a 1–100
rubric would reveal a larger relative noise floor. **Wrong.**

| | Sonnet 1–10 | Sonnet 1–100 | Haiku 1–10 | Haiku 1–100 |
|---|---|---|---|---|
| within-item SD | 0.25 | 1.95 | 0.70 | 5.42 |
| SD as % of scale range | 2.8% | **2.0%** | 7.8% | **5.5%** |
| ICC(1) | 0.988 | 0.995 | 0.926 | 0.959 |

Relative noise went *down* on the finer scale, for both judges. The 1–10 floor was the judge, not
the scale. The Sonnet/Haiku ratio held at ~2.8×. Item means mapped cleanly (s01: 9.0 → 92.6;
s05: 6.0 → 61.5), so the two scales measure the same thing with the same reliability.

What the finer scale did expose is the *shape* of Sonnet's noise: it is not Gaussian jitter but
two attractors — 90/93, 33–34/38, 31/38, 52/58, 77/80, 12/14. Eight draws land on one of two
values. Haiku's draws are spread (s03: 38–58; s05: 48–73). Same SD summary, different mechanism;
the raw per-item lists in the logs show it and the summary statistics do not.

`compare` at 1–100: Δ = +4.5, 6.3× retest SE, CI over items [−1.6, +11.7] → `ITEM-DEPENDENT`
again. Same verdict as 1–10. The taste difference is stable across scales.

Also fixed by this probe: `parse_output` now tolerates markdown fences and chatter (Haiku wraps
its JSON in ```; 64/64 draws parsed as empty before the fix).

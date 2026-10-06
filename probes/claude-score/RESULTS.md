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

**Caveat on the floor.** Integer 1–10 output quantises noise away: a judge that is internally
"6.3 ± 0.4" prints 6 every time. Sonnet's 0.25 is partly the scale, not only the judge. A 0–100
rubric would show the noise the integer scale hides; that is the next probe.

Also fixed by this probe: `parse_output` now tolerates markdown fences and chatter (Haiku wraps
its JSON in ```; 64/64 draws parsed as empty before the fix).

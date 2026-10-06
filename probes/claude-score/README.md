# Probe: a scoring judge (Claude Code CLI, readability 1–10)

The zeroshot probe exercised verdicts. This one exercises **scores** — the `retest` / ICC /
`compare` path — against the cheapest judge you already have: `claude -p`, no API key.

Eight Python snippets, graded for readability 1–10. The set is built so the *right* answer is
contested: two implementations of `median` (clean vs. one-liner), an over-engineered one, a
misnamed one, one drowning in comments, a five-deep nest and its flat rewrite, and a formula
with magic numbers. Reasonable people disagree. The question is whether the judge disagrees
with *itself*.

```bash
cd probes/claude-score
noisefloor run --cmd "./judge.sh {input}" --items ./items --draws 8 --parallel 4 --out score-sonnet.jsonl
NF_MODEL=haiku noisefloor run --cmd "./judge.sh {input}" --items ./items --draws 8 --parallel 4 --out score-haiku.jsonl
noisefloor compare score-sonnet.jsonl score-haiku.jsonl
noisefloor plan score-sonnet.jsonl --delta 0.5
```

What to look at: the **noise floor** (within-item SD on a 10-point scale), **ICC** (if it is
below 0.5 the judge is mostly grading itself), and **min detectable Δ** — the smallest
readability improvement this judge could ever confirm with this many draws. Then `compare`:
does Sonnet score systematically higher than Haiku, or is that inside the noise too?

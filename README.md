# noisefloor

Measure your LLM judge before you trust its deltas.

Every eval now has a model in the loop scoring outputs, reviewing diffs, or
declaring pass/fail. Almost nobody measures how much that judge disagrees
*with itself* on identical input. Until you do, a "+4 points" result is a
number with no error bar — and the judge's own wobble is usually the biggest
term in it.

`noisefloor` runs the judge k times per item under identical conditions and
reports the one thing that lets you read every other number: the judge's
retest variance.

```
$ noisefloor run --cmd 'python judge.py {input}' --items ./cases --draws 5 --out judge.jsonl

SCORES
items 40  ·  draws/item 5.0  ·  scores in [1, 10]  mean 6.21

  noise floor (within-item SD)   0.79      ← the judge re-scoring the same thing
  between-item SD                1.54      ← spread of item means
  ICC(1)                         0.78      ← share of variance that is the items, not the judge
  min detectable Δ (95%)         0.18      ← smallest A−B this many draws can resolve

$ noisefloor compare model_a.jsonl model_b.jsonl

paired items 40   mean A 6.21   mean B 6.33   Δ -0.12
  noise SE (from retest)   0.088   z = -1.36
  paired SE (over items)   0.102   95% CI [-0.31, +0.08]

  INSIDE THE NOISE: Δ=-0.120 is 1.4× the judge's own retest SE (0.088); 95% CI spans 0.
  Re-scoring the same work would produce a difference this big.
```

For categorical judges (accept/reject, pass/fail) it reports verdict stability
instead:

```
VERDICTS
items 3  ·  draws/item 10.0  ·  labels {accepted:14, rejected:16}

  unstable items                 1/3 (33%)   ← verdict changed on identical input
  pairwise disagreement          0.178       ← P(two re-runs of one item disagree)
  majority agreement             0.867

  breaks-default.patch         rejected 10
  correct.patch                accepted 10
  wrong-key.patch              accepted 4  rejected 6   ← flips
```

## Install

```bash
pip install noisefloor-llm    # the command is still `noisefloor`; the bare PyPI name was taken
```

No dependencies. Python 3.9+.

## Use

Your judge is any command that reads an item and prints a score or a label.
`{input}` is the item's file path, `{item}` its id, `{draw}` the repetition index.

```bash
# score judge: prints a number or {"score": 7.5}
noisefloor run --cmd 'python judge.py {input}' --items ./cases --draws 5 --out a.jsonl

# verdict judge: prints ACCEPT / REJECT or {"label": "..."}
noisefloor run --cmd './review.sh {input}' --items ./diffs --draws 10 --out r.jsonl

# re-read a log without re-running anything (adds per-item flip CIs and a latency section)
noisefloor report a.jsonl

# verdict judge against an answer key: right AND stable, per item
noisefloor grade r.jsonl --expected key.json

# is A really better than B, or is that the judge?
noisefloor compare a.jsonl b.jsonl       # exit 2 when inside the noise

# how many draws would it take to see a 0.05 change on 100 items?
noisefloor plan a.jsonl --delta 0.05 --items 100

# verdicts: two judges' flip tables side by side, with a CI on the difference
noisefloor compare r_sonnet.jsonl r_haiku.jsonl

# verdicts: how many draws to show an item flips more than a tolerable 5%?
noisefloor plan r.jsonl --flip 0.05 0.15

# see the output on a synthetic judge with known noise
noisefloor demo --noise 0.8 --shift 0.3
```

Items are a directory of files (id = filename) or a JSONL of `{"id", "text"}`.
Every draw is appended to the log as it finishes; a killed run keeps what it measured.

From Python:

```python
from noisefloor import measure, retest, compare, group_scores

rows = measure(lambda item_id, text: my_judge(text), items, draws=5)
r = retest(group_scores(rows))
print(r.within_sd, r.icc, r.min_detectable_delta)
```

## What the numbers mean

**noise floor** — pooled within-item standard deviation. The judge scoring the
same item again. This is the error bar every downstream number inherits.

**ICC(1)** — intraclass correlation, one-way random effects. The fraction of
total score variance explained by *which item it is* rather than *which draw
it was*. 0.9 is a judge you can use for fine comparisons; 0.5 means half of
what it tells you is itself; below 0.5 you are mostly measuring the judge.

**min detectable Δ** — for a paired comparison of two conditions over the same
items and draw count, the smallest mean difference that clears 1.96 × the
noise-only standard error. If your reported improvement is smaller than this,
it has not been shown.

**compare** reports two tests and names which one failed. `INSIDE THE JUDGE'S
NOISE`: re-scoring the same work would produce this delta — more draws help.
`ITEM-DEPENDENT`: the judges differ by more than noise, but not in a consistent
direction across items — a difference in taste, not a bias; more items help,
more draws don't. `CLEARS THE NOISE`: both pass.

**per-item flip CIs** — a 1-in-10 flip is not "10%". At n=10 the Wilson interval
is [2%, 40%]. The report prints it so nobody reads 0.1 as a measurement.

**latency** — flagged relative to the judge's overall median. In every run so far,
the slow draw on an otherwise-stable item was the flip. Treat a slow verifier as
an uncertain one and redraw.

**flips** — for categorical judges: the fraction of items whose verdict changed
across identical re-runs, and the probability that two random re-runs of the
same item disagree. A reviewer with a 20% pairwise disagreement rate is a
reviewer whose rejections are 20% weather.

## Probes

`probes/` holds ready-made judge wrappers for systems people actually use.

- [`probes/zeroshot`](probes/zeroshot) — the acceptance verifier in
  [zeroshot](https://github.com/the-open-engine/zeroshot), judging three
  labelled diffs (one correct, one with a wrong key, one that breaks the
  default) ten times each. Measures whether "independent review" is stable
  on identical input.

- [`probes/claude-score`](probes/claude-score) — a 1–10 readability grader on
  `claude -p` (no API key). Exercises the score path: noise floor, ICC, `compare`.
  Sonnet 0.25 SD vs Haiku 0.70 on the same eight snippets.

Add a probe by writing a shell wrapper that prints a score or label. PRs welcome.

## Why this exists

An interferometer built from several LLM "lenses" had a truth-detection
threshold of σ² < 0.02. Its retest jitter, never measured, was 0.005–0.02.
The gate never opened — including on *water boils at 100 °C at sea level*.
The threshold had been set below the instrument's own noise. This tool is that
mistake, generalised, so you can find it in an afternoon instead of a year.

## License

MIT.

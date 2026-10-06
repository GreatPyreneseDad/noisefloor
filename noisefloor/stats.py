"""noisefloor.stats — how much of your judge's signal is the judge.

Everything here is plain statistics over a *retest design*: the same item is
scored k times under identical conditions. From that you learn the judge's own
variance, and only then can you say whether a difference between two
conditions is larger than the judge's wobble.

Terms
  item      one input the judge scores (a prompt, a diff, a transcript)
  draw      one scoring of one item; k draws per item
  condition a system under evaluation (model A vs model B, prompt v1 vs v2)

Nothing imports numpy. The arithmetic is small and should be legible.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

Scores = Mapping[str, Sequence[float]]   # item -> draws
Labels = Mapping[str, Sequence[str]]     # item -> draws (categorical verdicts)

Z95 = 1.959963984540054


# --- helpers ---------------------------------------------------------------

def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _var(xs: Sequence[float]) -> float:
    """Unbiased sample variance; 0.0 for n < 2."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (n - 1)


def _pooled_within(scores: Scores) -> tuple[float, int, int]:
    """Pooled within-item variance, total draws, items with ≥2 draws."""
    num = 0.0
    dof = 0
    n_items = 0
    total = 0
    for draws in scores.values():
        total += len(draws)
        if len(draws) >= 2:
            num += _var(draws) * (len(draws) - 1)
            dof += len(draws) - 1
            n_items += 1
    return (num / dof if dof else 0.0), total, n_items


# --- retest reliability -----------------------------------------------------

@dataclass
class Retest:
    n_items: int
    draws_per_item: float          # mean k
    within_var: float              # pooled σ²_w — the noise floor
    within_sd: float
    between_var: float             # variance of item means (includes σ²_w/k)
    icc: float                     # ICC(1): share of total variance that is real item signal
    score_range: tuple[float, float]
    mean_score: float
    # Smallest paired difference between two conditions (each averaged over the
    # same items × k draws) that clears the noise at 95%, from σ²_w alone.
    min_detectable_delta: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["score_range"] = list(self.score_range)
        return d


def retest(scores: Scores) -> Retest:
    """Characterise a judge from repeated draws on the same items.

    ICC(1) via one-way random-effects ANOVA:
        MSW = pooled within-item variance
        MSB = k0 · var(item means)   (k0 = harmonic-ish mean k for unbalanced)
        ICC = (MSB − MSW) / (MSB + (k0 − 1)·MSW), clamped to [0, 1]
    ICC → 1: the judge reproduces itself; differences between items are real.
    ICC → 0: the judge's draws on one item are as spread out as scores across
    all items; it is mostly measuring itself.
    """
    items = [list(v) for v in scores.values() if len(v) > 0]
    if not items:
        raise ValueError("no scores")
    n = len(items)
    ks = [len(v) for v in items]
    total = sum(ks)
    k0 = (total - sum(k * k for k in ks) / total) / (n - 1) if n > 1 else float(ks[0])

    msw, _, _ = _pooled_within(scores)
    item_means = [_mean(v) for v in items]
    grand = _mean([x for v in items for x in v])
    msb = (sum(k * (m - grand) ** 2 for k, m in zip(ks, item_means)) / (n - 1)) if n > 1 else 0.0

    denom = msb + (k0 - 1) * msw
    icc = (msb - msw) / denom if denom > 0 else 0.0
    icc = max(0.0, min(1.0, icc))

    flat = [x for v in items for x in v]
    kbar = total / n
    # SE of a paired mean difference from within-noise alone: two conditions,
    # each mean over n items × k draws → var = 2σ²_w / (n·k)
    mdd = Z95 * math.sqrt(2 * msw / (n * kbar)) if n * kbar > 0 else float("nan")

    return Retest(
        n_items=n,
        draws_per_item=kbar,
        within_var=msw,
        within_sd=math.sqrt(msw),
        between_var=_var(item_means) if n > 1 else 0.0,
        icc=icc,
        score_range=(min(flat), max(flat)),
        mean_score=grand,
        min_detectable_delta=mdd,
    )


# --- categorical verdicts ---------------------------------------------------

@dataclass
class Flips:
    n_items: int
    draws_per_item: float
    unstable_items: int            # items where not every draw agreed
    unstable_fraction: float
    pairwise_disagreement: float   # P(two random draws of the same item disagree)
    majority_agreement: float      # mean fraction of draws matching the item's modal label
    label_counts: Dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


def flips(labels: Labels) -> Flips:
    """Verdict stability for categorical judges (accept/reject, pass/fail, A/B)."""
    items = [list(v) for v in labels.values() if len(v) > 0]
    if not items:
        raise ValueError("no labels")
    unstable = 0
    pair_dis_num = 0.0
    pair_dis_den = 0
    maj = []
    counts: Counter = Counter()
    for v in items:
        counts.update(v)
        c = Counter(v)
        k = len(v)
        if len(c) > 1:
            unstable += 1
        if k >= 2:
            same_pairs = sum(m * (m - 1) for m in c.values())
            pair_dis_num += (k * (k - 1) - same_pairs)
            pair_dis_den += k * (k - 1)
        maj.append(max(c.values()) / k)
    n = len(items)
    return Flips(
        n_items=n,
        draws_per_item=sum(len(v) for v in items) / n,
        unstable_items=unstable,
        unstable_fraction=unstable / n,
        pairwise_disagreement=(pair_dis_num / pair_dis_den) if pair_dis_den else 0.0,
        majority_agreement=_mean(maj),
        label_counts=dict(counts),
    )


# --- comparing two conditions -----------------------------------------------

@dataclass
class Comparison:
    n_items: int
    mean_a: float
    mean_b: float
    delta: float                   # mean over items of (mean_a_i − mean_b_i)
    noise_se: float                # SE of delta from within-draw noise alone
    z_noise: float                 # delta / noise_se
    paired_se: float               # SE of delta from item-level paired differences (bootstrap)
    ci95: tuple[float, float]      # bootstrap CI on delta
    within_var_a: float
    within_var_b: float
    inside_noise: bool             # |delta| cannot be distinguished from judge wobble
    verdict: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ci95"] = list(self.ci95)
        return d


def compare(a: Scores, b: Scores, *, seed: int = 0, boots: int = 2000) -> Comparison:
    """Is condition A really different from condition B, given the judge's noise?

    Items are paired by key; items missing from either side are dropped.
    Two tests are reported and the stricter one decides:
      - z_noise: delta against the SE implied by pooled within-item variance
        (what the judge would produce re-scoring the *same* work).
      - bootstrap CI over items of the paired difference of item means (what
        you'd get re-sampling items). Includes both judge noise and item
        heterogeneity.
    `inside_noise` is True when |z_noise| < 1.96 OR the bootstrap CI spans 0.
    """
    keys = [k for k in a if k in b and len(a[k]) and len(b[k])]
    if len(keys) < 2:
        raise ValueError("need ≥2 paired items")
    n = len(keys)
    ma = [_mean(a[k]) for k in keys]
    mb = [_mean(b[k]) for k in keys]
    diffs = [x - y for x, y in zip(ma, mb)]
    delta = _mean(diffs)

    wa, ta, _ = _pooled_within({k: a[k] for k in keys})
    wb, tb, _ = _pooled_within({k: b[k] for k in keys})
    ka = ta / n
    kb = tb / n
    noise_var = (wa / ka + wb / kb) / n if ka and kb else float("nan")
    noise_se = math.sqrt(noise_var) if noise_var == noise_var else float("nan")
    z = delta / noise_se if noise_se and noise_se > 0 else (float("inf") if delta else 0.0)

    rng = random.Random(seed)
    bs = []
    for _ in range(boots):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        bs.append(_mean(sample))
    bs.sort()
    lo = bs[int(0.025 * boots)]
    hi = bs[int(0.975 * boots) - 1]
    paired_se = math.sqrt(_var(diffs) / n)

    inside = abs(z) < Z95 or (lo <= 0.0 <= hi)
    if inside:
        verdict = (f"INSIDE THE NOISE: Δ={delta:+.3f} is {abs(z):.1f}× the judge's own "
                   f"retest SE ({noise_se:.3f}); 95% CI [{lo:+.3f}, {hi:+.3f}] spans 0. "
                   "Re-scoring the same work would produce a difference this big.")
    else:
        verdict = (f"CLEARS THE NOISE: Δ={delta:+.3f} is {abs(z):.1f}× the judge's retest SE "
                   f"({noise_se:.3f}); 95% CI [{lo:+.3f}, {hi:+.3f}].")
    return Comparison(
        n_items=n, mean_a=_mean(ma), mean_b=_mean(mb), delta=delta,
        noise_se=noise_se, z_noise=z, paired_se=paired_se, ci95=(lo, hi),
        within_var_a=wa, within_var_b=wb, inside_noise=inside, verdict=verdict,
    )


# --- planning ----------------------------------------------------------------

def draws_needed(within_var: float, n_items: int, delta: float, power: float = 0.8) -> int:
    """How many draws per item to detect `delta` at 95% / given power from noise alone.

    Solves  delta = (z_α + z_β)·sqrt(2σ²_w / (n·k))  for k.
    """
    zb = {0.8: 0.8416, 0.9: 1.2816, 0.95: 1.6449}.get(power, 0.8416)
    if delta <= 0 or n_items <= 0:
        raise ValueError("delta and n_items must be positive")
    k = 2 * within_var * (Z95 + zb) ** 2 / (n_items * delta * delta)
    return max(1, math.ceil(k))


__all__ = ["Retest", "retest", "Flips", "flips", "Comparison", "compare", "draws_needed", "Z95"]

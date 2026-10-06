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

    noise_fail = abs(z) < Z95
    items_fail = lo <= 0.0 <= hi
    inside = noise_fail or items_fail
    if noise_fail:
        verdict = (f"INSIDE THE JUDGE'S NOISE: Δ={delta:+.3f} is {abs(z):.1f}× the retest SE ({noise_se:.3f}). "
                   "Re-scoring the same work would produce a difference this big. More draws per item would help.")
    elif items_fail:
        verdict = (f"ITEM-DEPENDENT: Δ={delta:+.3f} is {abs(z):.1f}× the retest SE — the judge noise does not explain it — "
                   f"but the 95% CI over items [{lo:+.3f}, {hi:+.3f}] spans 0: the direction is not consistent from item to item. "
                   "More items would help; more draws would not.")
    else:
        verdict = (f"CLEARS THE NOISE: Δ={delta:+.3f} is {abs(z):.1f}× the retest SE ({noise_se:.3f}); "
                   f"95% CI over items [{lo:+.3f}, {hi:+.3f}].")
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


# --- intervals, verdict comparison, verdict planning -------------------------

def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n. Honest at small n and at 0 or n."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class ItemFlip:
    item: str
    n: int
    modal: str
    minority: int                  # draws not matching the modal label
    rate: float                    # minority / n
    ci95: tuple[float, float]      # Wilson on the minority rate
    counts: Dict[str, int]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ci95"] = list(self.ci95)
        return d


def item_flips(labels: Labels) -> List[ItemFlip]:
    """Per-item minority-verdict rate with a Wilson interval — 1/10 is not 0.10, it is [0.02, 0.40]."""
    out: List[ItemFlip] = []
    for item, v in labels.items():
        v = list(v)
        if not v:
            continue
        c = Counter(v)
        modal, m = c.most_common(1)[0]
        k = len(v) - m
        out.append(ItemFlip(item=item, n=len(v), modal=modal, minority=k, rate=k / len(v),
                            ci95=wilson(k, len(v)), counts=dict(c)))
    return out


def _pairwise_disagreement(labels: Labels) -> float:
    num = den = 0.0
    for v in labels.values():
        k = len(v)
        if k < 2:
            continue
        c = Counter(v)
        num += k * (k - 1) - sum(m * (m - 1) for m in c.values())
        den += k * (k - 1)
    return num / den if den else 0.0


@dataclass
class LabelComparison:
    n_items: int
    disagreement_a: float
    disagreement_b: float
    delta: float                   # a − b
    ci95: tuple[float, float]      # bootstrap over items
    p_value: float                 # two-sided, bootstrap: P(|Δ*| ≥ |Δ|) under item-resampling of the null
    items: List[tuple[str, Dict[str, int], Dict[str, int]]]   # side-by-side counts
    verdict: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ci95"] = list(self.ci95)
        return d


def compare_labels(a: Labels, b: Labels, *, seed: int = 0, boots: int = 2000) -> LabelComparison:
    """Do two verdict judges differ in how often they disagree with themselves?

    Items paired by key. Statistic: pairwise disagreement rate, A − B. Draws
    within an item are not independent, so the bootstrap resamples *items*.
    """
    keys = [k for k in a if k in b and len(a[k]) >= 2 and len(b[k]) >= 2]
    if len(keys) < 2:
        raise ValueError("need ≥2 paired items with ≥2 draws each")
    da = _pairwise_disagreement({k: a[k] for k in keys})
    db = _pairwise_disagreement({k: b[k] for k in keys})
    delta = da - db
    rng = random.Random(seed)
    n = len(keys)
    bs = []
    for _ in range(boots):
        s = [keys[rng.randrange(n)] for _ in range(n)]
        bs.append(_pairwise_disagreement({i: a[k] for i, k in enumerate(s)})
                  - _pairwise_disagreement({i: b[k] for i, k in enumerate(s)}))
    bs.sort()
    lo, hi = bs[int(0.025 * boots)], bs[int(0.975 * boots) - 1]
    # bootstrap p-value: centre the distribution on 0 and ask how often |Δ*| ≥ |Δ|
    centred = [x - delta for x in bs]
    p = sum(1 for x in centred if abs(x) >= abs(delta)) / boots
    side = [(k, dict(Counter(a[k])), dict(Counter(b[k]))) for k in keys]
    if lo <= 0.0 <= hi:
        verdict = (f"INDISTINGUISHABLE: A disagrees with itself {da:.1%}, B {db:.1%}; Δ={delta:+.1%}, "
                   f"95% CI [{lo:+.1%}, {hi:+.1%}] spans 0 (p≈{p:.2f}). With {n} items you cannot say one judge is steadier.")
    else:
        worse = "A" if delta > 0 else "B"
        verdict = (f"DIFFERENT: {worse} is the noisier judge. A {da:.1%} vs B {db:.1%}; Δ={delta:+.1%}, "
                   f"95% CI [{lo:+.1%}, {hi:+.1%}] (p≈{p:.2f}).")
    return LabelComparison(n_items=n, disagreement_a=da, disagreement_b=db, delta=delta,
                           ci95=(lo, hi), p_value=p, items=side, verdict=verdict)


def draws_needed_flip(p_null: float, p_alt: float, power: float = 0.8) -> int:
    """Draws on ONE item to tell a flip rate of p_alt from p_null (one-sample binomial, normal approx)."""
    zb = {0.8: 0.8416, 0.9: 1.2816, 0.95: 1.6449}.get(power, 0.8416)
    if not (0 <= p_null < 1 and 0 <= p_alt <= 1) or p_null == p_alt:
        raise ValueError("need 0 ≤ p_null ≠ p_alt ≤ 1")
    num = (Z95 * math.sqrt(p_null * (1 - p_null)) + zb * math.sqrt(p_alt * (1 - p_alt))) ** 2
    return max(1, math.ceil(num / (p_alt - p_null) ** 2))


# --- latency as an uncertainty signal ----------------------------------------

@dataclass
class LatencyReport:
    items: Dict[str, dict]         # item -> {median, slow: [(draw, latency, label_or_score)], n}
    slow_total: int
    slow_minority: int             # slow draws whose label is the item's minority verdict
    overall_median: float
    flagged_items: List[str]       # items with ≥1 slow draw

    def to_dict(self) -> dict:
        return asdict(self)


def latency(rows: Iterable[dict], factor: float = 1.75) -> LatencyReport:
    """Flag draws slower than `factor` × the judge's OVERALL median latency.

    Relative to the overall median, not the item's own: an item that is slow on
    every draw is itself the signal (the judge is working harder there), and
    those were the items that flipped. items[*]["slow_item"] marks an item whose
    median exceeds the overall median by `factor`.
    """
    by: Dict[str, List[dict]] = {}
    for r in rows:
        if r.get("latency_s") is not None:
            by.setdefault(r["item"], []).append(r)
    all_lat = sorted(r["latency_s"] for rs in by.values() for r in rs)
    if not all_lat:
        return LatencyReport(items={}, slow_total=0, slow_minority=0, overall_median=0.0, flagged_items=[])
    om = all_lat[len(all_lat) // 2] if len(all_lat) % 2 else (all_lat[len(all_lat) // 2 - 1] + all_lat[len(all_lat) // 2]) / 2
    cutoff = factor * om
    items: Dict[str, dict] = {}
    slow_total = slow_minority = 0
    flagged = []
    for item, rs in by.items():
        lats = sorted(r["latency_s"] for r in rs)
        med = lats[len(lats) // 2] if len(lats) % 2 else (lats[len(lats) // 2 - 1] + lats[len(lats) // 2]) / 2
        labels = [r.get("label") for r in rs if r.get("label") is not None]
        modal = Counter(labels).most_common(1)[0][0] if labels else None
        slow = []
        for r in rs:
            if r["latency_s"] > cutoff:
                val = r.get("label") if r.get("label") is not None else r.get("score")
                slow.append((r["draw"], r["latency_s"], val))
                slow_total += 1
                if modal is not None and r.get("label") is not None and r["label"] != modal:
                    slow_minority += 1
        items[item] = {"median": med, "n": len(rs), "slow": slow, "slow_item": med > cutoff,
                       "flips": len(set(labels)) > 1 if labels else None}
        if slow or med > cutoff:
            flagged.append(item)
    return LatencyReport(items=items, slow_total=slow_total, slow_minority=slow_minority,
                         overall_median=om, flagged_items=flagged)


def draws_to_separate(rate: float, p0: float, n_now: int, max_n: int = 2000) -> Optional[int]:
    """Smallest n at which a Wilson interval on `rate` would exclude `p0`, if the rate holds.

    The honest cost of confirming "this item flips more than p0". None if rate ≤ p0.
    """
    if rate <= p0:
        return None
    n = max(n_now, 1)
    while n <= max_n:
        k = round(rate * n)
        if wilson(k, n)[0] > p0:
            return n
        n += 1
    return None


__all__ += ["wilson", "ItemFlip", "item_flips", "LabelComparison", "compare_labels",
            "draws_needed_flip", "LatencyReport", "latency", "draws_to_separate"]

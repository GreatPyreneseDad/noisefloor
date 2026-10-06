import math
import random

import pytest

from noisefloor import stats


def test_retest_perfect_judge_has_zero_noise_and_icc_one():
    scores = {"a": [1, 1, 1], "b": [5, 5, 5], "c": [9, 9, 9]}
    r = stats.retest(scores)
    assert r.within_var == 0.0
    assert r.icc == 1.0
    assert r.min_detectable_delta == 0.0


def test_retest_pure_noise_judge_has_icc_near_zero():
    rng = random.Random(0)
    scores = {f"i{i}": [rng.gauss(5, 1) for _ in range(20)] for i in range(40)}
    r = stats.retest(scores)
    assert r.icc < 0.1
    assert abs(r.within_sd - 1.0) < 0.15


def test_retest_mixed_recovers_variance_split():
    rng = random.Random(1)
    # item signal SD 2, judge noise SD 1 → ICC ≈ 4/(4+1) = 0.8
    scores = {f"i{i}": [m + rng.gauss(0, 1) for _ in range(10)]
              for i, m in enumerate(rng.gauss(5, 2) for _ in range(200))}
    r = stats.retest(scores)
    assert 0.72 < r.icc < 0.88
    assert 0.9 < r.within_sd < 1.1


def test_min_detectable_delta_formula():
    scores = {"a": [1.0, 2.0], "b": [3.0, 4.0]}  # within var 0.5, n=2, k=2
    r = stats.retest(scores)
    assert r.within_var == pytest.approx(0.5)
    assert r.min_detectable_delta == pytest.approx(stats.Z95 * math.sqrt(2 * 0.5 / 4))


def test_flips_counts_instability():
    labels = {"a": ["accept"] * 5, "b": ["accept", "reject", "accept", "accept", "reject"], "c": ["reject"] * 5}
    f = stats.flips(labels)
    assert f.unstable_items == 1
    assert f.unstable_fraction == pytest.approx(1 / 3)
    # item b: pairs = 20, same = 3*2 + 2*1 = 8, disagreeing = 12; items a,c: 0 of 20 each
    assert f.pairwise_disagreement == pytest.approx(12 / 60)
    assert f.majority_agreement == pytest.approx((1 + 0.6 + 1) / 3)


def test_compare_inside_noise_when_shift_is_small():
    rng = random.Random(2)
    base = {f"i{i}": rng.uniform(3, 8) for i in range(30)}
    a = {k: [v + rng.gauss(0, 1) for _ in range(3)] for k, v in base.items()}
    b = {k: [v + 0.05 + rng.gauss(0, 1) for _ in range(3)] for k, v in base.items()}
    c = stats.compare(a, b, seed=0)
    assert c.inside_noise
    assert "INSIDE" in c.verdict or "ITEM-DEPENDENT" in c.verdict


def test_compare_clears_noise_when_shift_is_large():
    rng = random.Random(3)
    base = {f"i{i}": rng.uniform(3, 8) for i in range(30)}
    a = {k: [v + rng.gauss(0, 0.5) for _ in range(5)] for k, v in base.items()}
    b = {k: [v + 1.5 + rng.gauss(0, 0.5) for _ in range(5)] for k, v in base.items()}
    c = stats.compare(a, b, seed=0)
    assert not c.inside_noise
    assert c.delta < 0  # a − b
    assert abs(c.z_noise) > 5


def test_compare_drops_unpaired_items():
    a = {"x": [1, 2], "y": [3, 4], "only_a": [9]}
    b = {"x": [1, 2], "y": [3, 4], "only_b": [0]}
    c = stats.compare(a, b)
    assert c.n_items == 2
    assert c.delta == 0.0


def test_draws_needed_scales_inversely_with_delta_squared():
    k1 = stats.draws_needed(within_var=1.0, n_items=50, delta=0.2)
    k2 = stats.draws_needed(within_var=1.0, n_items=50, delta=0.1)
    assert 3.5 < k2 / k1 < 4.6


def test_empty_inputs_raise():
    with pytest.raises(ValueError):
        stats.retest({})
    with pytest.raises(ValueError):
        stats.flips({})
    with pytest.raises(ValueError):
        stats.compare({"a": [1]}, {"b": [1]})

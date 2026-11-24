"""Tests for the stacking core (pure numpy)."""
import numpy as np
from src.stacking import stack_pairs, parse_pair_dates

def test_recovers_known_velocity_and_reference_offsets():
    rng = np.random.default_rng(0)
    h, w, n = 40, 40, 16
    true = np.zeros((h, w)); true[10:20, 10:20] = -8.0
    years = np.array([(30 if i % 2 == 0 else 60) / 365.25 for i in range(n)])
    disp = (true[None] / 1000 * years[:, None, None]
            + rng.normal(0, 0.004, (n, 1, 1)) + rng.normal(0, 0.002, (n, h, w)) + 0.01)
    corr = np.clip(rng.normal(0.7, 0.1, (n, h, w)), 0, 1)
    result = stack_pairs(disp, corr, years, min_pairs=5)
    assert abs(np.nanmean(result["velocity_mm_yr"][10:20, 10:20]) + 8.0) < 1.5
    assert abs(np.nanmedian(result["velocity_mm_yr"][25:, 25:])) < 1.5

def test_low_coherence_pixels_are_masked():
    n = 8
    disp = np.ones((n, 5, 5)) * 0.001
    corr = np.full((n, 5, 5), 0.9); corr[:, 0, 0] = 0.1
    years = np.full(n, 0.1)
    result = stack_pairs(disp, corr, years, coh_threshold=0.35, min_pairs=5)
    assert np.isnan(result["velocity_mm_yr"][0, 0])

def test_parse_pair_dates():
    d1, d2 = parse_pair_dates("S1AA_20240701T053412_20240713T053413_VVP012_INT80_G_ueF_1A2B")
    assert (d1.year, d1.month, d1.day, d2.day) == (2024, 7, 1, 13)

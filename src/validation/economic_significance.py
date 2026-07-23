#!/usr/bin/env python3
"""
economic_significance.py — Phase 5 (Validation) of the VPIN project, Part 4
of the roadmap. Complements `volatility_control.py`'s statistical test with
the *economic* significance question the README's Phase 5 explicitly asks
for: "would a market maker who widened spreads on high VPIN have avoided
realized adverse-selection losses" -- tested here with the real captured
BTCUSDT trade tape, not a toy simulation.

--------------------------------------------------------------------------
The proxy (honest and simple, as the brief asks for)
--------------------------------------------------------------------------
A market maker posting quotes around the close of bucket tau is exposed to
the risk that price moves against a resting position over the buckets that
follow. A direct, symmetric (maker doesn't know direction in advance), real
proxy for that exposure is:

    forward_adverse_move_tau = | close_price[tau + h] - close_price[tau] |
                                / close_price[tau]         (in bps)

i.e. the realized magnitude of the price move over the next h buckets,
measured in basis points of the real BTCUSDT price at the time. If VPIN (or
the Part 3 ML classifier's predicted probability) is elevated at tau and a
maker who widened/pulled quotes in response would have faced systematically
*smaller* forward_adverse_move than one who didn't, that is genuine
economic evidence the signal is actionable, independent of the pure
statistical tests in `volatility_control.py`.

Two independent tests, both against real numbers from the actual capture:

1. **VPIN-based** (fully in-sample/descriptive -- VPIN itself is not
   "trained", so there is no train/test split issue here, only the
   walk-forward-computability of VPIN_tau itself, which is already
   guaranteed by construction -- see `vpin_estimator.py`): split all
   buckets into VPIN quartiles using the primary vpin_n50 series, compare
   mean/median forward_adverse_move in the top quartile ("would widen
   spreads") vs. the bottom quartile ("would not"), Welch t-test +
   Mann-Whitney U for the (skewed, small-sample) difference.
2. **ML-classifier-based** (genuinely out-of-sample): reuse
   `ml_toxicity_classifier.py`'s exact chronological 70/30 split and
   trained GradientBoostingClassifier, take its predicted P(toxic) on the
   held-out *test* rows only, split those test rows by predicted
   probability (median split, since the test slice is small), and run the
   same comparison restricted to that genuinely-unseen-by-the-model slice.

A stylized (explicitly labeled as such) "bps and USD avoided" figure is
also reported, using the real average bucket notional (bucket volume in
BTC times the real captured BTCUSDT price) from this capture -- illustrative
of what the effect size means in dollar terms, not a claim of a backtested
strategy P&L.

Usage:
    python src/validation/economic_significance.py \
        --in data/processed/btcusdt_vpin_part3.csv \
        --in data/processed/btcusdt_vpin_part3_nb400.csv \
        --horizon 5 --vpin-col vpin_n50
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "model"))
from ml_toxicity_classifier import build_features, build_label, evaluate_gbc  # noqa: E402


# ---------------------------------------------------------------------------
# Forward adverse-move construction
# ---------------------------------------------------------------------------


def build_forward_adverse_move(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    out = df.copy()
    fwd_price = out["close_price"].shift(-horizon)
    out["forward_adverse_move_bps"] = (
        (fwd_price - out["close_price"]).abs() / out["close_price"] * 1e4
    )
    return out


# ---------------------------------------------------------------------------
# Group comparison helper
# ---------------------------------------------------------------------------


def compare_groups(high: pd.Series, low: pd.Series) -> dict:
    t_stat, t_p = stats.ttest_ind(high, low, equal_var=False)
    u_stat, u_p = stats.mannwhitneyu(high, low, alternative="two-sided")
    return {
        "n_high": len(high),
        "n_low": len(low),
        "mean_high_bps": float(high.mean()),
        "mean_low_bps": float(low.mean()),
        "median_high_bps": float(high.median()),
        "median_low_bps": float(low.median()),
        "mean_diff_bps": float(high.mean() - low.mean()),
        "pct_diff": float((high.mean() - low.mean()) / low.mean() * 100) if low.mean() != 0 else float("nan"),
        "welch_t": float(t_stat),
        "welch_p": float(t_p),
        "mannwhitney_u": float(u_stat),
        "mannwhitney_p": float(u_p),
    }


# ---------------------------------------------------------------------------
# Test 1: VPIN-based (full sample, descriptive)
# ---------------------------------------------------------------------------


def vpin_based_test(df: pd.DataFrame, vpin_col: str, horizon: int, quartile: float = 0.25) -> dict:
    clean = df.dropna(subset=[vpin_col, "forward_adverse_move_bps"]).copy()
    lo_thresh = clean[vpin_col].quantile(quartile)
    hi_thresh = clean[vpin_col].quantile(1 - quartile)

    high_group = clean.loc[clean[vpin_col] >= hi_thresh, "forward_adverse_move_bps"]
    low_group = clean.loc[clean[vpin_col] <= lo_thresh, "forward_adverse_move_bps"]

    result = compare_groups(high_group, low_group)
    result["n_clean"] = len(clean)
    result["vpin_col"] = vpin_col
    result["hi_thresh"] = float(hi_thresh)
    result["lo_thresh"] = float(lo_thresh)
    return result


# ---------------------------------------------------------------------------
# Test 2: ML-classifier-based (genuinely out-of-sample)
# ---------------------------------------------------------------------------


def ml_based_test(
    df: pd.DataFrame,
    vpin_col: str,
    trail_window: int,
    fwd_window: int,
    toxic_multiplier: float,
    test_frac: float,
    horizon: int,
) -> dict | None:
    """Retrain the exact Part 3 GBC pipeline (same label/features/split),
    then evaluate forward_adverse_move_bps split by the model's predicted
    probability on the held-out test rows only -- a genuinely out-of-sample
    use of the classifier, distinct from the AUC/accuracy metrics Part 3
    already reported (those used the volatility LABEL as ground truth; this
    uses the real economic proxy instead).
    """
    labeled = build_label(df, trail_window, fwd_window, toxic_multiplier)
    featured, feature_cols = build_features(labeled)

    needed = feature_cols + [vpin_col, "label", "forward_adverse_move_bps"]
    featured[needed] = featured[needed].replace([np.inf, -np.inf], np.nan)
    clean = featured.dropna(subset=needed).reset_index(drop=True)

    n = len(clean)
    if n < 20:
        return None

    split_idx = int(n * (1 - test_frac))
    train, test = clean.iloc[:split_idx], clean.iloc[split_idx:]
    if len(test) < 10:
        return None

    X_train, X_test = train[feature_cols], test[feature_cols]
    y_train, y_test = train["label"].astype(int), test["label"].astype(int)

    gbc_result = evaluate_gbc(X_train, X_test, y_train, y_test)
    clf = gbc_result["model"]
    test_proba = pd.Series(clf.predict_proba(X_test)[:, 1], index=test.index)

    median_proba = test_proba.median()
    high_mask = test_proba >= median_proba
    low_mask = ~high_mask

    high_group = test.loc[high_mask, "forward_adverse_move_bps"]
    low_group = test.loc[low_mask, "forward_adverse_move_bps"]
    if len(high_group) < 3 or len(low_group) < 3:
        return None

    result = compare_groups(high_group, low_group)
    result["n_test"] = len(test)
    result["median_predicted_proba"] = float(median_proba)
    result["test_auc_on_volatility_label"] = gbc_result["auc"]
    return result


# ---------------------------------------------------------------------------
# Stylized bps/USD "avoided loss" translation
# ---------------------------------------------------------------------------


def stylized_avoided_loss(df: pd.DataFrame, vpin_test: dict) -> dict:
    """Illustrative only: NOT a backtested strategy P&L. Uses the real
    average bucket notional (bucket volume in BTC x real captured price)
    from this capture to translate the bps-difference finding into a
    dollar-scale intuition -- how much notional exposure sits in the
    "would-have-widened" quartile of buckets, and what the mean adverse-move
    bps difference implies for that notional if realized on every such
    bucket.
    """
    avg_bucket_volume_btc = float(df["volume"].mean())
    avg_price = float(df["close_price"].mean())
    avg_bucket_notional_usd = avg_bucket_volume_btc * avg_price

    n_high_buckets = vpin_test["n_high"]
    mean_diff_bps = vpin_test["mean_diff_bps"]

    total_notional_in_high_quartile = avg_bucket_notional_usd * n_high_buckets
    stylized_usd_at_risk_difference = total_notional_in_high_quartile * (mean_diff_bps / 1e4)

    return {
        "avg_bucket_volume_btc": avg_bucket_volume_btc,
        "avg_price_usd": avg_price,
        "avg_bucket_notional_usd": avg_bucket_notional_usd,
        "n_high_vpin_buckets": n_high_buckets,
        "total_notional_in_high_quartile_usd": total_notional_in_high_quartile,
        "mean_diff_bps": mean_diff_bps,
        "stylized_usd_exposure_difference": stylized_usd_at_risk_difference,
    }


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_one(
    in_path: Path,
    vpin_col: str,
    horizon: int,
    trail_window: int,
    fwd_window: int,
    toxic_multiplier: float,
    test_frac: float,
) -> None:
    df = pd.read_csv(in_path)
    df = build_forward_adverse_move(df, horizon)

    print(f"########## {in_path.name}  (vpin_col={vpin_col}, horizon={horizon} buckets) ##########")
    print()

    # --- Test 1: VPIN-based -------------------------------------------
    vpin_result = vpin_based_test(df, vpin_col, horizon)
    print("--- Test 1: VPIN-based (top vs. bottom quartile, full sample) ---")
    print(
        f"  n_high={vpin_result['n_high']} (VPIN>={vpin_result['hi_thresh']:.4f})   "
        f"n_low={vpin_result['n_low']} (VPIN<={vpin_result['lo_thresh']:.4f})   "
        f"of {vpin_result['n_clean']} clean buckets"
    )
    print(
        f"  Forward {horizon}-bucket adverse move: high-VPIN mean={vpin_result['mean_high_bps']:.3f} bps "
        f"(median={vpin_result['median_high_bps']:.3f})   "
        f"low-VPIN mean={vpin_result['mean_low_bps']:.3f} bps (median={vpin_result['median_low_bps']:.3f})"
    )
    print(
        f"  Difference: {vpin_result['mean_diff_bps']:+.3f} bps ({vpin_result['pct_diff']:+.1f}%)   "
        f"Welch t-test p={vpin_result['welch_p']:.4f}   Mann-Whitney U p={vpin_result['mannwhitney_p']:.4f}"
    )
    verdict1 = (
        "high-VPIN buckets DID see significantly larger adverse moves (signal is economically actionable)"
        if vpin_result["mean_diff_bps"] > 0 and vpin_result["welch_p"] < 0.05
        else "no significant difference (or wrong sign) -- signal not clearly economically actionable here"
    )
    print(f"  Verdict: {verdict1}")
    print()

    stylized = stylized_avoided_loss(df, vpin_result)
    print("  Stylized bps->USD translation (illustrative only, NOT a backtested strategy P&L):")
    print(
        f"    avg bucket volume={stylized['avg_bucket_volume_btc']:.6f} BTC   "
        f"avg price=${stylized['avg_price_usd']:,.2f}   "
        f"avg bucket notional=${stylized['avg_bucket_notional_usd']:,.2f}"
    )
    print(
        f"    {stylized['n_high_vpin_buckets']} high-VPIN buckets represent "
        f"${stylized['total_notional_in_high_quartile_usd']:,.2f} of notional; "
        f"at a {stylized['mean_diff_bps']:+.3f} bps adverse-move difference this implies "
        f"${stylized['stylized_usd_exposure_difference']:,.2f} of illustrative extra exposure "
        f"if that difference were fully realized as loss on every high-VPIN bucket."
    )
    print()

    # --- Test 2: ML-classifier-based -----------------------------------
    ml_result = ml_based_test(df, vpin_col, trail_window, fwd_window, toxic_multiplier, test_frac, horizon)
    print("--- Test 2: ML-classifier-based (genuinely OOS: held-out test rows only) ---")
    if ml_result is None:
        print("  SKIPPED: not enough held-out test rows for this capture/window configuration.")
    else:
        print(
            f"  n_test={ml_result['n_test']} (median predicted P(toxic)={ml_result['median_predicted_proba']:.4f}, "
            f"test-set AUC on volatility label={ml_result['test_auc_on_volatility_label']:.4f})"
        )
        print(
            f"  Forward {horizon}-bucket adverse move: high-predicted-prob mean={ml_result['mean_high_bps']:.3f} bps  "
            f"low-predicted-prob mean={ml_result['mean_low_bps']:.3f} bps"
        )
        print(
            f"  Difference: {ml_result['mean_diff_bps']:+.3f} bps ({ml_result['pct_diff']:+.1f}%)   "
            f"Welch t-test p={ml_result['welch_p']:.4f}   Mann-Whitney U p={ml_result['mannwhitney_p']:.4f}"
        )
        verdict2 = (
            "classifier's OOS probability IS economically informative for adverse-move risk"
            if ml_result["mean_diff_bps"] > 0 and ml_result["welch_p"] < 0.05
            else "classifier's OOS probability is NOT clearly economically informative here"
        )
        print(f"  Verdict: {verdict2}")
    print()
    print()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Economic significance test: would widening spreads on elevated VPIN / "
        "elevated ML-predicted toxicity probability have avoided realized adverse price moves?"
    )
    p.add_argument("--in", dest="in_paths", type=Path, action="append", required=True, help="CSV(s) from vpin_estimator.py.")
    p.add_argument("--vpin-col", default="vpin_n50", help="VPIN column to test (default: vpin_n50).")
    p.add_argument("--horizon", type=int, default=5, help="Forward buckets over which to measure the adverse move (default: 5).")
    p.add_argument("--trail-window", type=int, default=10, help="Same as ml_toxicity_classifier.py (default: 10).")
    p.add_argument("--fwd-window", type=int, default=5, help="Same as ml_toxicity_classifier.py (default: 5).")
    p.add_argument("--toxic-multiplier", type=float, default=1.0, help="Same as ml_toxicity_classifier.py (default: 1.0).")
    p.add_argument("--test-frac", type=float, default=0.3, help="Same as ml_toxicity_classifier.py (default: 0.3).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    for in_path in args.in_paths:
        run_one(
            in_path,
            args.vpin_col,
            args.horizon,
            args.trail_window,
            args.fwd_window,
            args.toxic_multiplier,
            args.test_frac,
        )


if __name__ == "__main__":
    main()

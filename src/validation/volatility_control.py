#!/usr/bin/env python3
"""
volatility_control.py — Phase 5 (Validation) of the VPIN project, Part 4 of
the roadmap. Implements CHEATSHEET.md's central critique test directly
against this project's own data, following Andersen & Bondarenko's (2014,
2015) own methodology (see `research/CHEATSHEET.md` "Critical literature"
and `research/DERIVATION.md`'s "Where the Andersen-Bondarenko critique
enters" section):

    Does VPIN have genuine incremental predictive power for future realized
    volatility, once *contemporaneous/trailing* realized volatility is
    already controlled for -- or does the apparent VPIN <-> volatility
    relationship (see the correlation numbers vpin_estimator.py prints)
    just reflect the mechanical fact that both VPIN and future volatility
    move with the same underlying volatility regime?

--------------------------------------------------------------------------
Method
--------------------------------------------------------------------------
For each bucket tau, define:

    trailing_vol_short_tau = std(delta_p) over buckets [tau-4, tau]      (5-bucket)
    trailing_vol_long_tau  = std(delta_p) over buckets [tau-19, tau]     (20-bucket)
    forward_vol_tau        = std(delta_p) over buckets [tau+1, tau+fwd_window]

Two nested forecasting models for forward_vol_tau:

    Model A (volatility only):       forward_vol ~ 1 + trailing_vol_short + trailing_vol_long
    Model B (volatility + VPIN):     forward_vol ~ 1 + trailing_vol_short + trailing_vol_long + vpin_n<window>

This is exactly Andersen & Bondarenko's own test design applied to this
dataset: if VPIN is just riding the same volatility regime as
trailing_vol, its coefficient in Model B should be small/insignificant and
Model B should not out-of-sample-forecast better than Model A. If VPIN
carries genuine incremental information, Model B should meaningfully beat
Model A out-of-sample.

Two complementary comparisons are reported, both walk-forward / no-lookahead:

1. **True walk-forward one-step-ahead OOS test.** Starting after a minimum
   training size, at each step t: fit Model A and Model B using only data
   up to t-1 (expanding window, refit every step), forecast bucket t, move
   on. This is the strict "no lookahead" methodology the roadmap calls for.
   Report each model's out-of-sample R^2 against a naive walk-forward
   "expanding historical mean of forward_vol" benchmark (Campbell-Thompson
   style: R^2_oos = 1 - SSE_model / SSE_naive), plus the incremental
   R^2 of B over A (1 - SSE_B / SSE_A).
2. **In-sample nested F-test on the training block only** (the classical
   Andersen-Bondarenko-style significance check): fit both models once on
   the chronological training slice (matches the 70/30 split convention
   used in `ml_toxicity_classifier.py`), run an F-test for whether adding
   VPIN significantly improves the fit.

Run across all three VPIN windows (n=20, 50, 100) and both bucket-count
captures (250-bucket and 400-bucket) available from Part 3, for robustness
-- a single run on a single configuration is exactly the kind of
cherry-picking this validation phase is supposed to guard against.

Usage:
    python src/validation/volatility_control.py \
        --in data/processed/btcusdt_vpin_part3.csv \
        --in data/processed/btcusdt_vpin_part3_nb400.csv \
        --fwd-window 5 --min-train-frac 0.6 --test-frac 0.3
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


# ---------------------------------------------------------------------------
# Feature / target construction (lookahead-free on the trailing side)
# ---------------------------------------------------------------------------


def build_vol_frame(df: pd.DataFrame, fwd_window: int) -> pd.DataFrame:
    """Add trailing_vol_short/long and forward_vol columns.

    trailing_vol_* uses only buckets up to and including tau (available in
    real time when bucket tau closes). forward_vol_tau uses buckets strictly
    after tau -- this is the target being forecast, not a feature.
    """
    out = df.copy()
    delta_p = out["delta_p"]

    out["trailing_vol_short"] = delta_p.rolling(window=5, min_periods=5).std()
    out["trailing_vol_long"] = delta_p.rolling(window=20, min_periods=20).std()

    out["forward_vol"] = (
        delta_p.shift(-1)
        .rolling(window=fwd_window, min_periods=fwd_window)
        .std()
        .shift(-(fwd_window - 1))
    )
    return out


# ---------------------------------------------------------------------------
# Walk-forward one-step-ahead OOS test
# ---------------------------------------------------------------------------


def walk_forward_forecasts(
    df: pd.DataFrame, y_col: str, x_cols: list[str], min_train: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Expanding-window, refit-every-step, one-step-ahead OOS forecasts.

    At step t (t = min_train .. n-1), fit OLS on rows [0, t) only, forecast
    row t. Strictly no lookahead: row t's own y/X are never used to fit the
    model that predicts row t. Returns (actuals, model_preds, naive_preds)
    where naive_preds[t] is the expanding historical mean of y over
    [0, t) -- the walk-forward "no-information" benchmark forecast.
    """
    n = len(df)
    actuals, preds, naive = [], [], []
    y = df[y_col].to_numpy()
    X = df[x_cols].to_numpy()

    for t in range(min_train, n):
        y_train = y[:t]
        X_train = sm.add_constant(X[:t], has_constant="add")
        model = sm.OLS(y_train, X_train).fit()

        # add_constant on a single row can't reliably detect which column is
        # the constant -- build the design row explicitly instead.
        x_t = np.concatenate([[1.0], X[t]]).reshape(1, -1)

        pred_t = float(model.predict(x_t)[0])
        preds.append(pred_t)
        actuals.append(y[t])
        naive.append(float(np.mean(y_train)))

    return np.array(actuals), np.array(preds), np.array(naive)


def oos_r2(actual: np.ndarray, pred: np.ndarray, benchmark: np.ndarray) -> float:
    sse_model = float(np.sum((actual - pred) ** 2))
    sse_bench = float(np.sum((actual - benchmark) ** 2))
    if sse_bench == 0:
        return float("nan")
    return 1.0 - sse_model / sse_bench


# ---------------------------------------------------------------------------
# In-sample nested F-test on the training block
# ---------------------------------------------------------------------------


def nested_f_test(
    train: pd.DataFrame, y_col: str, x_cols_restricted: list[str], x_cols_full: list[str]
) -> dict:
    y = train[y_col]
    X_r = sm.add_constant(train[x_cols_restricted])
    X_f = sm.add_constant(train[x_cols_full])

    model_r = sm.OLS(y, X_r).fit()
    model_f = sm.OLS(y, X_f).fit()

    f_test = model_f.compare_f_test(model_r)
    fvalue, pvalue, df_diff = f_test

    vpin_var = [c for c in x_cols_full if c not in x_cols_restricted][0]
    return {
        "r2_restricted": model_r.rsquared,
        "r2_full": model_f.rsquared,
        "delta_r2": model_f.rsquared - model_r.rsquared,
        "f_stat": float(fvalue),
        "p_value": float(pvalue),
        "vpin_coef": float(model_f.params[vpin_var]),
        "vpin_coef_pvalue": float(model_f.pvalues[vpin_var]),
        "vpin_var": vpin_var,
    }


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_one(
    in_path: Path, vpin_col: str, fwd_window: int, min_train_frac: float, test_frac: float
) -> dict:
    df = pd.read_csv(in_path)
    df = build_vol_frame(df, fwd_window)

    needed = ["trailing_vol_short", "trailing_vol_long", "forward_vol", vpin_col]
    df[needed] = df[needed].replace([np.inf, -np.inf], np.nan)
    clean = df.dropna(subset=needed).reset_index(drop=True)

    n = len(clean)
    min_train = max(30, int(n * min_train_frac))
    if min_train >= n - 5:
        raise ValueError(
            f"Not enough clean rows ({n}) for min_train_frac={min_train_frac} "
            "-- shrink min_train_frac or capture more data."
        )

    x_cols_a = ["trailing_vol_short", "trailing_vol_long"]
    x_cols_b = x_cols_a + [vpin_col]

    # --- 1. Walk-forward one-step-ahead OOS test -----------------------
    actual_a, pred_a, naive_a = walk_forward_forecasts(clean, "forward_vol", x_cols_a, min_train)
    actual_b, pred_b, naive_b = walk_forward_forecasts(clean, "forward_vol", x_cols_b, min_train)
    assert np.array_equal(actual_a, actual_b)

    r2_oos_a = oos_r2(actual_a, pred_a, naive_a)
    r2_oos_b = oos_r2(actual_b, pred_b, naive_b)
    sse_a = float(np.sum((actual_a - pred_a) ** 2))
    sse_b = float(np.sum((actual_b - pred_b) ** 2))
    incremental_r2_oos = 1.0 - sse_b / sse_a if sse_a > 0 else float("nan")

    # --- 2. In-sample nested F-test on the chronological train block ---
    split_idx = int(n * (1 - test_frac))
    train = clean.iloc[:split_idx]
    f_test_result = nested_f_test(train, "forward_vol", x_cols_a, x_cols_b)

    return {
        "in_path": str(in_path),
        "vpin_col": vpin_col,
        "n_clean": n,
        "n_oos_steps": len(actual_a),
        "r2_oos_vol_only": r2_oos_a,
        "r2_oos_vol_plus_vpin": r2_oos_b,
        "incremental_r2_oos": incremental_r2_oos,
        "f_test": f_test_result,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Andersen-Bondarenko-style test: does VPIN add incremental "
        "out-of-sample forecasting power for forward realized volatility, "
        "over trailing realized volatility alone?"
    )
    p.add_argument(
        "--in",
        dest="in_paths",
        type=Path,
        action="append",
        required=True,
        help="CSV(s) from vpin_estimator.py (repeat --in for multiple captures).",
    )
    p.add_argument(
        "--vpin-cols",
        nargs="+",
        default=["vpin_n20", "vpin_n50", "vpin_n100"],
        help="VPIN columns to test (default: vpin_n20 vpin_n50 vpin_n100).",
    )
    p.add_argument("--fwd-window", type=int, default=5, help="Forward buckets for realized-vol target (default: 5).")
    p.add_argument(
        "--min-train-frac",
        type=float,
        default=0.6,
        help="Fraction of clean rows used as the minimum walk-forward training window (default: 0.6).",
    )
    p.add_argument(
        "--test-frac",
        type=float,
        default=0.3,
        help="Fraction of clean rows held out for the in-sample nested F-test's train block "
        "(matches ml_toxicity_classifier.py's convention; default: 0.3).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("data/processed/validation_volatility_control.csv"),
        help="Where to write the summary results table.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rows = []
    for in_path in args.in_paths:
        for vpin_col in args.vpin_cols:
            try:
                result = run_one(in_path, vpin_col, args.fwd_window, args.min_train_frac, args.test_frac)
            except ValueError as e:
                print(f"SKIP {in_path.name} / {vpin_col}: {e}")
                continue

            f = result["f_test"]
            rows.append(
                {
                    "capture": in_path.name,
                    "vpin_col": vpin_col,
                    "n_clean": result["n_clean"],
                    "n_oos_steps": result["n_oos_steps"],
                    "oos_r2_vol_only": result["r2_oos_vol_only"],
                    "oos_r2_vol_plus_vpin": result["r2_oos_vol_plus_vpin"],
                    "incremental_oos_r2": result["incremental_r2_oos"],
                    "insample_r2_vol_only": f["r2_restricted"],
                    "insample_r2_vol_plus_vpin": f["r2_full"],
                    "insample_delta_r2": f["delta_r2"],
                    "f_stat": f["f_stat"],
                    "f_pvalue": f["p_value"],
                    "vpin_coef": f["vpin_coef"],
                    "vpin_coef_pvalue": f["vpin_coef_pvalue"],
                }
            )

            print(f"=== {in_path.name}  |  {vpin_col} ===")
            print(f"  clean rows: {result['n_clean']}   walk-forward OOS steps: {result['n_oos_steps']}")
            print(
                f"  Walk-forward OOS R^2 (vs. expanding-mean naive benchmark): "
                f"vol-only={result['r2_oos_vol_only']:+.4f}   "
                f"vol+VPIN={result['r2_oos_vol_plus_vpin']:+.4f}   "
                f"incremental(B over A)={result['incremental_r2_oos']:+.4f}"
            )
            print(
                f"  In-sample (train block) R^2: vol-only={f['r2_restricted']:.4f}   "
                f"vol+VPIN={f['r2_full']:.4f}   delta={f['delta_r2']:+.4f}"
            )
            print(
                f"  Nested F-test (H0: VPIN coef = 0): F={f['f_stat']:.4f}  p={f['p_value']:.4f}   "
                f"VPIN coef={f['vpin_coef']:+.6f} (p={f['vpin_coef_pvalue']:.4f})"
            )
            verdict = (
                "SURVIVES control (significant, p<0.05, and OOS improves)"
                if f["p_value"] < 0.05 and result["incremental_r2_oos"] > 0
                else "DOES NOT clearly survive control (Andersen-Bondarenko-consistent null)"
            )
            print(f"  Verdict: {verdict}")
            print()

    if rows:
        out_df = pd.DataFrame(rows)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(args.out, index=False)
        print(f"Wrote summary table ({len(out_df)} rows) -> {args.out}")

        n_survive = int(((out_df["f_pvalue"] < 0.05) & (out_df["incremental_oos_r2"] > 0)).sum())
        print()
        print(
            f"Overall: VPIN's incremental contribution is statistically significant (p<0.05) "
            f"AND improves walk-forward OOS fit in {n_survive}/{len(out_df)} (capture, window) "
            f"configurations tested."
        )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
vpin_estimator.py — Phase 4 (VPIN estimation) of the VPIN project.

Picks up exactly where `src/features/volume_clock.py` (Phase 3) leaves off:
that module produces a bucketed dataset with one row per fixed-volume
bucket, including the per-bucket order-imbalance column `oi`
(`OI_tau = |V_tau^Buy - V_tau^Sell| / V_tau`, bounded in [0, 1]).

This module implements Part 3 of `research/DERIVATION.md`: VPIN is the
rolling mean of OI_tau over a trailing window of `n` buckets:

    VPIN_tau = (1/n) * sum_{i=tau-n+1}^{tau} OI_i

Rolling mean uses only buckets up to and including tau (a trailing,
lookahead-free window), so VPIN_tau is a real-time-computable quantity
that only needs the last n completed buckets. The paper's own baseline
default is n=50 buckets; we also compute at least one alternative window
as a quick sensitivity check (Song/Wu/Simon 2014/2015, CHEATSHEET.md
"Follow-ups" section, flag window length as a parameter worth stress
testing rather than trusting blindly).

Also runs a first-pass, non-rigorous sanity check: does VPIN visibly rise
around the buckets with the largest realized |ΔP| price moves in the
capture? This is an eyeball check only, not a statistical claim of
predictive power (that rigorous walk-forward test is Phase 5 / Part 4 of
the roadmap, not here).

Usage:
    python src/model/vpin_estimator.py \
        --in data/processed/btcusdt_buckets_part3.csv \
        --out data/processed/btcusdt_vpin_part3.csv \
        --windows 50 20 100
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core VPIN computation
# ---------------------------------------------------------------------------


def compute_vpin(buckets: pd.DataFrame, window: int) -> pd.Series:
    """Rolling-mean VPIN over a trailing window of `window` buckets.

    Trailing (not centered) rolling mean of `oi`, using only the current
    bucket and buckets before it — this is the real-time-computable
    definition (at the moment bucket tau closes, VPIN_tau only needs
    buckets tau-window+1 .. tau, all already observed).
    """
    if window <= 0:
        raise ValueError("window must be positive")
    return buckets["oi"].rolling(window=window, min_periods=window).mean()


def add_vpin_columns(buckets: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    out = buckets.copy()
    for n in windows:
        out[f"vpin_n{n}"] = compute_vpin(out, n)
    return out


# ---------------------------------------------------------------------------
# Sanity check: VPIN vs largest realized price moves
# ---------------------------------------------------------------------------


def largest_move_sanity_check(
    df: pd.DataFrame, vpin_col: str, top_k: int = 5
) -> pd.DataFrame:
    """For the top_k buckets with the largest |delta_p|, report the VPIN
    value at that bucket and its percentile within the full VPIN series.

    This is a first-pass eyeball check (does VPIN tend to be elevated
    around the biggest realized price moves in the capture?), not a
    rigorous predictive-power test — see module docstring.
    """
    valid = df.dropna(subset=[vpin_col]).copy()
    valid["abs_delta_p"] = valid["delta_p"].abs()
    vpin_rank = valid[vpin_col].rank(pct=True)

    top_moves = valid.reindex(valid["abs_delta_p"].nlargest(top_k).index)
    top_moves = top_moves.assign(vpin_percentile=vpin_rank.reindex(top_moves.index))
    return top_moves[
        ["bucket_id", "close_price", "delta_p", "abs_delta_p", vpin_col, "vpin_percentile"]
    ]


def vpin_correlation_with_volatility(df: pd.DataFrame, vpin_col: str, vol_window: int = 5) -> float:
    """Correlation between VPIN_tau and trailing realized volatility
    (rolling std of delta_p over the same window), as a second, cheap
    sanity metric alongside the top-move eyeball check.
    """
    valid = df.dropna(subset=[vpin_col]).copy()
    realized_vol = valid["delta_p"].rolling(window=vol_window, min_periods=vol_window).std()
    both = pd.concat([valid[vpin_col], realized_vol], axis=1).dropna()
    if len(both) < 2:
        return float("nan")
    return float(both.iloc[:, 0].corr(both.iloc[:, 1]))


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run(in_path: Path, out_path: Path, windows: list[int]) -> pd.DataFrame:
    buckets = pd.read_csv(in_path)
    result = add_vpin_columns(buckets, windows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    return result


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute rolling VPIN (trailing mean of OI_tau) over one or more window lengths."
    )
    p.add_argument("--in", dest="in_path", type=Path, required=True, help="Bucketed CSV from volume_clock.py.")
    p.add_argument(
        "--out",
        dest="out_path",
        type=Path,
        default=Path("data/processed/vpin.csv"),
        help="Output CSV path (bucket data + vpin_n<window> columns).",
    )
    p.add_argument(
        "--windows",
        type=int,
        nargs="+",
        default=[50, 20],
        help="Trailing window lengths (in buckets) to compute VPIN over (default: 50 20). "
        "First value is treated as the primary/paper-default window for the sanity check print.",
    )
    p.add_argument("--top-k", type=int, default=5, help="Number of largest |delta_p| moves to report (default: 5).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result = run(args.in_path, args.out_path, args.windows)
    n_buckets = len(result)

    print(f"Loaded {n_buckets} buckets from {args.in_path}")
    print(f"Wrote VPIN series -> {args.out_path}")
    print()

    print("VPIN summary stats by window:")
    for n in args.windows:
        col = f"vpin_n{n}"
        series = result[col].dropna()
        n_valid = len(series)
        print(
            f"  n={n:>4}  valid_obs={n_valid:>4}  mean={series.mean():.4f}  "
            f"std={series.std():.4f}  min={series.min():.4f}  "
            f"p50={series.median():.4f}  p90={series.quantile(0.9):.4f}  max={series.max():.4f}"
        )
    print()

    primary_col = f"vpin_n{args.windows[0]}"
    print(f"Sensitivity check: correlation between window choices' VPIN series (pairwise, on overlapping obs):")
    valid_cols = [f"vpin_n{n}" for n in args.windows]
    corr_mat = result[valid_cols].corr()
    with pd.option_context("display.width", 200):
        print(corr_mat.round(4).to_string())
    print()

    print(f"Sanity check (primary window n={args.windows[0]}): top {args.top_k} largest |delta_p| moves vs VPIN_{args.windows[0]} percentile")
    top_moves = largest_move_sanity_check(result, primary_col, top_k=args.top_k)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(top_moves.to_string(index=False))
    print()

    corr = vpin_correlation_with_volatility(result, primary_col, vol_window=5)
    print(f"Corr(VPIN_{args.windows[0]}, trailing 5-bucket realized vol of delta_p) = {corr:.4f}")


if __name__ == "__main__":
    main()

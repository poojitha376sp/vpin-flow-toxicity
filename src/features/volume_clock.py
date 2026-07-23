#!/usr/bin/env python3
"""
volume_clock.py — Phase 3 (Volume clock + bucketing) of the VPIN project.

Implements exactly the two mechanisms derived in `research/DERIVATION.md`
Parts 1-2, and stops there (Part 3 of the derivation — averaging OI_tau into
the rolling VPIN estimator — is Phase 4 / a later session, NOT done here):

1. Fixed-volume bucket construction ("the volume clock"): partition the raw
   trade tape into buckets that each contain a fixed total volume V, instead
   of a fixed wall-clock window. A trade that would push a bucket over V is
   split across the bucket boundary so every bucket's volume is exactly V
   (except possibly the final, partial bucket, which is dropped).

2. Bulk Volume Classification (BVC): for each bucket, standardize the
   bucket's price change by a rolling (lookahead-free) estimate of the
   bucket-to-bucket price-change volatility, and use the standard normal CDF
   to split the bucket's volume into a buy-initiated and sell-initiated
   share:

       z_tau        = DeltaP_tau / sigma_DeltaP
       V_tau^Buy    = V_tau * Phi(z_tau)
       V_tau^Sell   = V_tau - V_tau^Buy
       OI_tau       = |V_tau^Buy - V_tau^Sell| / V_tau

No per-trade tick-rule classification is used anywhere in this module, by
design (see DERIVATION.md Part 2).

Usage:
    python src/features/volume_clock.py \
        --in data/raw/btcusdt_trades_part2.ndjson \
        --out data/processed/btcusdt_buckets.csv \
        --n-buckets 50 \
        --sigma-window 20
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm


# ---------------------------------------------------------------------------
# Loading raw trade prints
# ---------------------------------------------------------------------------


def load_trades(path: Path) -> pd.DataFrame:
    """Load newline-delimited JSON trade prints written by collect_trades.py.

    Only price, quantity, and trade_time_ms are needed for volume-clock
    bucketing (see data/README.md); everything else is dropped here.
    """
    records = []
    with path.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            records.append(
                {
                    "trade_time_ms": rec["trade_time_ms"],
                    "price": float(rec["price"]),
                    "quantity": float(rec["quantity"]),
                }
            )
    if not records:
        raise ValueError(f"No trade records found in {path}")

    df = pd.DataFrame.from_records(records)
    # Trades should already arrive time-ordered off the websocket, but sort
    # defensively (recv jitter / reconnects could reorder trade_time_ms
    # slightly) — the volume clock construction requires time order.
    df = df.sort_values("trade_time_ms", kind="mergesort").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Step 1: fixed-volume bucket construction (the volume clock)
# ---------------------------------------------------------------------------


def build_volume_buckets(trades: pd.DataFrame, bucket_volume: float) -> pd.DataFrame:
    """Partition a time-ordered trade tape into fixed-volume buckets.

    Each bucket tau accumulates trades until its cumulative volume reaches
    `bucket_volume`. A trade that would push the running total past
    `bucket_volume` is split: the portion needed to exactly fill the current
    bucket is counted in it, and the remainder rolls into the next bucket
    (same trade price on both sides of the split — a single print has one
    price). This keeps every completed bucket's volume exactly equal to
    `bucket_volume` by construction, which is what the volume-clock argument
    in DERIVATION.md Part 1 requires (each observation carries "comparable
    informational weight").

    The final, partially-filled bucket (if the trade tape doesn't divide
    evenly into `bucket_volume`) is dropped rather than kept short, so every
    row in the output has the same V_tau.

    Returns a DataFrame with one row per completed bucket:
        bucket_id, start_time_ms, end_time_ms, volume, close_price,
        n_trades (number of raw trades that contributed to this bucket,
        counting a split trade in both buckets it touches).
    """
    if bucket_volume <= 0:
        raise ValueError("bucket_volume must be positive")

    buckets = []
    bucket_id = 0
    acc_volume = 0.0
    start_time = None
    last_price = None
    end_time = None
    n_trades = 0

    for row in trades.itertuples(index=False):
        t_ms, price, qty = row.trade_time_ms, row.price, row.quantity
        if start_time is None:
            start_time = t_ms
        remaining_qty = qty

        while remaining_qty > 0:
            space_left = bucket_volume - acc_volume
            take = min(space_left, remaining_qty)

            acc_volume += take
            remaining_qty -= take
            last_price = price  # last price touched in this bucket so far
            end_time = t_ms
            n_trades += 1 if take == qty or take > 0 else 0

            if acc_volume >= bucket_volume - 1e-12:
                # bucket is full -> close it
                buckets.append(
                    {
                        "bucket_id": bucket_id,
                        "start_time_ms": start_time,
                        "end_time_ms": end_time,
                        "volume": acc_volume,
                        "close_price": last_price,
                        "n_trades": n_trades,
                    }
                )
                bucket_id += 1
                acc_volume = 0.0
                n_trades = 0
                start_time = t_ms if remaining_qty > 0 else None

    # NOTE: any leftover partial bucket (acc_volume > 0 at the end of the
    # tape) is intentionally dropped — see docstring.

    return pd.DataFrame(buckets)


# ---------------------------------------------------------------------------
# Step 2: Bulk Volume Classification (BVC)
# ---------------------------------------------------------------------------


def apply_bvc(buckets: pd.DataFrame, sigma_window: int = 20, min_sigma_periods: int = 2) -> pd.DataFrame:
    """Apply Bulk Volume Classification to a bucketed trade tape.

    Adds columns: delta_p, sigma_delta_p, z, buy_volume, sell_volume, oi.

    sigma_delta_p (the standardizing volatility, sigma_DeltaP in
    DERIVATION.md Part 2) is a *trailing* rolling std of DeltaP computed from
    buckets strictly before tau (shift(1) before rolling) — this avoids
    lookahead: at the moment bucket tau closes, only buckets 1..tau-1 are
    "known history" available to estimate typical price-change volatility.
    Buckets before enough history has accumulated (< min_sigma_periods prior
    DeltaP observations) get z = NaN -> BVC falls back to an even 50/50
    split for those buckets (the only sensible default with no volatility
    estimate yet), matching Phi(0) = 0.5.
    """
    out = buckets.copy()
    out["delta_p"] = out["close_price"].diff()

    # Trailing, lookahead-free rolling std of past DeltaP's: at row tau, use
    # DeltaP_1 .. DeltaP_{tau-1} only (shift(1) moves "current" out of the
    # window before rolling).
    out["sigma_delta_p"] = (
        out["delta_p"].shift(1).rolling(window=sigma_window, min_periods=min_sigma_periods).std()
    )

    out["z"] = out["delta_p"] / out["sigma_delta_p"]
    # Bucket 1 has no DeltaP (no prior bucket close) and early buckets have
    # no sigma estimate yet -> z is NaN -> Phi(NaN) misbehaves, so treat as
    # z = 0 (an exactly-balanced signal), which reproduces the natural
    # "no information yet" prior of a 50/50 split.
    z_filled = out["z"].fillna(0.0)

    buy_frac = norm.cdf(z_filled)
    out["buy_volume"] = out["volume"] * buy_frac
    out["sell_volume"] = out["volume"] - out["buy_volume"]
    out["oi"] = (out["buy_volume"] - out["sell_volume"]).abs() / out["volume"]

    return out


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_pipeline(
    in_path: Path,
    out_path: Path,
    n_buckets_target: int = 50,
    bucket_volume: float | None = None,
    sigma_window: int = 20,
) -> pd.DataFrame:
    trades = load_trades(in_path)
    total_volume = trades["quantity"].sum()

    if bucket_volume is None:
        # Sensible default documented in README/derivation: total captured
        # volume / 50, i.e. aim for ~50 buckets out of this capture. This
        # mirrors the paper's own heuristic of V = (avg daily volume) / 50.
        bucket_volume = total_volume / n_buckets_target

    buckets = build_volume_buckets(trades, bucket_volume)
    result = apply_bvc(buckets, sigma_window=sigma_window)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)

    return result, trades, bucket_volume, total_volume


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build fixed-volume buckets and apply BVC to a captured trade tape."
    )
    p.add_argument("--in", dest="in_path", type=Path, required=True, help="Input ndjson trade file.")
    p.add_argument(
        "--out",
        dest="out_path",
        type=Path,
        default=Path("data/processed/buckets.csv"),
        help="Output CSV path for the bucketed dataset (default: data/processed/buckets.csv).",
    )
    p.add_argument(
        "--n-buckets",
        type=int,
        default=50,
        help="Target number of buckets; bucket_volume = total_volume / n_buckets (default: 50).",
    )
    p.add_argument(
        "--bucket-volume",
        type=float,
        default=None,
        help="Explicit fixed bucket volume V (overrides --n-buckets if given).",
    )
    p.add_argument(
        "--sigma-window",
        type=int,
        default=20,
        help="Rolling window (in buckets) used to estimate sigma_DeltaP (default: 20).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result, trades, bucket_volume, total_volume = run_pipeline(
        args.in_path,
        args.out_path,
        n_buckets_target=args.n_buckets,
        bucket_volume=args.bucket_volume,
        sigma_window=args.sigma_window,
    )

    n_buckets = len(result)
    oi = result["oi"]
    print(f"Loaded {len(trades)} raw trades, total volume {total_volume:.6f}")
    print(f"Bucket volume V = {bucket_volume:.6f} -> {n_buckets} completed buckets")
    print(f"Wrote bucketed dataset -> {args.out_path}")
    print()
    print("OI_tau distribution:")
    print(f"  mean = {oi.mean():.4f}")
    print(f"  std  = {oi.std():.4f}")
    print(f"  min  = {oi.min():.4f}")
    print(f"  max  = {oi.max():.4f}")
    print()
    print("Sample rows:")
    cols = ["bucket_id", "start_time_ms", "end_time_ms", "volume", "close_price", "delta_p", "z", "buy_volume", "sell_volume", "oi"]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(result[cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()

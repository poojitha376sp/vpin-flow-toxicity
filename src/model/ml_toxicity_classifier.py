#!/usr/bin/env python3
"""
ml_toxicity_classifier.py — Part 3 "AI/ML plan" (classical ML stage) of the
VPIN project. See README.md "AI/ML plan" subsection and
`research/CHEATSHEET.md`'s "AI/ML plan for this project" section for the
framing this module implements.

Question this module answers: trained on the *same* bucket-level features
VPIN itself is built from (OI_tau, delta_p_tau, z_tau, volume, rolling
history of those), does a gradient boosting classifier predict near-term
"toxic" (elevated forward volatility) buckets any better than simply
thresholding the analytical VPIN rolling average on the same target? A
null result (ML doesn't clearly beat the hand-built formula) is reported
plainly if that's what the data shows — see CHEATSHEET.md's own
Andersen-Bondarenko-critique framing for why that's a legitimate, useful
finding here, not a failure to hide.

--------------------------------------------------------------------------
Label definition ("toxicity" proxy)
--------------------------------------------------------------------------
For each bucket tau (with at least `trail_window` buckets of history AND
`fwd_window` buckets remaining after it):

    trailing_vol_tau = std(delta_p) over buckets [tau-trail_window+1, tau]
    forward_vol_tau  = std(delta_p) over buckets [tau+1, tau+fwd_window]
    label_tau = 1 if forward_vol_tau > toxic_multiplier * trailing_vol_tau else 0

i.e. "is realized volatility over the next few buckets elevated relative
to its own trailing distribution at the time bucket tau closed" — an
adaptive, no-global-threshold definition of "toxic" that only needs
information available up to tau to define the trailing reference (the
forward_vol side is of course the future target being predicted, same as
any supervised label).

--------------------------------------------------------------------------
Features (all computable using only bucket 1..tau — no lookahead)
--------------------------------------------------------------------------
    oi, delta_p, z, volume                          (contemporaneous, bucket tau)
    oi_roll_mean_5 / _10, oi_roll_std_10             (rolling OI stats)
    delta_p_roll_std_10                              (trailing realized vol, same
                                                       family as VPIN's own sigma_delta_p)
    volume_roll_mean_10
    oi_lag1, oi_lag2                                 (recent-bucket history)

NOTE: VPIN itself (the rolling mean of oi) is deliberately *excluded* from
the feature set — the whole point of the comparison is "ML on the raw
inputs vs. the hand-built VPIN formula on those same inputs", so folding
VPIN in as a classifier feature would collapse that comparison.

--------------------------------------------------------------------------
Evaluation
--------------------------------------------------------------------------
Chronological (no-shuffle) train/test split. Compare:
  1. GradientBoostingClassifier (scikit-learn) trained on the feature set.
  2. VPIN-threshold baseline: use the rolling VPIN_n series (n from
     vpin_estimator.py) itself as a continuous score (AUC), and a
     train-set-chosen threshold for an accuracy figure.
  3. Naive baseline: predict the train-set majority class always.
Report AUC and accuracy for all three on the held-out (chronologically
last) test slice.

Usage:
    python src/model/ml_toxicity_classifier.py \
        --in data/processed/btcusdt_vpin_part3.csv \
        --vpin-col vpin_n50 \
        --trail-window 10 --fwd-window 5 --toxic-multiplier 1.0 \
        --test-frac 0.3
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score


# ---------------------------------------------------------------------------
# Label construction
# ---------------------------------------------------------------------------


def build_label(
    df: pd.DataFrame, trail_window: int, fwd_window: int, toxic_multiplier: float
) -> pd.DataFrame:
    out = df.copy()
    delta_p = out["delta_p"]

    trailing_vol = delta_p.rolling(window=trail_window, min_periods=trail_window).std()

    # Forward realized vol: std of the NEXT fwd_window delta_p values (no
    # current-bucket lookahead into the label's own trailing side — this is
    # deliberately the label, i.e. the thing being predicted).
    forward_vol = (
        delta_p.shift(-1)
        .rolling(window=fwd_window, min_periods=fwd_window)
        .std()
        .shift(-(fwd_window - 1))
    )

    out["trailing_vol"] = trailing_vol
    out["forward_vol"] = forward_vol
    out["label"] = (forward_vol > toxic_multiplier * trailing_vol).astype(float)
    # Rows without a full trailing OR forward window can't be labeled.
    out.loc[trailing_vol.isna() | forward_vol.isna(), "label"] = np.nan
    return out


# ---------------------------------------------------------------------------
# Feature construction (lookahead-free: only bucket 1..tau)
# ---------------------------------------------------------------------------


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    out = df.copy()
    out["oi_roll_mean_5"] = out["oi"].rolling(5, min_periods=5).mean()
    out["oi_roll_mean_10"] = out["oi"].rolling(10, min_periods=10).mean()
    out["oi_roll_std_10"] = out["oi"].rolling(10, min_periods=10).std()
    out["delta_p_roll_std_10"] = out["delta_p"].rolling(10, min_periods=10).std()
    out["volume_roll_mean_10"] = out["volume"].rolling(10, min_periods=10).mean()
    out["oi_lag1"] = out["oi"].shift(1)
    out["oi_lag2"] = out["oi"].shift(2)

    feature_cols = [
        "oi",
        "delta_p",
        "z",
        "volume",
        "oi_roll_mean_5",
        "oi_roll_mean_10",
        "oi_roll_std_10",
        "delta_p_roll_std_10",
        "volume_roll_mean_10",
        "oi_lag1",
        "oi_lag2",
    ]
    return out, feature_cols


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


def evaluate_vpin_threshold(
    vpin_train: pd.Series, vpin_test: pd.Series, y_train: pd.Series, y_test: pd.Series
) -> dict:
    """VPIN-as-a-classifier baseline: AUC treats VPIN as a continuous score
    (threshold-free); accuracy picks the train-set threshold that maximizes
    train accuracy (Youden-style grid search over observed train VPIN
    values), then applies that fixed threshold to the test set.
    """
    auc = roc_auc_score(y_test, vpin_test) if y_test.nunique() > 1 else float("nan")

    best_thresh, best_train_acc = None, -1.0
    for cand in np.unique(vpin_train):
        pred = (vpin_train >= cand).astype(int)
        acc = accuracy_score(y_train, pred)
        if acc > best_train_acc:
            best_train_acc, best_thresh = acc, cand

    test_pred = (vpin_test >= best_thresh).astype(int)
    test_acc = accuracy_score(y_test, test_pred)
    return {"auc": auc, "accuracy": test_acc, "threshold": best_thresh, "train_accuracy": best_train_acc}


def evaluate_gbc(
    X_train: pd.DataFrame, X_test: pd.DataFrame, y_train: pd.Series, y_test: pd.Series, **gbc_kwargs
) -> dict:
    clf = GradientBoostingClassifier(random_state=42, **gbc_kwargs)
    clf.fit(X_train, y_train)
    proba = clf.predict_proba(X_test)[:, 1]
    pred = clf.predict(X_test)
    auc = roc_auc_score(y_test, proba) if y_test.nunique() > 1 else float("nan")
    acc = accuracy_score(y_test, pred)
    importances = pd.Series(clf.feature_importances_, index=X_train.columns).sort_values(ascending=False)
    return {"auc": auc, "accuracy": acc, "model": clf, "feature_importances": importances}


def naive_baseline(y_train: pd.Series, y_test: pd.Series) -> dict:
    majority = y_train.mode().iloc[0]
    pred = pd.Series(majority, index=y_test.index)
    return {"accuracy": accuracy_score(y_test, pred), "majority_class": majority}


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run(
    in_path: Path,
    vpin_col: str,
    trail_window: int,
    fwd_window: int,
    toxic_multiplier: float,
    test_frac: float,
) -> dict:
    df = pd.read_csv(in_path)
    df = build_label(df, trail_window, fwd_window, toxic_multiplier)
    df, feature_cols = build_features(df)

    needed = feature_cols + [vpin_col, "label"]
    # z can be +/-inf when sigma_delta_p (BVC's rolling price-change vol
    # estimate) rounds to ~0 in a very quiet stretch of buckets -- treat
    # like any other missing feature rather than letting it poison sklearn.
    df[needed] = df[needed].replace([np.inf, -np.inf], np.nan)
    clean = df.dropna(subset=needed).reset_index(drop=True)

    n = len(clean)
    if n < 20:
        raise ValueError(
            f"Only {n} fully-labeled/featured rows available after dropping NaNs "
            "(need trailing + forward window history) -- capture more data or "
            "shrink --trail-window/--fwd-window."
        )

    split_idx = int(n * (1 - test_frac))
    train, test = clean.iloc[:split_idx], clean.iloc[split_idx:]

    X_train, X_test = train[feature_cols], test[feature_cols]
    y_train, y_test = train["label"].astype(int), test["label"].astype(int)

    gbc_result = evaluate_gbc(X_train, X_test, y_train, y_test)
    vpin_result = evaluate_vpin_threshold(train[vpin_col], test[vpin_col], y_train, y_test)
    naive_result = naive_baseline(y_train, y_test)

    return {
        "n_total": n,
        "n_train": len(train),
        "n_test": len(test),
        "train_label_rate": float(y_train.mean()),
        "test_label_rate": float(y_test.mean()),
        "gbc": gbc_result,
        "vpin_threshold": vpin_result,
        "naive": naive_result,
        "feature_cols": feature_cols,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train a gradient boosting toxicity classifier and compare vs. a VPIN-threshold baseline."
    )
    p.add_argument("--in", dest="in_path", type=Path, required=True, help="CSV from vpin_estimator.py (buckets + vpin_n<window> cols).")
    p.add_argument("--vpin-col", default="vpin_n50", help="Which VPIN column to use as the baseline (default: vpin_n50).")
    p.add_argument("--trail-window", type=int, default=10, help="Trailing buckets used for the label's volatility reference (default: 10).")
    p.add_argument("--fwd-window", type=int, default=5, help="Forward buckets used for the label's realized-vol target (default: 5).")
    p.add_argument("--toxic-multiplier", type=float, default=1.0, help="Label=1 if forward_vol > multiplier * trailing_vol (default: 1.0).")
    p.add_argument("--test-frac", type=float, default=0.3, help="Fraction of (chronologically last) rows held out for test (default: 0.3).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result = run(
        args.in_path,
        args.vpin_col,
        args.trail_window,
        args.fwd_window,
        args.toxic_multiplier,
        args.test_frac,
    )

    print(f"Loaded {args.in_path}")
    print(
        f"Labeled/featured rows: {result['n_total']}  "
        f"(train={result['n_train']}, test={result['n_test']})"
    )
    print(f"Label ('toxic') rate: train={result['train_label_rate']:.3f}  test={result['test_label_rate']:.3f}")
    print()

    g = result["gbc"]
    v = result["vpin_threshold"]
    nb = result["naive"]

    print("=== Test-set performance ===")
    print(f"  Naive (majority class, train mode={nb['majority_class']}):  accuracy={nb['accuracy']:.4f}")
    print(
        f"  VPIN-threshold baseline ({args.vpin_col}, train-optimal thresh={v['threshold']:.4f}):  "
        f"AUC={v['auc']:.4f}  accuracy={v['accuracy']:.4f}  (train_accuracy={v['train_accuracy']:.4f})"
    )
    print(f"  GradientBoostingClassifier:  AUC={g['auc']:.4f}  accuracy={g['accuracy']:.4f}")
    print()

    delta_auc = g["auc"] - v["auc"]
    delta_acc = g["accuracy"] - v["accuracy"]
    verdict = "beats" if delta_auc > 0.02 else ("roughly ties" if abs(delta_auc) <= 0.02 else "underperforms")
    print(
        f"Verdict: GBC {verdict} the VPIN-threshold baseline on AUC "
        f"(delta_AUC={delta_auc:+.4f}, delta_accuracy={delta_acc:+.4f})."
    )
    print()

    print("GBC feature importances:")
    with pd.option_context("display.width", 200):
        print(g["feature_importances"].round(4).to_string())


if __name__ == "__main__":
    main()

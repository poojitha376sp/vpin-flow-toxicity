# RESULTS — Part 4: Validation & Deliverables

Written 2026-07-23 as the final deliverable of this project (Part 4 / Phase
5 "Validation" + Phase 6 "Deliverables" of the roadmap in `README.md`).
Presents this project's own numbers against both the original VPIN paper's
claims and the Andersen-Bondarenko critique (`research/CHEATSHEET.md` §1),
and folds in the Part 3 ML result. Written for a QuantFest judging audience:
precise about what was actually tested, explicit about what wasn't.

**The one caveat that governs how to read everything below:** this is a
single, small, real BTCUSDT capture — two captures, actually, taken back to
back from Binance's live trade stream, spanning **~250s and ~606s** (9,972
and a further ~4,000 trades; 250 and 400 volume buckets respectively — see
`data/README.md` and Part 3's run logs). That is orders of magnitude
smaller than the multi-year E-mini S&P 500 futures samples in the original
VPIN papers or the Andersen-Bondarenko critique. Every number below is real
(computed from the actual capture, not simulated), but "real" is not the
same as "large-sample" — treat every statistic here as a demonstration that
the *methodology* is sound and correctly implemented, not as a claim that
generalizes to production trading at scale. This caveat is not a formality;
it is load-bearing for the final verdict below.

---

## 1. Recap: what Parts 1-3 established

- **Part 1-2**: derived and implemented the volume clock + Bulk Volume
  Classification (BVC) from first principles (`research/DERIVATION.md`),
  run against a real captured BTCUSDT trade tape.
- **Part 3**: rolling VPIN estimator (`src/model/vpin_estimator.py`) —
  VPIN_n50 mean 0.234 (std 0.088, n=201 valid observations on the
  250-bucket capture) — and a gradient boosting classifier
  (`src/model/ml_toxicity_classifier.py`) trained on VPIN's own raw inputs
  to predict a "toxic" (elevated forward realized volatility) label.
  Headline Part 3 result: on a chronological 70/30 split, the GBC beat a
  VPIN-threshold rule on **AUC** (0.56-0.72 vs. 0.27-0.52 across the
  250- and 400-bucket captures — the VPIN threshold was often *worse than
  random* out-of-sample), but **neither model beat a naive "always predict
  non-toxic" baseline on raw accuracy** (~0.71, driven by class imbalance).

Part 4 does not redo any of this. It asks the two questions Part 3
deliberately left open: (1) does VPIN's apparent relationship to future
volatility survive a direct Andersen-Bondarenko-style control for
contemporaneous volatility, and (2) is any of this economically actionable
for a market maker, using the real price tape rather than a proxy label.

---

## 2. Test 1 — Does VPIN survive the Andersen-Bondarenko volatility control?

**Script:** [`src/validation/volatility_control.py`](../src/validation/volatility_control.py)
**Output table:** [`data/processed/validation_volatility_control.csv`](../data/processed/validation_volatility_control.csv)

### Method

For every bucket τ, two nested OLS models forecast forward realized
volatility (`forward_vol_τ` = std of `delta_p` over the next 5 buckets):

- **Model A (volatility only):** `forward_vol ~ trailing_vol_short(5) + trailing_vol_long(20)`
- **Model B (volatility + VPIN):** Model A's regressors **plus** `vpin_n{20,50,100}`

This is deliberately Andersen & Bondarenko's own test design (2015,
"Assessing Measures of Order Flow Toxicity...") applied to this project's
own data rather than merely cited: if VPIN only appears to predict
volatility because it's riding the same volatility regime as recent
realized volatility, its marginal contribution once that regime is already
in the model should vanish. Two complementary checks, both without
lookahead:

1. **True walk-forward, one-step-ahead, expanding-window OOS test.**
   Refit both models at every step using only data strictly before it,
   forecast one bucket ahead, repeat. Report each model's out-of-sample
   R² against a walk-forward "expanding historical mean" naive benchmark
   (Campbell-Thompson style), and the **incremental OOS R²** of adding
   VPIN (B vs. A).
2. **In-sample nested F-test** on the same chronological 70% training
   block Part 3 used, for the classical significance read (H0: VPIN's
   coefficient = 0).

Run across all 3 VPIN windows (n=20, 50, 100) on **both** the 250-bucket
and 400-bucket captures — 6 configurations total, exactly to avoid
cherry-picking a single flattering setup.

### Results

| Capture | VPIN window | In-sample ΔR² | F-test p-value | Walk-forward incremental OOS R² | Survives control? |
|---|---|---|---|---|---|
| 250-bucket | n=20 | +0.0033 | 0.456 | −0.0102 | **No** |
| 250-bucket | n=50 | +0.0465 | **0.0076** | **−0.0208** | **No** — see note below |
| 250-bucket | n=100 | +0.0171 | 0.184 | −0.2247 | **No** |
| 400-bucket | n=20 | +0.0060 | 0.208 | −0.0132 | **No** |
| 400-bucket | n=50 | +0.0305 | **0.0055** | **+0.0733** | **Yes** |
| 400-bucket | n=100 | +0.0400 | **0.0024** | **+0.0104** | **Yes** |

**2 of 6 configurations survive** the combined bar (statistically
significant in-sample, p<0.05, *and* the incremental effect actually holds
up walk-forward out-of-sample).

### The single most important number in this report

Look at the **250-bucket, n=50 row** — this is the project's own primary
configuration (n=50 is the original paper's default window, and 250
buckets was Part 3's headline run). In-sample, adding VPIN to the
volatility-only model is statistically significant at **p=0.0076** — a
result that, reported on its own, would read exactly like "VPIN predicts
volatility, controlling for recent volatility, p<0.01" — a clean positive
headline. But walk-forward out-of-sample, that same VPIN term makes
forecasts **worse**, not better (incremental R² = −0.0208 — VPIN adds
*net noise* once you have to forecast forward rather than fit backward).

This is not a hypothetical illustration of the Andersen-Bondarenko
mechanism — it is that mechanism reproducing itself on this project's own
data, in real time, in the most natural configuration to have reported.
Anyone running only the in-sample F-test (a very common shortcut) on this
exact capture would have published a false positive. That is the concrete,
first-hand version of Andersen & Bondarenko's point that in-sample
"predictive power" claims for VPIN need to be checked walk-forward before
being trusted, not the abstract version cited secondhand.

### Reading the other rows

The 400-bucket capture's n=50 and n=100 windows *do* survive — genuinely,
by both criteria — with incremental OOS R² of +0.073 and +0.010
respectively. So the honest summary is not "VPIN never survives the
control on this data" (that would overclaim in the critique's favor); it's
**bucket-count- and window-dependent, and passes in a minority (2/6) of
reasonable configurations tested** — which is itself consistent with the
literature's own mixed record (Song/Wu/Simon's parameter-sensitivity
finding, and Bambade & Wu's "mixed, threshold-dependent" result, both
cited in `research/CHEATSHEET.md` §1).

---

## 3. Test 2 — Economic significance: would widening spreads have paid off?

**Script:** [`src/validation/economic_significance.py`](../src/validation/economic_significance.py)

### Method

A market maker holding a resting quote around the close of bucket τ is
exposed to the price moving against it over the buckets that follow. The
proxy used here (symmetric, since the maker doesn't know direction in
advance, and built directly from the real captured price tape):

```
forward_adverse_move_bps(τ) = | close_price[τ+5] − close_price[τ] | / close_price[τ] × 10,000
```

Two independent comparisons, both on real numbers:

1. **VPIN-based** (descriptive, full sample): split all buckets into
   VPIN_n50 quartiles; compare mean forward adverse move in the top
   quartile ("would widen spreads") vs. the bottom quartile ("would not"),
   with a Welch t-test and Mann-Whitney U test.
2. **ML-classifier-based** (genuinely out-of-sample): reuse Part 3's exact
   trained GBC and chronological 70/30 split; take its predicted P(toxic)
   on the **held-out test rows only**, split those by a median predicted-
   probability split, and run the same comparison restricted to that
   genuinely-unseen-by-the-model slice.

A stylized bps→USD translation is also reported, using this capture's real
average bucket notional (bucket volume in BTC × the real captured
BTCUSDT price) — explicitly **illustrative, not a backtested strategy
P&L** (no order-book, fill-probability, or fee model is involved).

### Results

**250-bucket capture:**

| Test | High-signal group mean | Low-signal group mean | Difference | p-value (Welch) |
|---|---|---|---|---|
| VPIN quartiles (n=49 each) | 0.957 bps | 0.561 bps | **+0.396 bps (+70.6%)** | **0.0079** |
| ML predicted-prob, OOS test rows (n=59, AUC=0.563 on vol. label) | 1.161 bps | 0.576 bps | **+0.585 bps (+101.5%)** | **0.0065** |

**400-bucket capture:**

| Test | High-signal group mean | Low-signal group mean | Difference | p-value (Welch) |
|---|---|---|---|---|
| VPIN quartiles (n=87 each) | 0.602 bps | 0.374 bps | **+0.228 bps (+61.0%)** | **0.0095** |
| ML predicted-prob, OOS test rows (n=101, AUC=0.721 on vol. label) | 0.668 bps | 0.538 bps | +0.130 bps (+24.1%) | 0.3400 (n.s.) |

**Stylized bps→USD translation:** on the 250-bucket capture, the 49
highest-VPIN-quartile buckets represent ~$637,840 of real trading notional
(0.198 BTC/bucket at ~$65,701); the +0.396 bps mean difference implies
~$25.27 of illustrative extra exposure if fully realized as loss across
every high-VPIN bucket. The 400-bucket capture: ~$707,808 of notional
across 87 buckets, ~$16.15 illustrative difference. Both figures are small
in absolute dollar terms — expected given the tiny (~10-minute) capture
window and thin per-bucket volume, not a claim about production scale.

### Interpretation

**VPIN itself passes the economic test cleanly in both captures**: buckets
with elevated VPIN really were followed by significantly larger real price
moves against a resting position (p=0.0079 and p=0.0095, correctly signed
in both cases), using the actual trade tape rather than a proxy label. This
is a genuinely positive result for VPIN's economic usefulness on this
dataset, and it holds up in both captures tested — more robust, in fact,
than Test 1's statistical-significance-after-control result.

**The ML classifier's result is the more interesting, more honest finding
here.** It is economically significant on the 250-bucket capture
(p=0.0065) — the capture where its AUC against the *volatility label* was
mediocre (0.563, barely above chance) — but **not** significant on the
400-bucket capture (p=0.34) — the capture where its AUC against the
volatility label was actually strong (0.721, matching Part 3's headline
best number). In other words: **better discriminative statistics against
the proxy label used to train and evaluate the model did not translate
into a more economically informative signal against the real price-move
outcome.** This is a small-sample-scale, from-scratch echo of the
Optiver AI-trading-models finding cited in `research/CHEATSHEET.md` §4 —
that a model "recognizing" a pattern statistically is not the same as that
recognition being reliably actionable — and it is exactly the kind of gap
this project's own AI/ML plan (`research/CHEATSHEET.md`, "AI/ML plan for
this project") flagged in advance as something Part 4's validation should
check for explicitly, rather than assuming "AUC went up" settles the
question.

---

## 4. How this fits together with Part 3

Putting all three parts' findings side by side:

| Question | Result | Verdict |
|---|---|---|
| Does the ML classifier beat the VPIN-threshold rule statistically (AUC)? (Part 3) | Yes, in both captures (0.56-0.72 vs. 0.27-0.52) | ML > VPIN on this metric |
| Does either beat a naive "always non-toxic" baseline on accuracy? (Part 3) | No, neither does (~0.71 for the naive baseline, driven by class imbalance) | Null result, reported honestly |
| Does VPIN's apparent link to *future* volatility survive controlling for *trailing* volatility, walk-forward, no lookahead? (Part 4, §2) | Survives in 2/6 configurations; fails, including one in-sample-significant-but-OOS-negative case, in the other 4 | Mixed, bucket/window-dependent — Andersen-Bondarenko's mechanism directly reproduced in the primary (250-bucket, n=50) configuration |
| Would elevated VPIN have flagged real, larger subsequent adverse price moves? (Part 4, §3) | Yes, significantly, in both captures (p=0.0079, p=0.0095) | Positive for VPIN |
| Would the ML classifier's OOS predicted probability have flagged real, larger subsequent adverse price moves? (Part 4, §3) | Yes in one capture (p=0.0065), not the other (p=0.34) — with *no* relationship to which capture had the better volatility-label AUC | Mixed; AUC-on-proxy-label is not a reliable stand-in for economic usefulness |

No single row of this table, read alone, tells the whole story — which is
itself the point. A project that reported only Part 3's AUC numbers would
sound like an unambiguous ML win. A project that reported only Part 3's
accuracy numbers would sound like an unambiguous null result. A project
that reported only §2's in-sample F-test on the primary configuration
would sound like a clean, VPIN-survives-the-critique positive. A project
that reported only §3's VPIN economic test would sound like unambiguous
support for using VPIN in production. Every one of those single-metric
readings is available in this project's own numbers, and every one of them
would be an overclaim. The only honest summary is the composite one below.

---

## 5. Final verdict, against both the original paper and the critique

**Against the original ELO framing** (VPIN as a real-time, reliably
predictive early-warning toxicity signal): not fully supported on this
data. VPIN's incremental *statistical* predictive power for future
volatility, once trailing volatility is controlled for and the test is run
walk-forward with no lookahead, only survives in 2 of 6 tested
configurations — and in the project's own primary configuration
(250-bucket capture, n=50 window), an apparently clean in-sample positive
result (p=0.0076) actively *reverses* out-of-sample. A judge should not
walk away thinking this project reproduced the original paper's strongest
claims at face value.

**Against the Andersen-Bondarenko critique** (VPIN has no genuine
incremental information once volatility is controlled for, and any
appearance of predictive power is a classification-error artifact): also
not fully supported as a blanket claim. The critique's *mechanism* is
directly and concretely reproduced here — that is this project's strongest,
most specific validation-phase finding, and it is worth being clear that
reproducing a critique's failure mode on your own data is a genuine,
useful result, not a consolation prize. But the critique's strongest claim
("no incremental predictive power," full stop) is too strong for this
dataset: 2 of 6 configurations do survive, and — more importantly — the
independent, real-price-tape economic-significance test in §3 finds VPIN
*did* flag genuinely larger subsequent adverse price moves, significantly,
in both captures tested. A pure "VPIN is worthless" reading would be
overclaiming in the other direction.

**The composite, honest verdict:** on this small (~250-600s, single-asset,
single-session) BTCUSDT sample, VPIN carries **real, non-trivial, but
fragile and implementation-choice-sensitive information** — present enough
to show up cleanly in a direct economic test against real price moves in
both captures, but not robust enough to survive a strict walk-forward
statistical control for contemporaneous volatility across most tested
bucket-count/window combinations, and specifically prone to producing
false-positive-looking in-sample results of exactly the kind the
Andersen-Bondarenko critique warns about. The Part 3 ML classifier tells
the same story from a different angle: it beats VPIN on one metric
(AUC), loses to a naive baseline on another (accuracy), and its
statistical performance against a proxy label doesn't reliably predict its
economic performance against real price data. **The single sentence
version: VPIN and ML-on-VPIN's-inputs both show up as "sometimes real,
never overwhelming, and easy to over- or under-claim if you only check one
metric" — which is a legitimate, literature-consistent finding for a
sample this size, not a definitive resolution of the ELO vs.
Andersen-Bondarenko dispute, and should not be presented to a larger
audience as one.**

---

## 6. Deliverables checklist (Phase 6)

- [x] VPIN computation pipeline (reusable): `src/features/volume_clock.py`
  (volume clock + BVC) → `src/model/vpin_estimator.py` (rolling VPIN).
- [x] Monitor-style output: `vpin_estimator.py`'s CLI prints a live-style
  VPIN summary (per-window stats, top-move sanity check, correlation with
  realized volatility) on every run against fresh capture data; a
  streaming/dashboard UI is listed as a stretch goal (README.md), not
  claimed as done here.
- [x] Write-up comparing results against both the original paper and its
  critics, with an honest verdict: this document.

## 7. What Part 4 deliberately did not do (honest scope note)

- No attempt was made to reconcile these findings with the original VPIN
  papers' E-mini S&P 500 futures results directly (different asset class,
  vastly larger sample, different classification/threshold choices) —
  only with the *methodology* those papers and their critics used.
- The economic-significance test is a proxy (symmetric forward price-move
  magnitude), not a full market-making backtest with an order book,
  inventory model, fill probabilities, or fees — flagged explicitly in §3
  and not disguised as more than it is.
- No attempt was made to re-run Andersen & Bondarenko's specific
  finding about BVC's classification errors growing with volatility
  directly (that would require an independent, non-BVC trade-classification
  ground truth for this capture, e.g. exchange-side maker/taker flags,
  which `data/README.md` notes were captured but not used in BVC by
  design) — a natural next validation step, not attempted here.

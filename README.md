# VPIN — Flow Toxicity / Informed-Trading Detector

Implements Volume-Synchronized Probability of
Informed Trading (VPIN) — a real-time measure of "order flow toxicity" that
flags when informed traders are likely picking off market makers before it
shows up in price. VPIN is famous for being implicated in explaining the
liquidity conditions preceding the 2010 Flash Crash, and market-maker risk
desks watch some version of it in production.

Status: core project complete (Parts 1-4); stretch goals not yet started.

See [`research/CHEATSHEET.md`](research/CHEATSHEET.md) for the working
reference doc — academic papers (including the Andersen-Bondarenko
critique dispute), practitioner writeups, relevant conferences, and what
market-making/HFT firms publicly disclose about adverse-selection / toxic-flow
risk management. Kept up to date as research continues.

---

## Execution Roadmap (4 parts)

Built day by day rather than in one sitting.

- [x] **Part 1 — Foundations** (Phase 1 Research + Phase 2 Data acquisition):
  derive bulk volume classification and the VPIN formula from first
  principles, stand up a real tick/trade data pipeline.
- [x] **Part 2 — Core Mechanism** (Phase 3 Volume clock + bucketing):
  construct the volume clock and implement Bulk Volume Classification. See
  [`src/features/volume_clock.py`](src/features/volume_clock.py) — fixed-volume
  bucket construction + BVC, run against a real ~240s BTCUSDT capture.
- [x] **Part 3 — Fitting & Extension** (Phase 4 VPIN estimation): rolling
  VPIN estimator + gradient boosting toxicity classifier, run on a fresh
  ~606s / 9,972-trade BTCUSDT capture (250 volume buckets). See
  [`src/model/vpin_estimator.py`](src/model/vpin_estimator.py) and
  [`src/model/ml_toxicity_classifier.py`](src/model/ml_toxicity_classifier.py).
  Headline numbers: VPIN_n50 mean 0.234 (std 0.088, n=201 valid obs);
  3 of the 5 largest realized price moves land above the 85th VPIN
  percentile (2 don't — a first-pass, non-rigorous eyeball check only).
  On a chronological 70/30 split, the gradient boosting classifier beats
  a VPIN-threshold baseline on AUC (0.56–0.72 vs. 0.27–0.52 across two
  bucket-count settings — the VPIN threshold is often worse than random
  out-of-sample), but **neither model beats a naive "always predict
  non-toxic" baseline on raw accuracy** (~0.71, driven by class
  imbalance) — reported plainly as a legitimate mixed/null result per
  the Andersen-Bondarenko-critique framing in `research/CHEATSHEET.md`.
- [x] **Part 4 — Validation & Deliverables** (Phase 5 + 6): out-of-sample
  predictive-power test checking the Andersen-Bondarenko critique directly
  against this data, plus an economic-significance test on the real
  trade tape. See [`src/validation/volatility_control.py`](src/validation/volatility_control.py),
  [`src/validation/economic_significance.py`](src/validation/economic_significance.py),
  and the full write-up in [`research/RESULTS.md`](research/RESULTS.md).
  Headline verdict: VPIN's incremental predictive power over trailing
  volatility survives a strict walk-forward control in only 2 of 6 tested
  (capture, window) configurations — directly reproducing the
  Andersen-Bondarenko failure mode on this project's own primary
  configuration, not just citing it — yet an independent economic test
  finds high-VPIN buckets *did* see significantly larger real forward
  price moves in both captures tested, so the honest verdict is real but
  fragile, implementation-sensitive signal, not a clean win for either
  side of the dispute.

Stretch goals (streaming VPIN, cross-venue comparison) are a bonus beyond
these 4 parts, not required for core completion.

---

## Plan of Approach

### Phase 1 — Research
- Primary reference: Easley, López de Prado, O'Hara (2012), *"Flow Toxicity
  and Liquidity in a High-Frequency World"*. Understand the full pipeline:
  volume clock construction, volume bucketing, bulk volume classification
  (BVC), and the VPIN estimator itself.
- Secondary reference: Easley, de Prado, O'Hara (2011), *"The Volume Clock:
  Insights into the High-Frequency Paradigm"* — the "why trade in volume
  time, not clock time" argument that VPIN depends on.
- Read the critical literature too (Andersen & Bondarenko's critique of
  VPIN's forecasting power) so the write-up can honestly discuss the
  metric's limitations rather than presenting it as beyond question.
- Write a short internal note deriving bulk volume classification and the
  VPIN formula from first principles before writing code — see
  [`research/DERIVATION.md`](research/DERIVATION.md).

### Phase 2 — Data acquisition
- Primary candidate: trade-level (tick) data with volume and price, from a
  crypto exchange (Binance/Bybit REST or websocket trade streams) — high
  frequency, free, fully reproducible.
- Secondary candidate: LOBSTER or a public equities tick dataset for
  cross-market validation.
- Store raw trade prints (price, size, timestamp) without pre-aggregation.

### Phase 3 — Volume clock + bucketing
- Construct the volume clock: partition the trade stream into buckets of
  fixed total volume (not fixed time) — this is the core mechanism that
  makes VPIN synchronize with information arrival rate rather than wall
  clock.
- Implement Bulk Volume Classification (BVC) using the standardized price
  change over each bucket (via a normal CDF) to split bucket volume into
  buy-initiated and sell-initiated portions, avoiding the need for a
  tick-rule trade classifier.

### Phase 4 — VPIN estimation
- Compute order imbalance per bucket: |buy volume − sell volume| / total
  volume.
- Compute VPIN as the moving average of bucket-level imbalance over a
  rolling window (n buckets) — reproduce the original paper's parameter
  choices as a baseline, then run sensitivity analysis over bucket size
  and window length.
- Track the VPIN time series against known stress events in the data
  (largest realized-volatility spikes, largest single-bucket price moves)
  as a first sanity check.

### AI/ML plan
ML is a core part of this project, not an afterthought — staged so a solid
classical baseline exists before anything heavier (decision recorded
2026-07-23, see `research/CHEATSHEET.md` for full citations):
- **Now (Part 3, classical ML)**: a gradient boosting classifier trained on
  the Part 2 bucket-level features (OI_τ, ΔP_τ, z_τ, volume, recent-bucket
  history) to predict elevated near-term volatility/toxicity, compared
  against simply thresholding the analytical VPIN rolling average —
  answering "does an ML model trained on the same inputs beat the
  hand-built formula, and does it inherit the same
  volatility-confound problem Andersen & Bondarenko identified in VPIN
  itself (CHEATSHEET.md §1), or avoid it?"
- **Later (Part 4 / stretch, deep learning)**: Cartea, Duran-Martin &
  Sánchez-Betancourt's "Detecting Toxic Flow" (CHEATSHEET.md §1) is the
  direct modern analogue — an online Bayesian neural-network method
  ("PULSE") classifying trade-by-trade toxicity, a genuinely different
  paradigm from VPIN's aggregate rolling average. Also worth keeping in
  mind: Optiver's own AI-trading-models post (CHEATSHEET.md §4) found
  their models could *recognize* adverse selection but still traded at
  negative EV against informed counterparties — a useful, honest
  benchmark for what "the ML model works" should actually mean here
  (recognizing toxicity isn't the same as acting on it correctly).

### Phase 5 — Validation (the part most student projects get wrong)
- Test predictive power out-of-sample: does elevated VPIN precede
  short-horizon volatility spikes or adverse price moves against resting
  liquidity, using strict walk-forward evaluation with no lookahead?
- Compare against the Andersen–Bondarenko critique directly: check whether
  VPIN's apparent predictive power survives once you control for
  contemporaneous volatility, rather than accepting the headline result.
- Report both statistical significance (does VPIN Granger-cause a toxicity
  proxy) and economic significance (would a market maker who widened
  spreads on high VPIN have avoided realized adverse-selection losses).

### Phase 6 — Deliverables
- VPIN computation pipeline (reusable module: volume clock → BVC → VPIN).
- Monitor/dashboard-style output: live VPIN time series with configurable
  alert thresholds.
- Write-up comparing results against both the original paper and its
  critics, with an honest verdict on when VPIN is and isn't useful.

### Stretch goals
- Real-time streaming VPIN computation (not just offline backtest).
- Cross-venue VPIN comparison (does toxicity in one venue lead another?).

---

## Research papers to read next
- Easley, López de Prado, O'Hara (2012) — *Flow Toxicity and Liquidity in a
  High-Frequency World*
- Easley, de Prado, O'Hara (2011) — *The Volume Clock: Insights into the
  High-Frequency Paradigm*
- Easley, Kiefer, O'Hara, Paperman (1996) — *Liquidity, Information, and
  Infrequently Traded Stocks* (origin of PIN, VPIN's predecessor)
- Andersen, Bondarenko (2014) — *VPIN and the Flash Crash* (critical view)

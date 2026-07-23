# VPIN — Flow Toxicity / Informed-Trading Detector

QuantFest (IICPC) project. Implements Volume-Synchronized Probability of
Informed Trading (VPIN) — a real-time measure of "order flow toxicity" that
flags when informed traders are likely picking off market makers before it
shows up in price. VPIN is famous for being implicated in explaining the
liquidity conditions preceding the 2010 Flash Crash, and market-maker risk
desks watch some version of it in production.

Part of a 4-project microstructure suite for QuantFest:
[order-flow-imbalance](https://github.com/poojitha376sp/order-flow-imbalance) ·
[hawkes-fill-probability](https://github.com/poojitha376sp/hawkes-fill-probability) ·
[adverse-selection-market-making](https://github.com/poojitha376sp/adverse-selection-market-making)

Status: planning phase.

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
- [ ] **Part 3 — Fitting & Extension** (Phase 4 VPIN estimation): compute
  the rolling VPIN estimator, sanity-check against known stress events.
- [ ] **Part 4 — Validation & Deliverables** (Phase 5 + 6): out-of-sample
  predictive-power test (incl. checking the Andersen-Bondarenko critique
  directly against this data), monitor pipeline, final write-up.

Stretch goals (streaming VPIN, cross-venue comparison, feeding
adverse-selection-market-making) are a bonus beyond these 4 parts, not
required for core completion.

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
- Feed VPIN as an informed-flow proxy into
  [adverse-selection-market-making](https://github.com/poojitha376sp/adverse-selection-market-making)'s
  spread-widening logic.

---

## Research papers to read next
- Easley, López de Prado, O'Hara (2012) — *Flow Toxicity and Liquidity in a
  High-Frequency World*
- Easley, de Prado, O'Hara (2011) — *The Volume Clock: Insights into the
  High-Frequency Paradigm*
- Easley, Kiefer, O'Hara, Paperman (1996) — *Liquidity, Information, and
  Infrequently Traded Stocks* (origin of PIN, VPIN's predecessor)
- Andersen, Bondarenko (2014) — *VPIN and the Flash Crash* (critical view)

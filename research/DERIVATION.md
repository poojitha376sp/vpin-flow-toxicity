# Deriving VPIN From First Principles

This note works through the reasoning behind VPIN — volume clocks, Bulk Volume
Classification (BVC), and the VPIN estimator itself — in my own words and
math, starting from the underlying microstructure question rather than
quoting the paper's equations. See `CHEATSHEET.md` §1 for the exact sourcing
(Easley, López de Prado & O'Hara 2011/2012; Andersen & Bondarenko 2014/2015).

**Up front, not as an afterthought:** every derivation step below is written
knowing that Andersen & Bondarenko (2015) show BVC's classification errors
grow with volatility, which mechanically inflates VPIN exactly when
volatility is high. That caveat is folded into the derivation at the point
where it actually bites (Part 2), rather than tacked on as a disclaimer at
the end.

---

## Part 0 — The question VPIN is trying to answer

A market maker posts a bid and an ask and captures the spread from
uninformed order flow. The risk is *adverse selection*: some fraction of
incoming orders come from traders who know something about where the price
is about to move, and trading against them is a losing proposition for the
maker no matter how tight or wide the spread is set, in expectation, on that
flow. The practical question a market maker wants answered in real time is:
"is the flow I'm currently seeing more or less likely to be informed right
now, compared to a baseline?" VPIN is one specific, model-free attempt to
build a real-time proxy for that quantity from public trade prints alone
(price, size, timestamp — no need for a structural MLE model like PIN,
no need for order-book depth).

The two design choices that define VPIN are (1) *when* to sample — volume
time instead of clock time — and (2) *how* to label a sample as
buy-pressure vs. sell-pressure without needing a per-trade classifier.
Each is derived below.

---

## Part 1 — Why sample in volume time, not clock time

### The problem with a fixed clock-time grid

Suppose I want to build a time series of "order flow imbalance" and I do
the obvious thing: bucket trades into fixed 5-minute windows, compute
imbalance in each window, done. The issue is that trading activity is
enormously non-uniform in clock time. At 3am on a quiet Tuesday, a 5-minute
bucket might contain 20 trades. During a news release, a 5-minute bucket
might contain 20,000 trades. If I treat both buckets as one "observation"
in a time series, I'm implicitly saying a quiet 5 minutes and a frantic
5 minutes carry equal informational weight. That's backwards: the frantic
period is exactly when new information is most likely to be entering the
market and getting traded on. A clock-time grid *undersamples* the
informative regime and *oversamples* the dead regime.

### The volume-time alternative

Instead of asking "how much time has passed?", ask "how much trading has
happened?" Partition the trade stream into buckets that each contain a
fixed amount of volume `V` (e.g., `V` = 1/50th of average daily volume).
A bucket fills fast when the market is busy and slowly when it's quiet —
so the bucket boundaries themselves adapt to the pace of trading. This is
"volume time": the clock ticks once per `V` units of volume traded, not
once per fixed wall-clock interval.

Why is this the right sampling scheme for an information-arrival proxy?
Market microstructure theory (going back to sequential-trade models like
Easley-Kiefer-O'Hara-Paperman's PIN) treats trade volume itself as
informative: informed traders trade more when they have information to
exploit, and uninformed/noise traders' aggregate volume is comparatively
smooth. If volume is a (noisy) proxy for the intensity of information
arrival, then sampling one observation per fixed unit of volume gives each
observation *roughly comparable informational content*, regardless of how
much or how little wall-clock time it took to accumulate. A bucket that
fills in 3 seconds during a burst of activity and a bucket that fills in
40 minutes overnight are, by construction, treated as the same "size" of
observation — which is precisely the equalization a clock-time grid fails
to provide. This is also why bucketing by volume, rather than by trade
*count*, is preferred: a print of 1 share and a print of 10,000 shares are
very different events, and volume-time weighting is closer to "one dollar
of trading gets one unit of sampling weight" than "one trade gets one unit."

This is the entire content of the "Volume Clock" companion paper's
argument — HFT participants effectively operate in volume/event time
already (their strategies react to trade/quote events, not to a
wall-clock heartbeat), so a measurement framework built in clock time is
structurally mismatched to the phenomenon it's trying to measure.

---

## Part 2 — Deriving Bulk Volume Classification (BVC)

### Why not just classify each trade?

The classical approach (tick rule, Lee-Ready) labels *each individual
trade* as buyer- or seller-initiated by comparing its price to the
previous trade or the prevailing quote midpoint. This requires either
quote data (which the raw exchange trade tape by itself doesn't always
give you cleanly, and definitely doesn't for many crypto/retail-accessible
feeds) or an assumption-heavy tick-rule heuristic applied trade-by-trade,
which is noisy at the individual-trade level and expensive to do exactly
right at HFT tick volumes.

BVC sidesteps per-trade classification entirely. Instead of asking "was
*this* trade a buy or a sell?" it asks a coarser, more robust question:
"over this *whole bucket* of volume, what fraction was probably
buy-initiated?" — and answers it using only the aggregate price move over
the bucket, not any single trade's identity.

### Setting up the classification

Take a volume bucket `τ` containing total volume `V_τ` (using fixed-volume
buckets means `V_τ = V` for every bucket by construction, but the general
form works for the case of unequal bucket sizes too). Let `ΔP_τ = P_τ -
P_{τ-1}` be the change in price (close-to-close, or last trade to last
trade) over that bucket.

The core intuition: if a bucket's volume was disproportionately
buy-initiated, aggressive buyers were hitting the ask repeatedly, which on
net pushes price up — so `ΔP_τ` should be positive. If a bucket's volume
was disproportionately sell-initiated, `ΔP_τ` should be negative. If the
bucket was roughly balanced, `ΔP_τ` should be small in either direction.
The sign and magnitude of `ΔP_τ` is being used as a *bucket-level, noisy
signal* of net order-flow direction over that bucket, standing in for
information we don't have (an actual per-trade classification).

### Standardizing the signal

`ΔP_τ` alone is not comparable across buckets, assets, or time, because
its natural scale depends on how volatile the asset is generally. A $0.50
move in a stock with typical intra-bucket standard deviation of $0.10 is a
huge, decisive move; the same $0.50 move in a stock with typical
intra-bucket standard deviation of $5 is noise. So standardize:

```
z_τ = ΔP_τ / σ_ΔP
```

where `σ_ΔP` is the standard deviation of bucket-to-bucket price changes,
estimated from the recent history of the series (in practice: from the
distribution of `ΔP` across a rolling window of past buckets). `z_τ` now
answers "how many standard deviations of typical price movement did this
bucket's price change represent?" — a scale-free measure of how decisive
the bucket's net direction was.

### From a standardized move to a buy/sell split

Here's the derivation step that actually produces BVC. We want a function
`f(z)` that maps a standardized price change to "the fraction of this
bucket's volume assigned to buys," with three properties that any
sensible such function must satisfy:

1. **Monotonicity**: a larger positive price move should never imply a
   *smaller* buy fraction. `f` should be non-decreasing in `z`.
2. **Symmetry around zero**: a bucket with `ΔP_τ = 0` (no net price
   information one way or the other) should split volume roughly 50/50 —
   there's no reason from price action alone to lean either way. As
   `z → -∞` (a bucket that's unambiguously all selling pressure), the buy
   fraction should go to 0; as `z → +∞`, it should go to 1. So `f` should
   satisfy `f(0) = 0.5`, `f(-∞) = 0`, `f(∞) = 1`.
3. **Diminishing sensitivity at the extremes**: going from `z = 0` to
   `z = 1` (a "somewhat decisive" move) should shift the buy fraction more
   than going from `z = 3` to `z = 4` (already an extremely decisive
   move) — because by the time a bucket's price move is already several
   standard deviations from typical, we're already about as confident as
   we're going to get that it was buy-dominated; more magnitude doesn't
   add much more information about the *split*.

The standard normal CDF, `Φ(z) = P(Z ≤ z)` for `Z ~ N(0,1)`, satisfies all
three by construction: it's monotonic, `Φ(0) = 0.5`, `Φ(-∞) = 0`,
`Φ(∞) = 1`, and it's an S-shaped (sigmoid) curve — steep near zero,
flattening out at the tails, which is exactly the diminishing-sensitivity
property in point 3. There's also a natural probabilistic reading: if we
model the standardized bucket price change as itself approximately
normally distributed (a reasonable assumption for aggregated price
changes over many trades, loosely justified by a CLT-style argument
—many small individual trade-level price impacts summing up), then `Φ(z)`
is literally "the probability that a draw from that normal distribution
is at or below the observed standardized move" — i.e. treating `z` as
itself a random variable and using `Φ` to convert it into a probability
mass reading gives a coherent way to say "how likely is it, on this
model, that the realized move looked at least this buy-ish." That
probability is then used as the buy-volume *fraction*.

So define:

```
V_τ^Buy  = V_τ · Φ(z_τ) = V_τ · Φ(ΔP_τ / σ_ΔP)
V_τ^Sell = V_τ - V_τ^Buy
```

This is BVC. Note what it does *not* require: no quote data, no
trade-by-trade tick-rule comparison, no assumption about which side
initiated any individual trade. It only needs the bucket's closing price
sequence and an estimate of typical price-change volatility — both
derivable from the trade tape alone.

### Where the Andersen-Bondarenko critique enters

This derivation makes the critique's mechanism transparent rather than
mysterious. `z_τ = ΔP_τ / σ_ΔP` is a *standardized* price move — but `σ_ΔP`
is estimated from recent data, and during high-volatility regimes the
*true* underlying volatility of price changes within a bucket is larger
than in calm regimes, for reasons that have nothing to do with informed
trading (liquidity gaps, wider spreads, more volatile market-wide
conditions). If `σ_ΔP` is estimated with any lag or smoothing (which it
must be, since it needs a rolling window), it will underestimate current
realized volatility exactly during the onset of a volatility spike. That
means `z_τ` gets systematically overstated in magnitude right when
volatility jumps — pushing `Φ(z_τ)` toward 0 or 1 more often than the true
buy/sell split would warrant, i.e. BVC becomes a *noisier and more
extreme* classifier precisely when volatility rises, independent of
whether informed trading actually increased. Since VPIN is built by
averaging `|V^Buy - V^Sell|` (Part 3, below), a noisier bucket-level
classifier mechanically produces a *larger* average imbalance — so VPIN
rises with volatility for a purely mechanical, classification-error
reason, not necessarily because more trading is genuinely informed. This
is Andersen & Bondarenko's core point: BVC's error rate is not constant,
it's volatility-dependent, so any observed correlation between VPIN and
subsequent volatility is contaminated by this mechanical channel and
can't be read as evidence of a genuine information-based leading
relationship without first controlling for it.

---

## Part 3 — Deriving the VPIN formula

### Order imbalance per bucket

Given a bucket's buy/sell volume split from BVC, the natural per-bucket
"toxicity" measure is the *absolute* imbalance, normalized by bucket size
so it's comparable across buckets:

```
OI_τ = |V_τ^Buy - V_τ^Sell| / V_τ
```

Absolute value, not signed: a bucket dominated by buying and a bucket
dominated by selling are both "one-sided" in the sense that matters here
— a market maker is being run over by an informed player on one side of
the book either way. The *sign* tells you which side has the informed
pressure (useful for something like an adverse-selection-aware
quote-skewing strategy) but the toxicity magnitude itself should treat
both directions symmetrically. Dividing by `V_τ` normalizes to a fraction
regardless of how large the bucket's absolute volume was, which matters
if bucket sizes vary or you want to compare across assets with different
typical volumes.

**Bounds check:** since `V_τ^Buy + V_τ^Sell = V_τ` and both are
non-negative, `|V_τ^Buy - V_τ^Sell|` is maximized when one of them is 0
(giving `|V_τ^Buy - V_τ^Sell| = V_τ`) and minimized at 0 when
`V_τ^Buy = V_τ^Sell = V_τ/2`. So `OI_τ ∈ [0, 1]` always, with 0 meaning a
perfectly balanced bucket and 1 meaning a bucket BVC assigned entirely to
one side.

### Rolling into VPIN

A single bucket's imbalance is noisy — BVC is already an approximation,
and any one bucket could show a large imbalance from pure chance even
under normal conditions. What actually matters for a toxicity signal is
whether imbalance is *persisting* across many consecutive buckets, which
is a much stronger indication that something systematic (as opposed to
one noisy print) is going on. So average `OI_τ` over the trailing `n`
buckets:

```
VPIN = (1/n) · Σ_{τ=1}^{n} OI_τ = (1/n) · Σ_{τ=1}^{n} |V_τ^Buy - V_τ^Sell| / V
```

(using `V` for the fixed bucket size, matching the paper's notation, since
each `V_τ = V` under fixed-volume bucketing).

**Bounds check:** VPIN is an average of quantities each in `[0,1]`, so
`VPIN ∈ [0,1]` too — a convex combination of bounded terms stays within
their bounds. VPIN = 0 would require every one of the last `n` buckets to
be exactly balanced (essentially never happens in practice); VPIN = 1
would require every one of the last `n` buckets to be classified as
100% one-sided by BVC.

### Reading the number

VPIN near its historical low end says: over the last `n` buckets of
trading, buy and sell pressure have been roughly offsetting — consistent
with a market where order flow is dominated by liquidity/noise trading
rather than one-sided informed positioning. VPIN elevated relative to its
own recent distribution says: for `n` buckets running, volume has
persistently leaned to one side — consistent with (though, per the
critique above, not *proof* of) informed traders repeatedly picking off
one side of the book faster than the other side can be replenished by
uninformed flow, which is exactly the condition under which a market
maker's realized losses from adverse selection accumulate and (per the
Flash Crash narrative) liquidity providers eventually widen or withdraw.
The rolling window is what turns "one noisy bucket" into "a regime" — `n`
is a tunable smoothing parameter (bigger `n` = smoother but slower to
react; the parameter-sensitivity literature in the cheatsheet, e.g. Song/
Wu/Simon, studies this tradeoff directly) and is exactly the kind of
choice Part 4 of this project's roadmap will sensitivity-test rather than
take on faith from the original paper's defaults.

### The caveat, restated precisely

Given Part 2's mechanism, a rising VPIN should be read, from the outset,
as "flow imbalance persisting across buckets, which is *consistent with*
informed trading pressure but is also *mechanically more likely* during
high-volatility regimes because BVC's classification noise itself rises
with volatility." Any claim of the form "VPIN predicts stress" needs to
be tested controlling for contemporaneous volatility/volume before it can
be attributed to genuine information content rather than this mechanical
channel — which is exactly the walk-forward test the roadmap's Phase 5
plans to run, following Andersen & Bondarenko (2015)'s own approach of
checking whether VPIN adds anything once volatility is already accounted
for.

---

## Summary of the pipeline this derivation motivates

1. **Volume clock** (Part 1): partition the trade tape into fixed-volume
   buckets so each observation carries comparable informational weight,
   instead of a wall-clock grid that over/under-samples busy/quiet
   periods.
2. **BVC** (Part 2): within each bucket, use the standardized price change
   `Φ(ΔP_τ / σ_ΔP)` to split volume into a buy fraction and sell fraction,
   avoiding per-trade classification — while carrying the explicit
   knowledge that this standardization is what makes BVC's error rate
   rise with volatility.
3. **VPIN** (Part 3): average the absolute normalized imbalance
   `|V^Buy - V^Sell| / V` over a trailing window of `n` buckets to get a
   bounded `[0,1]` real-time toxicity estimate, read with the volatility
   caveat built in rather than added as a footnote.

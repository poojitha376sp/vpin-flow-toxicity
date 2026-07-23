# VPIN — Flow Toxicity Reference Cheatsheet

Research compiled 2026-07-23. Covers: (1) academic literature, (2) practitioner
explainers, (3) conferences/venues, (4) what market-making/HFT firms disclose
publicly about adverse-selection / toxic-flow risk management. Mirrors the
structure of the sister "Order Flow Imbalance" cheatsheet
(`order-flow-imbalance/research/CHEATSHEET.md`).

**Correction to a premise worth flagging up front:** the *actual* VPIN
methodology paper — Easley, López de Prado & O'Hara (2012), "Flow Toxicity and
Liquidity in a High-Frequency World" — was published in the ***Review of
Financial Studies***, **not** the *Journal of Portfolio Management* (DOI:
10.1093/rfs/hhs053). The *Journal of Portfolio Management* is instead the home
of two closely related but distinct papers by the same authors: "The
Microstructure of the 'Flash Crash'" (2011, JPM 37(2):118–128 — the paper that
first applies VPIN to the Flash Crash) and "The Volume Clock" (2012, JPM
39(1):19–29 — the conceptual/expository companion piece on volume-time
sampling). All three are covered below since the brief for this cheatsheet
named all three as foundational.

---

## 1. Academic papers (core literature)

### Foundational papers

- **Easley, D., Kiefer, N. M., O'Hara, M., & Paperman, J. B. (1996). "Liquidity, Information, and Infrequently Traded Stocks."** *The Journal of Finance*, 51(4), 1405–1436.
  Wiley: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1996.tb04074.x · SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7881
  - Origin of the **PIN (Probability of Informed Trading)** model: a structural microstructure model in which market makers post prices as a function of the estimated arrival rates of informed vs. uninformed (buy/sell) order flow, estimated via maximum likelihood on daily buy/sell trade counts.
  - Headline empirical result: informed-trading risk (PIN) is estimated for NYSE stocks sorted by volume decile, and is found to be **higher for infrequently-traded (low-volume) stocks**, which is offered as an explanation for why such stocks have wider spreads.
  - Why it matters for implementation: PIN is the direct conceptual ancestor of VPIN — same idea (infer informed-trading intensity from order-flow imbalance) but PIN is a **daily, likelihood-estimated, low-frequency** measure, while VPIN (below) is designed to be a **real-time, volume-clock, non-model-based analogue** usable intraday at HFT speed. Useful baseline to contrast against when explaining why VPIN's authors moved away from MLE estimation.

- **Easley, D., de Prado, M. L., & O'Hara, M. (2012). "The Volume Clock: Insights into the High-Frequency Paradigm."** *The Journal of Portfolio Management*, 39(1), 19–29. (Note: dated 2011 in the competition brief / some citations as a working paper, but the JPM print issue is Fall 2012.)
  Publisher: https://jpm.pm-research.com/content/39/1/19 · SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2034858
  - Conceptual/expository paper arguing that the defining feature of HFT is not raw speed but that HFT strategies operate in **"volume time"** (event-based clocks — e.g., ticks, volume, dollar volume) rather than **chronological (wall-clock) time**, and that this creates a structural information/timing disadvantage for traders still operating in clock time.
  - Why it matters for implementation: this is the paper that motivates *why* VPIN buckets trades by fixed volume rather than fixed time — sampling in volume time equalizes the "information content" per observation instead of over/under-sampling quiet vs. frenetic periods.

- **Easley, D., López de Prado, M. M., & O'Hara, M. (2012). "Flow Toxicity and Liquidity in a High-Frequency World."** *The Review of Financial Studies*, 25(5), 1457–1493. DOI: 10.1093/rfs/hhs053. **This is the core VPIN methodology paper.**
  Publisher (Oxford Academic): https://academic.oup.com/rfs/article-abstract/25/5/1457/1569929 · SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1695596 · Author-hosted PDF (Marcos López de Prado's site): https://www.quantresearch.org/VPIN.pdf · NYU Stern-hosted copy: https://www.stern.nyu.edu/sites/default/files/assets/documents/con_035928.pdf
  - **Volume bucket construction:** trading volume (not clock time) is partitioned into buckets of fixed size `V` (volume bucket size = average daily volume ÷ number of buckets, e.g., 50 buckets/day as a starting convention). Each bucket accumulates trades until its volume quota `V` is filled, so busy periods produce buckets faster than quiet periods.
  - **Bulk Volume Classification (BVC):** instead of classifying each individual trade as buyer- or seller-initiated (à la tick rule / Lee-Ready), VPIN classifies volume in **bulk per time interval**, assigning a *fraction* of a bucket's volume to the buy side using the standardized price change over that interval and the **standard normal CDF**: `V_τ^Buy = V_τ · Z((P_τ − P_{τ−1}) / σ_ΔP)`, `V_τ^Sell = V_τ − V_τ^Buy`, where `Z(·)` is the standard normal CDF, `P_τ` is the closing price of sub-interval τ, and `σ_ΔP` is the standard deviation of price changes. A strongly positive price move over the interval assigns most of the interval's volume to buys; a strongly negative move assigns most to sells; roughly flat price assigns close to 50/50.
  - **VPIN formula:** VPIN is the **rolling average, over the most recent `n` volume buckets, of each bucket's absolute order imbalance normalized by volume**:
    `VPIN = (1/n) · Σ_{τ=1}^{n} |V_τ^Sell − V_τ^Buy| / V`
    where `V` is the (fixed) volume per bucket. This yields a bounded [0,1] real-time toxicity estimate that updates every time a new volume bucket fills, without needing MLE estimation (unlike PIN).
  - **Headline empirical claim about the Flash Crash (May 6, 2010):** the paper (together with its companion JPM 2011 piece, below) reports that VPIN, computed on E-mini S&P 500 futures, rose to **unusually/record high levels in the hours before** the Flash Crash, which the authors interpret as order flow becoming progressively more toxic through the morning of May 6, 2010, consistent with market makers being adversely selected and eventually withdrawing liquidity — the proximate mechanism the authors argue produced the crash's liquidity vacuum. **This specific timing claim (VPIN peaking *before* the crash) is the exact point directly disputed by Andersen & Bondarenko — see Critical literature below.**
  - Why it matters for implementation: this paper is the actual spec to code against — BVC formula, bucket sizing, and the rolling-average VPIN definition above are the three components needed for a from-scratch implementation.

- **Easley, D., López de Prado, M. M., & O'Hara, M. (2011). "The Microstructure of the 'Flash Crash': Flow Toxicity, Liquidity Crashes, and the Probability of Informed Trading."** *The Journal of Portfolio Management*, 37(2), 118–128.
  Publisher: https://jpm.pm-research.com/content/37/2/118 · SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1695041
  - Applies the (contemporaneously-developed) VPIN metric specifically to the May 6, 2010 Flash Crash, walking through the intraday VPIN trajectory on E-mini futures that day; commonly cited alongside the RFS (2012) paper as "the VPIN papers." Widely cited claim: VPIN crossed the authors' ~0.9 (90th-percentile) threshold hours ahead of the crash's worst point (~11:55 a.m., roughly two hours before the 2:45 p.m. low), which the authors present as evidence VPIN could have served as an early-warning signal.
  - Why it matters for implementation: this is the specific paper whose Flash Crash "early warning" claim became the most publicly famous result associated with VPIN, and the one most directly attacked (see Andersen & Bondarenko below) — important context for any implementation/backtest that tries to reproduce or evaluate that claim.

### Follow-ups / extensions of VPIN specifically

- **Bethel, E. W., Leinweber, D., Rübel, O., & Wu, K. (2012). "Federal Market Information Technology in the Post Flash Crash Era: Roles for Supercomputing."** *The Journal of Trading*, 7(2), 9–24.
  SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1939522 · DOE/LBNL report version: https://www.osti.gov/servlets/purl/1055697
  - A Lawrence Berkeley National Lab (LBNL) team **independently re-implemented VPIN on E-mini S&P 500 futures data at scale using supercomputing infrastructure** and reports that they could reproduce a strong VPIN signal ahead of the May 6, 2010 Flash Crash, arguing VPIN (and similar toxicity metrics computed at scale) could underpin a regulatory early-warning system for market stress.
  - Matters for implementation: a genuinely independent (non-ELO-authored) computational replication that supports the original Flash Crash timing claim — the main positive data point on the "does VPIN really lead the crash" question, and useful to cite alongside Andersen & Bondarenko's contrary finding for balance.

- **Song, J. H., Wu, K., & Simon, H. D. (2014/2015). "Parameter Analysis of the VPIN (Volume-Synchronized Probability of Informed Trading) Metric."** In *Quantitative Financial Risk Management: Theory and Practice* (Wiley), ch. 13.
  Wiley: https://onlinelibrary.wiley.com/doi/10.1002/9781119080305.ch13 · SSRN: https://ssrn.com/abstract=2427086 · Working-paper PDF (eScholarship): https://escholarship.org/content/qt2sr9m6gk/qt2sr9m6gk_noSplash_31c899ac57bd2a510b3277cbbacb36b5.pdf
  - Also from the LBNL group; systematically studies how VPIN's several free parameters (number of buckets, bucket size, window length `n`, etc.) affect its false-positive rate as an early-warning indicator, since VPIN's practical usefulness is sensitive to these implementation choices rather than being parameter-free.
  - Matters for implementation: directly actionable — a concrete parameter-sensitivity study to reference when choosing bucket count/window length rather than picking the original paper's defaults blindly.

- **Abad, D., & Yagüe, J. (2012). "From PIN to VPIN: An Introduction to Order Flow Toxicity."** *The Spanish Review of Financial Economics*, 10(2), 74–83.
  Publisher (Elsevier/SciELO mirror): https://www.elsevier.es/en-revista-the-spanish-review-financial-economics-332-articulo-from-pin-vpin-an-introduction-S2173126812000344 · Author-hosted PDF: https://www.quantresearch.org/From%20PIN%20to%20VPIN.pdf
  - Didactic paper estimating both PIN and VPIN on 15 Spanish stocks (split into large/medium/small size portfolios); finds VPIN specifications give adverse-selection proxies broadly consistent with PIN estimates, and flags the number-of-buckets parameter as a key sensitivity.
  - Matters for implementation: good, accessible worked example / cross-market (non-U.S.) replication showing the metric transfers outside the E-mini futures setting it was originally built on.

- **Abad, D., Massot, M., Nawn, S., Pascual, R., & Yagüe, J. (2020). "Order Flow Toxicity under the Microscope."**
  Working paper PDF: https://ifrogs.org/PDF/marketMicrostructure_2020/Abad_Massot_Nawn_Pascua_Yague_2020.pdf (an earlier/related version circulated as "Bulk Volume Classification Under the Microscope": https://acfr.aut.ac.nz/__data/assets/pdf_file/0016/222037/ROBERTO-Massot-Samarpan-and-Pascual-2018-BVC-and-NOF-Preliminary-and-incomplete.pdf)
  - Digs into the mechanics of BVC itself — comparing the BVC-classified order-flow proxy against directly-observed (non-inferred) order-flow data, examining which components of modern market message traffic act as leading indicators of illiquidity.
  - Matters for implementation: relevant if you want to validate your own BVC implementation's classification accuracy against ground-truth buy/sell labels rather than trusting the CDF-based split blindly.

- **Yildiz, S., & Van Ness, R. (2020, published version).** "VPIN, liquidity, and return volatility in the U.S. equity markets." *Global Finance Journal*, 45.
  ScienceDirect: https://www.sciencedirect.com/science/article/abs/pii/S1044028318302679
  - Broad U.S. equities study finding VPIN is negatively associated with volume/number-of-trades and positively associated with trade size and volume fragmentation; argues VPIN captures ex-ante information about liquidity deterioration and return volatility, and could serve as a **risk-management tool for market makers, regulators, and traders**.
  - Matters for implementation: a large-sample, more recent, non-ELO-authored positive result on VPIN's usefulness as a liquidity/volatility signal — useful counterweight to the Andersen-Bondarenko critique when the cheatsheet needs a "still has defenders in later literature" data point. (Could not independently verify every figure quoted in secondary summaries — treat headline direction as medium confidence pending a direct read of the published article.)

- **Low, R. K. Y. (2018). "BV-VPIN: Measuring the Impact of Order Flow Toxicity and Liquidity on International Equity Markets."** *Journal of Risk*, 21(2), 1–35. DOI: 10.21314/JOR.2018.399.
  Author-hosted PDF: https://randlow.github.io/2018_JR_BV_VPIN_rev.pdf
  - Applies a bucketed-volatility variant ("BV-VPIN") of the metric to a range of **international equity indices** (not just U.S. futures) and finds elevated BV-VPIN foreshadows periods of high subsequent volatility; a simple tactical asset-allocation strategy switching between equities and cash based on BV-VPIN levels is reported to outperform buy-and-hold in the tested markets.
  - Matters for implementation: another independent, positive, out-of-U.S.-equity-markets replication — useful if the project wants to test VPIN outside E-mini futures/large-cap U.S. equities.
  - Flagged: could not fully machine-extract this PDF's body text (image/stream-heavy); citation and headline finding cross-confirmed via search snippets and Journal of Risk's own indexing, but read the primary source directly before quoting specific numbers.

- **Cartea, Á., Duran-Martin, G., & Sánchez-Betancourt, L. (2023/2026). "Detecting Toxic Flow."** *Quantitative Finance* (forthcoming/2026). arXiv preprint: https://arxiv.org/abs/2312.05827 · Publisher: https://www.tandfonline.com/doi/full/10.1080/14697688.2026.2619539
  - Not a VPIN paper per se — a distinct, more recent (Oxford, Cartea et al.) framework for a **broker** to predict whether a specific client's trade will turn out to be toxic, using an online Bayesian neural-network method ("PULSE") on proprietary FX transaction data, updating in under 1ms.
  - Matters for implementation: represents the modern, ML-based alternative lineage of toxic-flow detection (per-counterparty/per-trade classification) as opposed to VPIN's aggregate, volume-clock, market-wide toxicity estimate — useful to cite as "where this research area has gone since VPIN" / a contrast in scope (broker-client toxicity vs. market-wide flow toxicity).

### Critical literature: Andersen & Bondarenko

This is a real, multi-paper published dispute in the *Journal of Financial Markets* (and later *Review of Finance*) between Andersen & Bondarenko (critics) and Easley, López de Prado & O'Hara (original authors, defending). All items below are separately verified (title, venue, volume/pages, or SSRN ID).

- **Andersen, T. G., & Bondarenko, O. (2014). "VPIN and the Flash Crash."** *Journal of Financial Markets*, 17, 1–46.
  SSRN (2011 working-paper version): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1881731 · ScienceDirect: https://www.sciencedirect.com/science/article/abs/pii/S1386418113000189
  - Reconstructs VPIN on E-mini S&P 500 futures and finds: (1) VPIN is, **by construction**, mechanically correlated with trading volume and volatility — so any apparent "predictive power" may just reflect that mechanical link rather than genuine information content; (2) once volume and volatility are controlled for, VPIN shows **no incremental predictive power for future short-run volatility**; (3) VPIN did **not** reach an all-time high *before* the Flash Crash — it reached its extreme *after*, contradicting the ELO early-warning narrative; (4) VPIN's behavior is highly sensitive to the trade-classification scheme, and a more standard classification approach reverses ELO's reported pattern.
  - Why it matters for implementation: this is the central, most-cited critique. Any implementation that reproduces the "VPIN spiked before the Flash Crash" claim should be checked against this paper's contrary reconstruction — the discrepancy appears to hinge heavily on trade-classification (BVC) choices and exact data/timestamp handling.

- **Easley, D., López de Prado, M. M., & O'Hara, M. (2014). "VPIN and the Flash Crash: A Rejoinder."** *Journal of Financial Markets*, 17, 47–52.
  ScienceDirect: https://www.sciencedirect.com/science/article/abs/pii/S1386418113000293 · SSRN (submitted as "A Comment," 2012): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2062450
  - The original authors' direct reply/defense in the same JFM volume (note: despite the "Comment"/"Rejoinder" naming ambiguity across SSRN vs. published titles, this is authored by Easley/López de Prado/O'Hara, responding to Andersen & Bondarenko). They concede some data/timing nuances but maintain that sustained elevated VPIN reflects genuine adverse-selection conditions and defend the BVC methodology.
  - Why it matters for implementation: shows the specific points of disagreement are largely about methodological choices (trade classification, exact sample window, threshold definitions) rather than a wholesale rejection — useful for deciding which implementation choices are actually load-bearing for the "does it predict the crash" conclusion.

- **Andersen, T. G., & Bondarenko, O. (2014). "Reflecting on the VPIN Dispute."** *Journal of Financial Markets*, 17, 53–64.
  SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2305905 · ScienceDirect: https://www.sciencedirect.com/science/article/abs/pii/S1386418113000475
  - Andersen & Bondarenko's closing response in the same dispute, restating and clarifying their critique after the ELO rejoinder.
  - Why it matters for implementation: the cleanest single summary of the full dispute's final state if you only read one of the four dispute papers.

- **Andersen, T. G., & Bondarenko, O. (2015). "Assessing Measures of Order Flow Toxicity and Early Warning Signals for Market Turbulence."** *Review of Finance*, 19(1), 1–54.
  Publisher (Oxford Academic): https://academic.oup.com/rof/article-abstract/19/1/1/2886427 · SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2292602
  - A more extensive, methodologically deeper follow-up (not just a dispute reply): the authors construct an accurate trade-classification benchmark for E-mini S&P 500 futures using quotes+trades, and show against that benchmark that ELO's **Bulk Volume Classification (BVC) scheme is inferior to a standard tick rule**. They further argue **VPIN "predicts" volatility only because rising volatility itself induces systematic classification errors in BVC** — i.e., an artifact of the classification method, not genuine information content. Conclusion: VPIN is unsuitable as a measure of order flow toxicity or an early-warning signal for market turbulence.
  - Why it matters for implementation: this is the critics' most rigorous and complete statement, going beyond "VPIN didn't predict the crash" to a specific mechanistic explanation (BVC classification error induced by volatility) for *why* it can spuriously appear to. Essential reading before trusting BVC as ground truth in any implementation.

### Other empirical validation / replication (mixed results)

- **Bethel, Leinweber, Rübel & Wu (2012)** — positive replication, see above (Follow-ups section).
- **Yildiz & Van Ness, *Global Finance Journal* (2020)** — positive/supportive result on U.S. equities, see above.
- **Low, *Journal of Risk* (2018)**, BV-VPIN — positive result on international equity indices, see above.
- **An Assessment of the Prediction Quality of VPIN.** Bambade, A., & Wu, K. In *Advanced Analytics and Artificial Intelligence Applications* (IntechOpen, 2019).
  https://www.intechopen.com/chapters/67499
  - Systematically evaluates VPIN's precision/recall as a predictor of extreme-volatility events across 5.6 years of data on the five most liquid futures contracts of the period studied, testing sensitivity to the computation start point. Finding: VPIN has **poor prediction power for large-amplitude "flash crash"-type events** at the traditional 0.99 decision threshold (and raising the threshold doesn't meaningfully help), but shows **more useful predictive power for lower-amplitude flash/liquidity events**.
  - Why it matters for implementation: a mixed/nuanced result — neither a clean vindication nor a clean rejection. Useful for calibrating expectations: VPIN may be more useful as a general liquidity-stress gauge than as a discrete "crash predictor" with a hard threshold.
- **Andersen & Bondarenko (2014, 2015)** — negative, see Critical literature above; this is the dominant skeptical position in the peer-reviewed literature.

---

## 2. Practitioner articles / blog posts / talks

- **Dean Markwick (dm13450.github.io)** — searched specifically for VPIN/PIN/order-flow-toxicity content. **Not found.** His confirmed relevant post is "Order Flow Imbalance - A High Frequency Trading Signal" (2022) — https://dm13450.github.io/2022/02/02/Order-Flow-Imbalance.html — which covers CKS-style OFI, not VPIN. No VPIN-specific post from this author was located; flagging as searched-and-not-found rather than omitted silently.

- **Johannes Heusser — "Order Flow Toxicity of the Bitcoin April Crash"** (Oct 13, 2013)
  https://jheusser.github.io/2013/10/13/informed-trading.html
  Independent quant blogger; implements VPIN (500-BTC volume buckets) on MtGox tick data around the April 2013 Bitcoin crash. Reports VPIN readings above 85% during the crash aftermath — comparable in magnitude to levels reported for the 2010 equity Flash Crash — declining to ~63% as prices recovered, with secondary VPIN peaks around later smaller corrections. Explicitly cautious about over-interpreting this as proof VPIN is a reliable crash predictor. One of the earliest public, from-scratch practitioner replications of VPIN outside the original futures/equities context.

- **VisualHFT — VPIN blog posts**
  - "Volume-Synchronized Probability of Informed Trading (VPIN)" — https://www.visualhft.com/blog/volume-synchronized-probability-of-informed-trading-vpin/
  - "VPIN and Real-Time Order Toxicity: What Your Execution Stack Cannot See Before the Fill" — https://www.visualhft.com/blog/vpin-real-time-order-toxicity-what-your-execution-stack-cannot-see/
  VisualHFT is an open-source (Apache-2.0), C#/.NET real-time market-microstructure analytics tool (per its GitHub: 1,100+ stars) that surfaces VPIN, multi-level LOB imbalance, and related metrics live against exchange feeds; its blog gives practitioner-oriented explainers of VPIN mechanics and how it fits into an execution stack. Vendor content (promotes their own tool) but technically substantive.

- **QuestDB — "VPIN (Volume-synchronized Probability of Informed Trading)" cookbook page**
  https://questdb.com/docs/cookbook/sql/finance/vpin/
  Time-series-database vendor's SQL cookbook example computing VPIN (volume bucketing, per-bucket imbalance, rolling average) directly in SQL over tick data; useful concrete, runnable reference implementation of the bucket/imbalance/rolling-average mechanics, though it is vendor documentation rather than independent research and does not implement full BVC (uses a simpler buy/sell split).

- **QuantStart** — searched specifically for VPIN content. **Not found.** QuantStart (Michael Halls-Moore) has a well-known HFT/market-microstructure article series (see the sister OFI cheatsheet), but no VPIN- or PIN-specific article surfaced via site search; flagging as searched-and-not-found.

- **QuantInsti / Quantra** — searched specifically for VPIN content. **Not found** as a standalone free article; QuantInsti's general "Market Microstructure for High-Frequency Trading" EPAT course module (https://www.quantinsti.com/epat/market-microstructure) may cover PIN/VPIN as part of its curriculum but no dedicated public blog post was located — flagging as unconfirmed rather than invented.

- **Hudson River Trading — "The HRT Beat"** (https://www.hudsonrivertrading.com/hrtbeat/) and **Optiver — Technology Blog** (https://www.optiver.com/insights/technology-blog/): checked directly (see firm section below); HRT's blog has no VPIN/adverse-selection-specific post. Optiver's blog has one directly relevant post, "Where AI trading models work (and where they still fall short)" (April 27, 2026) — https://www.optiver.com/insights/technology-blog/where-ai-trading-models-work-and-where-they-still-fall-short/ — discussing how well LLM-based models identify adverse selection/informed counterparties (see Section 4 for detail).

- **Jane Street — Tech Talks** (https://www.janestreet.com/tech-talks/index.html): no VPIN- or toxic-flow-specific talk found; their exchange/matching-engine talk (as noted in the sister OFI cheatsheet) is infrastructure-focused, not signal-research-focused.

- No HRT/Jump Trading/Optiver/DRW/etc. blog or talk was found that names "VPIN" specifically — see firm-by-firm honesty notes in Section 4.

---

## 3. Conferences / venues

**Academic journals (confirmed venues where VPIN/flow-toxicity work has actually appeared):**
- ***The Journal of Finance*** — original PIN paper (Easley, Kiefer, O'Hara & Paperman, 1996).
- ***The Review of Financial Studies*** (Oxford) — the core VPIN methodology paper (Easley, López de Prado & O'Hara, 2012). This is the correct venue for "the actual VPIN paper" — **not** Journal of Portfolio Management (see correction note at top of this document).
- ***The Journal of Portfolio Management*** — home of the two companion ELO papers: "The Microstructure of the 'Flash Crash'" (2011) and "The Volume Clock" (2012). A practitioner-oriented, applied journal (Institutional Investor Journals imprint) rather than a peer-reviewed academic-economics journal in the RFS/JF sense — worth distinguishing when discussing rigor/peer-review depth.
- ***Journal of Financial Markets*** (Elsevier) — the venue for the entire Andersen–Bondarenko vs. Easley/López de Prado/O'Hara published dispute (all four papers, JFM Vol. 17, 2014).
- ***Review of Finance*** (Oxford, for the European Finance Association) — Andersen & Bondarenko's more extensive 2015 follow-up critique.
- ***The Journal of Trading*** — Bethel, Leinweber, Rübel & Wu's supercomputing-replication paper.
- ***Journal of Risk*** — Low's BV-VPIN international-equities paper.
- ***Global Finance Journal*** (Elsevier) — Yildiz & Van Ness's U.S.-equities VPIN/liquidity/volatility paper.
- ***The Spanish Review of Financial Economics*** — Abad & Yagüe's PIN-to-VPIN didactic paper.
- ***Quantitative Finance*** (Taylor & Francis) — home of the more recent, adjacent "Detecting Toxic Flow" (Cartea, Duran-Martin & Sánchez-Betancourt) toxic-flow-detection paper.

**Books:**
- ***High-Frequency Trading: New Realities for Traders, Markets and Regulators*** (edited by David Easley, Marcos López de Prado & Maureen O'Hara; Risk Books, 2013) — edited volume gathering VPIN-adjacent chapters from the same authors and collaborators; flyer/description: https://quantresearch.org/Risk_HFT_Flyer.PDF · library listing: https://catalog.princeton.edu/catalog/99122351153506421
- ***Quantitative Financial Risk Management: Theory and Practice*** (Wiley, 2015) — contains the Song/Wu/Simon VPIN parameter-analysis chapter (ch. 13).

**Conferences:** No VPIN-specific conference or dedicated track was independently confirmed in this research pass. The metric's home literature overlaps heavily with the general market-microstructure/HFT venues already documented in the sister OFI cheatsheet (e.g., the Paris "Market Microstructure: Confronting Many Viewpoints" series, University of Chicago's Stevanovich Center microstructure conference, Battle of the Quants) — those venues are plausible places VPIN/toxicity work could be presented given topical overlap, but **no specific VPIN talk/session at any of them was verified via search**, so this is flagged as a reasonable inference from subject-matter overlap, not a confirmed fact. Refer to the sister cheatsheet's Section 3 for the general microstructure-conference landscape rather than duplicating unconfirmed specifics here.

---

## 4. Firms — publicly known approach to flow toxicity / informed-trading detection

Caveat up front, same as the sister cheatsheet: **no firm publishes its actual production toxicity/adverse-selection model.** What follows is genuinely public content — blog posts, talks, or on-the-record statements — not speculation about proprietary systems.

- **Optiver** — Runs a public "Technology Blog" (https://www.optiver.com/insights/technology-blog/). One post is directly on point: **"Where AI trading models work (and where they still fall short)"** (April 27, 2026) — https://www.optiver.com/insights/technology-blog/where-ai-trading-models-work-and-where-they-still-fall-short/ — reporting that in internal experiments, LLM-based trading models "recognized the risks of adverse selection and could accurately describe how to adjust their pricing in response," but **struggled to act consistently on that recognition**: "even after correctly identifying an informed counterparty, they still chose to trade with that counterparty at levels that implied negative EV." The post also notes the models could categorize counterparty types (informed traders, position-driven traders, liquidity providers) but "struggled to simulate how those participants would react over time," relying on "simplified or optimistic assumptions" rather than adversarial reasoning. This is a genuine, specific, on-the-record firm statement about adverse-selection handling — one of the more substantive findings in this entire cheatsheet's Section 4.

- **Hudson River Trading (HRT)** — Public tech blog "The HRT Beat" (https://www.hudsonrivertrading.com/hrtbeat/) checked directly; posts cover general modeling philosophy (e.g., "Modeling Equities Returns: The Linear Case," "How HRT Thinks About Data," "In Trading, Machine Learning Benchmarks Don't Track What You Care About," "Applying Artificial Intelligence to Trading") but **no post specifically addresses adverse selection, toxic flow, VPIN, or informed-trading detection**. As in the sister cheatsheet's findings, HRT is one of the more publicly visible firms on general research philosophy but discloses no specific toxicity-detection methodology.

- **Jane Street** — Public "Tech Talks" series (https://www.janestreet.com/tech-talks/index.html), including their exchange/matching-engine ("JX") talk covering LOB mechanics. No talk or post specifically on adverse selection, toxic flow, or informed-trading detection was found.

- **XTX Markets** — Widely described (third-party coverage, not firm-authored) as a fully model-driven market maker using AI to manage adverse selection risk and operating "private liquidity pools" that segment counterparties by trading behavior — but this framing comes from secondary sources (e.g., industry commentary blogs), not a firm-published technical paper found in this pass. As in the sister cheatsheet, XTX's one confirmed direct policy-audience publication is their contribution to a Bank of Canada volume on AI in market making (https://www.banqueducanada.ca/wp-content/uploads/2026/04/Use-of-Artificial-Intelligence-in-Market-Making-XTX-Markets-020326.pdf) — content not independently re-verified in this research pass; treat the adverse-selection-specific claims about XTX as **medium-to-unconfirmed**.

- **Citadel Securities** — No technical research blog found. Third-party/secondary commentary (not firm-published) states that Citadel invests heavily in technology/speed specifically to reduce adverse-selection exposure and uses "toxic flow filtering" to identify informed order flow — but no primary Citadel Securities source substantiating specific methodology was found; this should be treated as generic industry description, not a disclosed methodology.

- **Jump Trading, DRW, Tower Research Capital, IMC, Virtu Financial** — No technical research blogs, papers, or talks specifically addressing flow toxicity, adverse selection, or informed-trading detection were found for any of these five firms in this research pass, consistent with the sister cheatsheet's finding for the same firm list on OFI. Virtu's public-facing analytics business (via its ITG acquisition) markets institutional execution-analytics products to clients, which is a commercial product line, not a disclosure of Virtu's own internal toxicity-detection methodology.

**Honest summary:** across all ten firms, **Optiver's AI-trading-models post is the single most substantive, specific, firm-authored public statement found anywhere in this research pass that directly addresses adverse selection / informed-counterparty detection.** Everything else is either generic infrastructure/philosophy content (HRT, Jane Street) or third-party characterization rather than firm-published technical disclosure (Citadel Securities, XTX Markets). For Jump, DRW, Tower, IMC, and Virtu, no relevant public content of any kind was found.

---

## Summary of sourcing confidence

- **High confidence / directly verified (cross-confirmed across multiple independent sources — SSRN, publisher page, and/or secondary academic summaries):**
  Easley, Kiefer, O'Hara & Paperman (1996) PIN, Journal of Finance 51(4):1405–1436; Easley/López de Prado/O'Hara "Flow Toxicity and Liquidity in a High-Frequency World" (2012), **Review of Financial Studies** 25(5):1457–1493 (DOI 10.1093/rfs/hhs053) — including the correction that this, not JPM, is the core VPIN paper's venue; "The Volume Clock" (2012), JPM 39(1):19–29; "The Microstructure of the 'Flash Crash'" (2011), JPM 37(2):118–128; the full four-paper Andersen–Bondarenko vs. ELO published dispute in Journal of Financial Markets Vol. 17 (2014) with confirmed page ranges (1–46, 47–52, 53–64) and their extended 2015 Review of Finance paper (19(1):1–54) with its BVC-inferior-to-tick-rule finding; Bethel, Leinweber, Rübel & Wu (2012) Journal of Trading 7(2):9–24; VPIN's core formula components (volume bucket construction, BVC via normal CDF of standardized price change, VPIN as rolling mean of |V^Sell − V^Buy|/V) — cross-confirmed across the QuestDB cookbook, MicroAlphas, and multiple secondary academic summaries, though the primary RFS PDF itself could not be machine-extracted for verbatim equation text (see below).
- **Medium confidence (directionally correct, worth verifying primary source before quoting exact figures):**
  Yildiz & Van Ness (2020) Global Finance Journal — headline direction (VPIN correlates with liquidity deterioration) confirmed via multiple secondary summaries, exact statistics not independently re-derived; Low (2018) Journal of Risk BV-VPIN — citation and headline finding confirmed via search/indexing, but the PDF's body text could not be machine-extracted, so specific performance numbers are unverified; Abad, Massot, Nawn, Pascual & Yagüe "Order Flow Toxicity under the Microscope" — existence and general thrust confirmed, exact publication venue/year ambiguous (working-paper vs. published version not fully disentangled); Bambade & Wu IntechOpen chapter — findings summary cross-confirmed via search snippets, primary chapter text not directly read; XTX Markets' and Citadel Securities' adverse-selection practices as described — sourced from third-party/secondary commentary rather than firm-published primary sources.
- **Flagged as unconfirmed / not found (do not cite as fact):**
  Any QuantStart-specific VPIN article (searched, none found); any free/public QuantInsti VPIN blog post (only a paid course module was found, content unverified); any Dean Markwick (dm13450.github.io) post specifically on VPIN or PIN (only his OFI post was found); any specific VPIN-related conference talk/track at Battle of the Quants, the Paris "Confronting Many Viewpoints" series, or the Chicago Stevanovich Center conference (plausible venue overlap by subject matter, but no specific instance verified); any Jump Trading, DRW, Tower Research, IMC, or Virtu Financial public technical content on flow toxicity or informed-trading detection beyond generic careers/company descriptions; the exact verbatim BVC and VPIN equations as printed in the original RFS (2012) paper — reconstructed here from multiple consistent secondary sources (QuestDB, MicroAlphas, and academic summaries) rather than extracted directly from the primary PDF, which repeatedly failed automated text extraction in this research pass — readers implementing VPIN for the competition should verify the exact equations against the primary source (https://www.quantresearch.org/VPIN.pdf) or a clean-text mirror before finalizing code.

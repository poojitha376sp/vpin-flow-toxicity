# Data

## `raw/` (gitignored)

Raw, unaggregated trade prints captured directly from Binance's public
websocket API by `src/data/collect_trades.py`. Not committed to git (large,
easily reproducible, and timestamped snapshots would go stale immediately).

### Capturing data

```bash
pip install -r requirements.txt

# Capture 60s of real BTCUSDT trade prints (default symbol/duration)
python src/data/collect_trades.py

# Explicit options
python src/data/collect_trades.py \
  --symbol btcusdt \
  --duration 120 \
  --out data/raw/btcusdt_trades.ndjson

# Other symbols / the lighter aggTrade stream
python src/data/collect_trades.py --symbol ethusdt --duration 60 --stream aggTrade
```

Ctrl-C stops the capture early (still flushes whatever was captured).

### Output format

Newline-delimited JSON (one trade per line) under `data/raw/`, e.g.:

```json
{"event_time_ms": 1784798778069, "trade_time_ms": 1784798778069, "recv_time_ms": 1784798778211, "symbol": "BTCUSDT", "trade_id": 6528601250, "price": 65725.13, "quantity": 0.00052, "buyer_order_id": null, "seller_order_id": null, "buyer_is_maker": false, "is_best_match": true}
```

Fields: `price`, `quantity`, `trade_time_ms` (exchange trade timestamp) are
the three fields VPIN's pipeline actually needs (Phase 3 volume-clock
bucketing consumes exactly these). `buyer_is_maker` is kept only as an
optional ground-truth label for later validating a from-scratch trade
classifier against Binance's own maker/taker flag — VPIN's BVC approach
(see `research/DERIVATION.md`) does not use it directly.

### Network note

Binance's docs list `wss://stream.binance.com:9443` as the websocket
endpoint. The identical stream is also served on port 443, which the script
uses by default (`--ws-port 443`) since some sandboxed/corporate network
environments block outbound 9443 while allowing standard HTTPS/WSS (443).
Pass `--ws-port 9443` if your network allows the documented port and you
prefer it.

### Verified working (2026-07-23)

Ran `collect_trades.py --symbol btcusdt --duration 45` against the live
Binance API: captured 713 real trade prints over a 43.3s span
(2026-07-23 09:26:18 - 09:27:01 UTC), price range $65,722.39-$65,728.00,
total traded volume 2.874 BTC. Confirms the pipeline works end-to-end
against live exchange data, not just against a mocked/replayed feed.

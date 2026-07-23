#!/usr/bin/env python3
"""
collect_trades.py — capture real-time trade prints from Binance's public
websocket API and store them as raw, unaggregated newline-delimited JSON.

This is Phase 2 (Data acquisition) of the VPIN project: VPIN needs
trade-level (tick) data — price, size, timestamp — NOT order-book depth.
No aggregation or bucketing happens here; that's Phase 3 (volume clock).

Data source: Binance's public raw trade stream
    wss://stream.binance.com:9443/ws/<symbol>@trade
No API key / authentication required for public market data streams.
(Binance also serves the identical stream on port 443, used as the default
here since some network environments/sandboxes block outbound 9443; override
with --ws-port 9443 if your network allows it and you prefer the documented
default port.)

Each line written to the output file is one JSON object with the fields
Binance sends on the raw trade stream, plus a local receipt timestamp:

    {
      "event_time_ms":   int,   # Binance "E" - event time (exchange, ms)
      "trade_time_ms":   int,   # Binance "T" - trade time (exchange, ms)
      "recv_time_ms":    int,   # local wall-clock receipt time (ms) - ours
      "symbol":          str,   # Binance "s"
      "trade_id":        int,   # Binance "t"
      "price":           float, # Binance "p"
      "quantity":        float, # Binance "q"
      "buyer_order_id":  int,   # Binance "b"
      "seller_order_id": int,   # Binance "a"
      "buyer_is_maker":  bool,  # Binance "m" - True => trade was sell-initiated
                                 #               (taker/aggressor was the seller)
      "is_best_match":   bool   # Binance "M"
    }

`buyer_is_maker` is kept only as an optional ground-truth signal for later
validating a from-scratch BVC/tick-rule classifier against Binance's own
maker/taker labelling -- it is NOT used to do the classification itself;
VPIN's whole point is to classify without needing this kind of label.

Usage:
    python src/data/collect_trades.py --symbol btcusdt --duration 60
    python src/data/collect_trades.py --symbol ethusdt --duration 120 \
        --out data/raw/ethusdt_trades.ndjson

Requires: `websockets` (see requirements.txt).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
from pathlib import Path

import websockets

BINANCE_WS_HOST = "stream.binance.com"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Capture raw Binance trade prints to newline-delimited JSON."
    )
    p.add_argument(
        "--symbol",
        default="btcusdt",
        help="Trading pair, lowercase, Binance format (default: btcusdt).",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Capture window in seconds (default: 60). Ctrl-C also stops early.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Output path (newline-delimited JSON). Defaults to "
            "data/raw/<symbol>_trades_<unix_ts>.ndjson"
        ),
    )
    p.add_argument(
        "--stream",
        choices=["trade", "aggTrade"],
        default="trade",
        help=(
            "Binance stream type: 'trade' = every individual trade print "
            "(default, preferred for VPIN's tick data); 'aggTrade' = trades "
            "aggregated by price+taker+timestamp window."
        ),
    )
    p.add_argument(
        "--ws-port",
        type=int,
        default=443,
        help=(
            "Websocket port. Binance documents 9443 but also serves the "
            "identical stream on 443 (default here) - some network "
            "environments block outbound 9443."
        ),
    )
    return p.parse_args()


def default_out_path(symbol: str) -> Path:
    ts = int(time.time())
    out_dir = Path(__file__).resolve().parents[2] / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{symbol}_trades_{ts}.ndjson"


def normalize_trade(msg: dict, stream: str, recv_time_ms: int) -> dict:
    """Map a raw Binance trade/aggTrade payload to our normalized schema."""
    if stream == "trade":
        return {
            "event_time_ms": msg.get("E"),
            "trade_time_ms": msg.get("T"),
            "recv_time_ms": recv_time_ms,
            "symbol": msg.get("s"),
            "trade_id": msg.get("t"),
            "price": float(msg["p"]),
            "quantity": float(msg["q"]),
            "buyer_order_id": msg.get("b"),
            "seller_order_id": msg.get("a"),
            "buyer_is_maker": msg.get("m"),
            "is_best_match": msg.get("M"),
        }
    else:  # aggTrade
        return {
            "event_time_ms": msg.get("E"),
            "trade_time_ms": msg.get("T"),
            "recv_time_ms": recv_time_ms,
            "symbol": msg.get("s"),
            "agg_trade_id": msg.get("a"),
            "price": float(msg["p"]),
            "quantity": float(msg["q"]),
            "first_trade_id": msg.get("f"),
            "last_trade_id": msg.get("l"),
            "buyer_is_maker": msg.get("m"),
        }


async def capture(
    symbol: str, duration: float, out_path: Path, stream: str, ws_port: int
) -> int:
    url = f"wss://{BINANCE_WS_HOST}:{ws_port}/ws/{symbol.lower()}@{stream}"
    deadline = time.monotonic() + duration
    count = 0

    stop = asyncio.Event()

    def _handle_sigint(*_args):
        stop.set()

    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, _handle_sigint)
    except (NotImplementedError, RuntimeError):
        pass  # signal handlers unavailable (e.g. some platforms); rely on duration only

    print(f"Connecting to {url} ...", file=sys.stderr)
    with out_path.open("w", buffering=1) as fh:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            print(
                f"Connected. Capturing for {duration:.0f}s "
                f"(or Ctrl-C to stop early). Writing to {out_path}",
                file=sys.stderr,
            )
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or stop.is_set():
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                except asyncio.TimeoutError:
                    continue
                recv_time_ms = int(time.time() * 1000)
                msg = json.loads(raw)
                record = normalize_trade(msg, stream, recv_time_ms)
                fh.write(json.dumps(record) + "\n")
                count += 1

    return count


def main() -> None:
    args = parse_args()
    out_path = args.out or default_out_path(args.symbol.lower())
    out_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.time()
    count = asyncio.run(
        capture(args.symbol, args.duration, out_path, args.stream, args.ws_port)
    )
    elapsed = time.time() - start

    print(
        f"Done. Captured {count} trade prints in {elapsed:.1f}s -> {out_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

"""Deterministic, seeded paper-trading showcase for the dashboard.

Everything here is SIMULATION. The price series is synthetic (a seeded regime-switching
random walk), the broker is the in-process paper replay engine, and nothing touches a
network, a broker or a credential. Results demonstrate that the pipeline works end to end
(signals -> risk gate -> fills -> hash-chained audit -> analytics). They are not market
evidence, never count toward the Level 3 / 30-day gate, and say nothing about profitability.
"""
from __future__ import annotations

import hashlib
import json
import random
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from research.live_readiness import DemoEvidenceSummary, assess_live_readiness
from research.paper_replay import Bar, PaperReplay

SYMBOL = "SIMUSD"
DEFAULT_SEED = 7
DEFAULT_BARS = 720
MAX_BARS = 2000
_START = datetime(2026, 1, 5, tzinfo=timezone.utc)

SIMULATION_NOTICE = (
    "Synthetic seeded simulation. Not market data, not forward evidence, and it does not "
    "count toward the 30-day gate. No forecast or profit guarantee."
)


def synthetic_bars(seed: int, count: int) -> list[Bar]:
    """Regime-switching (trend / chop / reversal) random walk; fully deterministic per seed."""
    rng = random.Random(seed)
    price = 100.0
    drift, vol, regime_left = 0.0, 0.004, 0
    bars: list[Bar] = []
    for i in range(count):
        if regime_left <= 0:
            regime_left = rng.randint(40, 120)
            drift = rng.choice((-0.0012, -0.0004, 0.0, 0.0005, 0.0013))
            vol = rng.uniform(0.002, 0.007)
        regime_left -= 1
        open_ = price
        close = max(1.0, open_ * (1 + drift + rng.gauss(0, vol)))
        wick = abs(rng.gauss(0, vol)) * open_
        high = max(open_, close) + wick
        low = max(0.5, min(open_, close) - wick)
        price = close
        ts = (_START + timedelta(hours=i)).isoformat()
        bars.append(Bar(ts, SYMBOL, Decimal(f"{open_:.4f}"), Decimal(f"{high:.4f}"),
                        Decimal(f"{low:.4f}"), Decimal(f"{close:.4f}"), Decimal(int(rng.uniform(800, 5000)))))
    return bars


def _sma(values: list[float], n: int, i: int) -> float | None:
    return sum(values[i - n + 1:i + 1]) / n if i + 1 >= n else None


def run_showcase(seed: int = DEFAULT_SEED, count: int = DEFAULT_BARS, *, fast: int = 8, slow: int = 21,
                 starting_cash: Decimal = Decimal("10000")) -> dict:
    if not isinstance(seed, int) or not 0 <= seed <= 10**9:
        raise ValueError("seed must be an integer between 0 and 1,000,000,000")
    if not isinstance(count, int) or not slow + 10 <= count <= MAX_BARS:
        raise ValueError(f"count must be between {slow + 10} and {MAX_BARS}")
    bars = synthetic_bars(seed, count)
    digest = hashlib.sha256(
        "\n".join(f"{b.timestamp},{b.close}" for b in bars).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="jarvis-showcase-") as tmp:
        engine = PaperReplay(Path(tmp) / "showcase.sqlite3", starting_cash=starting_cash, fast=fast, slow=slow,
                             risk_fraction=Decimal("0.02"))
        try:
            report = engine.replay(bars, digest)
            curve = [(ts, float(eq)) for ts, eq in engine.db.execute(
                "SELECT ts,equity FROM equity_curve WHERE symbol=? ORDER BY ts", (SYMBOL,))]
            events = [(ts, kind, json.loads(payload)) for ts, kind, payload in engine.db.execute(
                "SELECT ts,kind,payload FROM events WHERE kind!='observation' ORDER BY id")]
            signals = engine.db.execute(
                "SELECT COUNT(*) FROM events WHERE kind='observation' AND json_extract(payload,'$.signal')!='hold'"
            ).fetchone()[0]
        finally:
            engine.close()

    closes = [float(b.close) for b in bars]
    candles = [{"t": b.timestamp, "o": float(b.open), "h": float(b.high), "l": float(b.low), "c": float(b.close),
                "f": _sma(closes, fast, i), "s": _sma(closes, slow, i)} for i, b in enumerate(bars)]
    peak, max_dd = 0.0, 0.0
    equity = []
    for ts, eq in curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak else 0.0
        max_dd = max(max_dd, dd)
        equity.append({"t": ts, "e": round(eq, 2), "dd": round(dd, 3)})

    trades, open_entry = [], None
    for ts, kind, p in events:
        if kind == "entry_fill":
            open_entry = {"entry_t": ts, "entry_price": float(p["price"]), "quantity": float(p["quantity"]),
                          "entry_fee": float(p["fee"])}
        elif kind == "exit_fill" and open_entry:
            trades.append({**open_entry, "exit_t": ts, "exit_price": float(p["price"]),
                           "net_pnl": round(float(p["realized_net_pnl"]), 2), "reason": p["reason"]})
            open_entry = None
    rejections = [{"t": ts, "reason": p.get("reason")} for ts, kind, p in events if kind == "risk_reject"]

    start_eq = float(starting_cash)
    end_eq = float(report["equity"])
    buy_hold = (closes[-1] / closes[slow] - 1) * 100
    return {
        "simulation": True,
        "notice": SIMULATION_NOTICE,
        "symbol": SYMBOL,
        "seed": seed,
        "params": {"strategy": report["strategy_id"], "version": report["strategy_version"], "fast": fast,
                   "slow": slow, "risk_fraction_pct": 2.0, "fee_bps": 10, "slippage_bps": 5,
                   "daily_loss_limit_pct": 2.0, "bars": count},
        "data_sha256": digest,
        "metrics": {
            "starting_equity": start_eq, "ending_equity": round(end_eq, 2),
            "return_pct": round((end_eq / start_eq - 1) * 100, 3),
            "buy_and_hold_pct": round(buy_hold, 3),
            "max_drawdown_pct": round(max_dd, 3),
            "realized_net_pnl": round(float(report["realized_net_pnl"]), 2),
            "entries": report["entries"], "exits": report["exits"], "signals": signals,
            "risk_rejections": report["risk_rejections"], "wins": report["wins"], "losses": report["losses"],
            "win_rate": None if report["win_rate"] is None else round(float(report["win_rate"]), 4),
            "profit_factor": None if report["profit_factor"] is None else round(float(report["profit_factor"]), 3),
            "expectancy_per_exit": None if report["expectancy_per_exit"] is None
            else round(float(report["expectancy_per_exit"]), 3),
            "open_positions": len(report["open_positions"]),
            "audit_events": report["event_count"], "audit_chain_valid": report["event_chain_valid"],
        },
        "candles": candles,
        "equity": equity,
        "trades": trades,
        "risk_rejections": rejections,
    }


def gate_payload() -> dict:
    """Live-trading gate status. Always blocked: there is no verified demo evidence and no live adapter."""
    empty = DemoEvidenceSummary(0, 0, None, None, None, None, None, 0)
    assessment = assess_live_readiness(empty)
    return {
        "live_trading_enabled": False,
        "status": assessment.status.value,
        "verified_demo_days": 0,
        "required_demo_days": 30,
        "reasons": list(assessment.reasons),
        "criteria": [
            {"label": "Consecutive UTC demo days", "required": "30", "current": "0"},
            {"label": "Realized trade events", "required": "100", "current": "0"},
            {"label": "Net expectancy after costs", "required": "> 0", "current": "n/a"},
            {"label": "Profit factor", "required": ">= 1.2", "current": "n/a"},
            {"label": "Max drawdown", "required": "<= 10%", "current": "n/a"},
            {"label": "Slippage coverage", "required": "100%", "current": "n/a"},
        ],
        "note": "Gate is informational. The simulation never counts toward it, and nothing in this "
                "application can enable live execution.",
    }

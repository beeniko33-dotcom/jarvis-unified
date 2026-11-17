"""Offline, immutable strategy outcome analytics; never auto-promotes strategies."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation


def summarize_strategy_outcomes(outcomes: list[dict], *, minimum_trades: int = 30) -> dict:
    """Summarize closed paper outcomes for one strategy version.

    Results are evidence for human review only. This function cannot edit strategy
    parameters, change risk, enable execution, or promote a candidate.
    """
    if minimum_trades < 1:
        raise ValueError("minimum_trades must be positive")
    if not isinstance(outcomes, list):
        raise ValueError("outcomes must be a list")

    parsed = []
    seen = set()
    identity = None
    for item in outcomes:
        if not isinstance(item, dict):
            raise ValueError("each outcome must be an object")
        trade_id = str(item.get("trade_id", "")).strip()
        strategy_id = str(item.get("strategy_id", "")).strip()
        version = str(item.get("strategy_version", "")).strip()
        if not trade_id or not strategy_id or not version:
            raise ValueError("trade_id, strategy_id and strategy_version are required")
        if trade_id in seen:
            raise ValueError("duplicate trade_id")
        seen.add(trade_id)
        if identity is None:
            identity = (strategy_id, version)
        elif identity != (strategy_id, version):
            raise ValueError("summarize one strategy version at a time")
        try:
            pnl = Decimal(str(item["net_pnl"]))
            risk = Decimal(str(item["risk_amount"]))
            closed = datetime.fromisoformat(str(item["closed_at"]).replace("Z", "+00:00"))
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("outcome requires valid net_pnl, risk_amount and closed_at") from exc
        if not pnl.is_finite() or not risk.is_finite() or risk <= 0:
            raise ValueError("net_pnl must be finite and risk_amount positive and finite")
        if closed.tzinfo is None or closed.utcoffset() is None:
            raise ValueError("closed_at must include a timezone")
        parsed.append((closed, trade_id, pnl, risk))

    parsed.sort(key=lambda row: (row[0], row[1]))
    count = len(parsed)
    wins = sum(1 for row in parsed if row[2] > 0)
    losses = sum(1 for row in parsed if row[2] < 0)
    gross_profit = sum((row[2] for row in parsed if row[2] > 0), Decimal("0"))
    gross_loss = -sum((row[2] for row in parsed if row[2] < 0), Decimal("0"))
    total_pnl = sum((row[2] for row in parsed), Decimal("0"))
    expectancy = total_pnl / count if count else Decimal("0")

    equity = peak = drawdown = Decimal("0")
    for _, _, pnl, _ in parsed:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)

    return {
        "strategy_id": identity[0] if identity else None,
        "strategy_version": identity[1] if identity else None,
        "closed_trade_count": count,
        "wins": wins,
        "losses": losses,
        "breakeven": count - wins - losses,
        "win_rate": str(Decimal(wins) / count) if count else "0",
        "gross_profit": str(gross_profit),
        "gross_loss": str(gross_loss),
        "profit_factor": str(gross_profit / gross_loss) if gross_loss else None,
        "net_pnl": str(total_pnl),
        "expectancy_per_trade": str(expectancy),
        "max_drawdown": str(drawdown),
        "evidence_status": "minimum_sample_met" if count >= minimum_trades else "insufficient_sample",
        "promotion_status": "HUMAN_REVIEW_REQUIRED",
        "automatic_strategy_changes": False,
        "automatic_risk_increase": False,
        "live_trading_enabled": False,
    }

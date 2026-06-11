"""Performance metrics computation."""
import math
from typing import List, Dict

from services.live_account import period_pnl


def compute_metrics(trades: List[Dict], starting_balance: float = 10000.0) -> Dict:
    if not trades:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "win_loss_ratio": 0.0,
            "pnl_today": 0.0,
            "pnl_week": 0.0,
            "pnl_month": 0.0,
        }

    pnls = [t.get("pnl", 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = sum(pnls)
    winrate = (len(wins) / len(pnls)) * 100 if pnls else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    p_win = len(wins) / len(pnls)
    p_loss = len(losses) / len(pnls)
    expectancy = (p_win * avg_win) + (p_loss * avg_loss)

    # Equity curve & drawdown
    equity = starting_balance
    peak = starting_balance
    max_dd = 0.0
    returns = []
    for p in pnls:
        prev = equity
        equity += p
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
        if prev > 0:
            returns.append(p / prev)

    # Sharpe (simplified, no risk-free rate, annualized assuming trades are independent)
    if len(returns) > 1:
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var)
        sharpe = (mean_r / std) * math.sqrt(252) if std > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "total_trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round(winrate, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(sum(pnls) / len(pnls), 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "win_loss_ratio": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0.0,
        **period_pnl(trades),
    }

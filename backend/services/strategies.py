"""Technical indicators and strategy signals (pure Python)."""
from typing import List, Optional, Tuple, Dict


def sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    out = [e]
    for v in values[period:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += -diff
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        gain = diff if diff > 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Tuple[float, float, float]]:
    if len(values) < slow + signal:
        return None
    ema_fast_series = ema_series(values, fast)
    ema_slow_series = ema_series(values, slow)
    # align lengths
    diff = len(ema_fast_series) - len(ema_slow_series)
    if diff > 0:
        ema_fast_series = ema_fast_series[diff:]
    macd_line = [a - b for a, b in zip(ema_fast_series, ema_slow_series)]
    if len(macd_line) < signal:
        return None
    sig_series = ema_series(macd_line, signal)
    if not sig_series:
        return None
    macd_val = macd_line[-1]
    sig_val = sig_series[-1]
    hist = macd_val - sig_val
    return macd_val, sig_val, hist


def bollinger(values: List[float], period: int = 20, std: float = 2.0) -> Optional[Tuple[float, float, float]]:
    if len(values) < period:
        return None
    window = values[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    s = variance ** 0.5
    upper = mid + std * s
    lower = mid - std * s
    return lower, mid, upper


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


# ---------- Strategy signals ----------
# Returns: ("BUY"|"SELL"|None, reason_str)

def strat_rsi(closes: List[float], cfg) -> Tuple[Optional[str], str]:
    r = rsi(closes, cfg.rsi_period)
    if r is None:
        return None, "RSI insufficient data"
    if r < cfg.rsi_oversold:
        return "BUY", f"RSI={r:.2f} < {cfg.rsi_oversold} (oversold)"
    if r > cfg.rsi_overbought:
        return "SELL", f"RSI={r:.2f} > {cfg.rsi_overbought} (overbought)"
    return None, f"RSI={r:.2f} neutre"


def strat_ema_macd(closes: List[float], cfg) -> Tuple[Optional[str], str]:
    ef = ema(closes, cfg.ema_fast)
    es = ema(closes, cfg.ema_slow)
    m = macd(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    if ef is None or es is None or m is None:
        return None, "EMA/MACD insufficient data"
    macd_val, sig_val, hist = m
    if ef > es and macd_val > sig_val and hist > 0:
        return "BUY", f"EMA{cfg.ema_fast}>{cfg.ema_slow}, MACD bullish (hist={hist:.4f})"
    if ef < es and macd_val < sig_val and hist < 0:
        return "SELL", f"EMA{cfg.ema_fast}<{cfg.ema_slow}, MACD bearish (hist={hist:.4f})"
    return None, "EMA/MACD pas de signal"


def strat_bollinger(closes: List[float], cfg) -> Tuple[Optional[str], str]:
    b = bollinger(closes, cfg.bb_period, cfg.bb_std)
    if b is None:
        return None, "BB insufficient data"
    lower, mid, upper = b
    price = closes[-1]
    if price < lower:
        return "BUY", f"Prix {price:.4f} < BB inférieure {lower:.4f}"
    if price > upper:
        return "SELL", f"Prix {price:.4f} > BB supérieure {upper:.4f}"
    return None, f"Prix dans bandes ({lower:.4f}-{upper:.4f})"


def strat_multi(closes: List[float], cfg) -> Tuple[Optional[str], str]:
    """Combination: RSI + EMA cross + MACD + Bollinger. Requires majority alignment."""
    votes_buy = 0
    votes_sell = 0
    reasons = []

    r_sig, r_reason = strat_rsi(closes, cfg)
    if r_sig == "BUY":
        votes_buy += 1
    elif r_sig == "SELL":
        votes_sell += 1
    reasons.append(r_reason)

    e_sig, e_reason = strat_ema_macd(closes, cfg)
    if e_sig == "BUY":
        votes_buy += 2  # weighted higher
    elif e_sig == "SELL":
        votes_sell += 2
    reasons.append(e_reason)

    b_sig, b_reason = strat_bollinger(closes, cfg)
    if b_sig == "BUY":
        votes_buy += 1
    elif b_sig == "SELL":
        votes_sell += 1
    reasons.append(b_reason)

    if votes_buy >= 3 and votes_buy > votes_sell:
        return "BUY", "Multi-indicateur BUY: " + " | ".join(reasons)
    if votes_sell >= 3 and votes_sell > votes_buy:
        return "SELL", "Multi-indicateur SELL: " + " | ".join(reasons)
    return None, "Multi-indicateur: pas de consensus"


STRATEGIES: Dict[str, Dict] = {
    "rsi": {"name": "Scalping RSI", "fn": strat_rsi, "description": "Achète en survente, vend en surachat"},
    "ema_macd": {"name": "Trend EMA/MACD", "fn": strat_ema_macd, "description": "Suit la tendance avec EMA et MACD"},
    "bollinger": {"name": "Mean-Reversion Bollinger", "fn": strat_bollinger, "description": "Reversion à la moyenne via bandes de Bollinger"},
    "multi": {"name": "Multi-indicateurs", "fn": strat_multi, "description": "Combinaison pondérée RSI + EMA/MACD + Bollinger"},
}


def detect_volatility(closes: List[float], window: int = 20) -> float:
    """Return relative volatility (stddev / mean) over the last window candles."""
    if len(closes) < window:
        return 0.0
    w = closes[-window:]
    mean = sum(w) / window
    if mean == 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in w) / window
    return (var ** 0.5) / mean

"""High win-rate, small-gain strategies WITHOUT martingale (1h bars, gold via PAXG and BTC, ~2 months).

Each trade has a fixed stop-loss, one position at a time, fixed 0.05 lot.
Signals on bar close, entry at next bar open, SL/TP checked on following bars' high/low
(if both touched in the same bar, the SL is assumed hit first: pessimistic).
"""
import os
import numpy as np, pandas as pd

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# $ P&L per $1 move at 0.05 lot, round-trip cost in price units
SPEC = {"PAXG": dict(mult=5.0, cost=0.40), "BTC": dict(mult=0.05, cost=40.0)}

def load(sym):
    d = pd.read_csv(f"{D}/{sym}_1h.csv")
    d.index = pd.to_datetime(d.time, unit="ms")
    return d

def indicators(d):
    c = d.close
    d["ema200"] = c.ewm(span=200).mean()
    d["ema50"] = c.ewm(span=50).mean()
    d["ema5"] = c.ewm(span=5).mean()
    delta = c.diff()
    up, dn = delta.clip(lower=0), -delta.clip(upper=0)
    rs2 = up.ewm(alpha=1/2).mean() / dn.ewm(alpha=1/2).mean()
    d["rsi2"] = 100 - 100 / (1 + rs2)
    tr = pd.concat([d.high - d.low, (d.high - c.shift()).abs(), (d.low - c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14).mean()
    m, s = c.rolling(20).mean(), c.rolling(20).std()
    d["bb_up"], d["bb_lo"], d["bb_mid"] = m + 2 * s, m - 2 * s, m
    return d

def simulate(d, sym, signal, sl_atr, tp_atr, exit_rule=None, max_bars=24):
    spec = SPEC[sym]
    trades, i, n = [], 210, len(d)
    while i < n - 1:
        side = signal(d, i)
        if side == 0:
            i += 1; continue
        e = d.open.iloc[i + 1]; a = d.atr.iloc[i]
        sl = e - side * sl_atr * a; tp = e + side * tp_atr * a
        j = i + 1; out = None
        while j < n and j <= i + max_bars:
            hi, lo = d.high.iloc[j], d.low.iloc[j]
            if (side == 1 and lo <= sl) or (side == -1 and hi >= sl): out = sl; break
            if (side == 1 and hi >= tp) or (side == -1 and lo <= tp): out = tp; break
            if exit_rule and exit_rule(d, j, side): out = d.close.iloc[j]; break
            j += 1
        if out is None: out = d.close.iloc[min(j, n - 1)]
        pnl = (side * (out - e) - spec["cost"]) * spec["mult"]
        trades.append((d.index[i + 1], pnl))
        i = j + 1
    return pd.Series(dict(trades)) if trades else pd.Series(dtype=float)

# ---- signals ----
def rsi2_trend(d, i):        # buy dips in uptrend, sell rallies in downtrend
    if d.close.iloc[i] > d.ema200.iloc[i] and d.rsi2.iloc[i] < 10: return 1
    if d.close.iloc[i] < d.ema200.iloc[i] and d.rsi2.iloc[i] > 90: return -1
    return 0

def bb_trend(d, i):          # touch of the outer band, only in the trend's direction
    if d.ema50.iloc[i] > d.ema200.iloc[i] and d.low.iloc[i] < d.bb_lo.iloc[i]: return 1
    if d.ema50.iloc[i] < d.ema200.iloc[i] and d.high.iloc[i] > d.bb_up.iloc[i]: return -1
    return 0

def ema5_exit(d, j, side):   # classic RSI(2) exit: close back across the 5 EMA
    return (side == 1 and d.close.iloc[j] > d.ema5.iloc[j]) or (side == -1 and d.close.iloc[j] < d.ema5.iloc[j])

def report(name, s):
    if len(s) == 0:
        print(f"  {name:48s} aucun trade"); return
    eq = s.cumsum(); dd = (eq - eq.cummax()).min()
    w = s[s > 0]; l = s[s <= 0]
    days = (s.index[-1] - s.index[0]).days or 1
    half = s.index[0] + (s.index[-1] - s.index[0]) / 2
    print(f"  {name:48s} trades {len(s):3d} ({len(s)/days*7:4.1f}/sem)  gagnants {len(w)/len(s):4.0%}  "
          f"gain moy {w.mean() if len(w) else 0:+6.1f}$  perte moy {l.mean() if len(l) else 0:+7.1f}$  "
          f"TOTAL {s.sum():+7.0f}$  pire DD {dd:+6.0f}$  mois1 {s[:half].sum():+6.0f}$ mois2 {s[half:].sum():+6.0f}$")

if __name__ == "__main__":
    for sym in ["PAXG", "BTC"]:
        d = indicators(load(sym))
        print(f"== {sym} 1h, {d.index[0].date()} -> {d.index[-1].date()}, buy&hold {d.close.iloc[-1]/d.close.iloc[210]-1:+.1%}")
        report("RSI2 tendance, sortie EMA5, SL 2 ATR", simulate(d, sym, rsi2_trend, 2.0, 99, ema5_exit))
        report("RSI2 tendance, TP 0.5 ATR / SL 1.5 ATR", simulate(d, sym, rsi2_trend, 1.5, 0.5))
        report("RSI2 tendance, TP 1 ATR / SL 1 ATR", simulate(d, sym, rsi2_trend, 1.0, 1.0))
        report("Bollinger tendance, TP milieu-ish 1 ATR / SL 1.5", simulate(d, sym, bb_trend, 1.5, 1.0))
        report("Bollinger tendance, TP 0.5 ATR / SL 1.5 ATR", simulate(d, sym, bb_trend, 1.5, 0.5))

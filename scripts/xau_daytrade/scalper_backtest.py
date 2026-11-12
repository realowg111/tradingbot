"""Rebuild of the "12-indicator neural" XAUUSD scalper seen in a TikTok video, tested on 2009-2026.

The video's dashboard scores RSI 14, H1 trend, distance to moving average, MACD, structure,
Bollinger, volatility, VWAP, momentum 5 and 15, breakout and "alignment", and trades when
enough signals agree ("8/12 signaux alignés"). We turn each directional indicator into a vote
(+1 bullish / -1 bearish / 0) on 5-minute bars, enter on the next bar open when |sum of votes|
reaches the threshold, and exit on a take-profit / stop-loss in ATR multiples or after a max
holding time. Trading window 03:00-16:55 New York time (the video trades around 09:00 Paris),
one position at a time, flat by 16:55. Stop wins when stop and target sit in the same bar.

The volatility and alignment gauges are not directional, so 10 votes remain. Both the
momentum reading (follow the votes) and the contrarian one (fade them) are tested.

Usage: python3 scalper_backtest.py [path/to/xau_5m.pkl]
"""
import itertools, os, sys
import numpy as np, pandas as pd

COSTS = {"sans frais": 0.0, "ECN 0,007 %": 0.00007, "standard 0,02 %": 0.0002}
SPLIT = pd.Timestamp("2018-01-01", tz="America/New_York")


def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def votes(d):
    c, h, l = d["close"], d["high"], d["low"]
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn)
    macd = ema(c, 12) - ema(c, 26)
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    hi12, lo12 = h.rolling(12).max().shift(1), l.rolling(12).min().shift(1)
    hi20, lo20 = h.rolling(20).max().shift(1), l.rolling(20).min().shift(1)
    tp = (h + l + c) / 3
    day = (d.index + pd.Timedelta(hours=6)).date
    vwap = tp.groupby(day).transform(lambda s: s.expanding().mean())   # no volume in the data
    s = lambda x: np.sign(x).fillna(0)
    v = pd.DataFrame({
        "RSI14": np.where(rsi > 55, 1, np.where(rsi < 45, -1, 0)),
        "Tendance H1": s(c - ema(c, 600)),            # 50-hour EMA on 5-minute bars
        "Ecart MM": s(c - ema(c, 20)),
        "MACD": s(macd - ema(macd, 9)),
        "Structure": s(c - (hi12 + lo12) / 2),
        "Bollinger": s(c - mid),
        "VWAP": s(c - vwap),
        "Momentum 5": s(c - c.shift(5)),
        "Momentum 15": s(c - c.shift(15)),
        "Cassure": np.where(c > hi20, 1, np.where(c < lo20, -1, 0)),
    }, index=d.index)
    return v.sum(axis=1).to_numpy()


def atr(d, n=14):
    pc = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - pc).abs(), (d["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().shift(1).to_numpy()


def simulate(d, score, a, thr, tp_atr, sl_atr, max_bars, fade):
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    m = (d.index.hour * 60 + d.index.minute).to_numpy()
    open_ok = (m >= 180) & (m < 16 * 60 + 55)
    flat = m >= 16 * 60 + 55
    day = ((d.index + pd.Timedelta(hours=6)).normalize()).to_numpy()
    sig = np.where(score >= thr, 1, np.where(score <= -thr, -1, 0)) * (-1 if fade else 1)
    trades, i, n = [], 0, len(o) - 1
    while i < n:
        if sig[i] == 0 or not open_ok[i + 1] or day[i + 1] != day[i] or not a[i] > 0:
            i += 1
            continue
        side, j = sig[i], i + 1
        en = o[j]
        tp, sl = en + side * tp_atr * a[i], en - side * sl_atr * a[i]
        ex, k = None, j
        while k <= n and k < j + max_bars and day[k] == day[j]:
            if side > 0:
                if l[k] <= sl: ex = min(o[k], sl) if k > j else sl
                elif h[k] >= tp: ex = tp
            else:
                if h[k] >= sl: ex = max(o[k], sl) if k > j else sl
                elif l[k] <= tp: ex = tp
            if ex is not None or flat[k]:
                break
            k += 1
        k = min(k, n)
        if ex is None:
            ex = c[k]
        trades.append((d.index[j], side * (ex / en - 1)))
        i = k + 1
    return pd.DataFrame(trades, columns=["t", "r"]).set_index("t")["r"]


def summary(r, cost):
    r = r - cost
    if len(r) == 0:
        return {}
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    daily = r.groupby(r.index.date).sum()
    daily.index = pd.to_datetime(daily.index)
    full = pd.Series(0.0, index=pd.bdate_range(daily.index[0], daily.index[-1])).add(daily, fill_value=0)
    eq = (1 + full).cumprod()
    win, loss = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades/jour": len(r) / yrs / 252, "gagnants": (r > 0).mean(), "PF": win / loss if loss else np.nan,
            "moy. (pb)": r.mean() * 1e4, "CAGR 1x": eq.iloc[-1] ** (1 / yrs) - 1,
            "max DD 1x": (eq / eq.cummax() - 1).min(), "Sharpe": full.mean() / full.std() * np.sqrt(252)}


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "data", "xau_5m.pkl")
    d = pd.read_pickle(path)
    score, a = votes(d), atr(d)

    # Default: 8 of 10 votes aligned, scalper exits (small target, wide stop -> high win rate), 1 h max.
    print("Réglage par défaut : 8/10 votes alignés, TP 0,5 ATR, SL 1,5 ATR, 1 h max (taille 1x le notionnel)\n")
    rows = []
    for fade in (False, True):
        r = simulate(d, score, a, 8, 0.5, 1.5, 12, fade)
        for cname, cost in COSTS.items():
            st = summary(r, cost)
            st_is, st_oos = summary(r[:SPLIT], cost), summary(r[SPLIT:], cost)
            rows.append({"lecture": "contrarian" if fade else "momentum", "frais": cname, **st,
                         "Sharpe 09-17": st_is["Sharpe"], "Sharpe 18-26": st_oos["Sharpe"]})
    df = pd.DataFrame(rows)
    for col in ("gagnants", "CAGR 1x", "max DD 1x"):
        df[col] = df[col].map(lambda x: f"{x:+.1%}" if col != "gagnants" else f"{x:.0%}")
    print(df.round(2).to_string(index=False))

    print("\nGrille (frais ECN) : seuil x TP x SL x durée x lecture")
    res = []
    for thr, tp, sl, mb, fade in itertools.product([6, 8, 10], [0.3, 0.5, 1.0], [0.5, 1.0, 2.0], [6, 24], [False, True]):
        r = simulate(d, score, a, thr, tp, sl, mb, fade)
        if len(r) < 200:
            continue
        cost = COSTS["ECN 0,007 %"]
        res.append(((thr, tp, sl, mb, "fade" if fade else "mom"), summary(r[:SPLIT], cost)["Sharpe"],
                    summary(r[SPLIT:], cost)["Sharpe"], summary(r, cost)["gagnants"], summary(r, COSTS["standard 0,02 %"])["Sharpe"]))
    g = np.array([[x[1], x[2], x[4]] for x in res])
    print(f"  {len(res)} réglages | Sharpe 09-17 > 0 : {int((g[:, 0] > 0).sum())} | 18-26 > 0 : {int((g[:, 1] > 0).sum())}"
          f" | les deux > 0 : {int(((g[:, 0] > 0) & (g[:, 1] > 0)).sum())} | positifs avec frais standard : {int((g[:, 2] > 0).sum())}")
    best = max(res, key=lambda x: x[1])
    print(f"  meilleur sur 09-17 {best[0]} : Sharpe {best[1]:+.2f} -> 18-26 {best[2]:+.2f}, gagnants {best[3]:.0%}, frais standard {best[4]:+.2f}")
    top = max(res, key=lambda x: x[3])
    print(f"  plus haut taux de réussite {top[0]} : gagnants {top[3]:.0%}, Sharpe 09-17 {top[1]:+.2f}, 18-26 {top[2]:+.2f}")

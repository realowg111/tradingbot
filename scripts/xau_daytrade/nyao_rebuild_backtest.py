"""Independent rebuild of the core of Nyao Scalper v54 (github.com/elrizwiraswara/nyao_scalper_mt5,
open source MT5 EA for XAUUSD M5), tested on 2009-2026 HistData 5-minute bars.

The author publishes backtests for 2022-2026 only: -5.3 %, -9.0 %, +0.9 %, +65.3 % (2025) and
+93.8 % (Jan-Sep 2026). This script rebuilds the default profile's main rules from the source:

  - Trend score per closed M5 bar, 4 parts averaged into s (code: ReadTrend):
      range position over 200 bars, tanh((close - EMA200) / 4 ATR14),
      tanh(efficiency ratio over 100 bars / 0.25), tanh(move over 192 bars / 12 ATR14).
    Buy score = 5 + 5 s, smoothed over the last 2 closed bars (weights 2 and 1).
  - D1 filter: last daily close >= 0.5 % beyond a rising EMA50 (falling for sells).
  - Entry at the next bar open when the score of the allowed side is >= 5.
  - Stop $20 from entry. Checkpoints every $20: keep the trade if the score still agrees and
    lock 50 % of the move, else close. Trailing stop $20 behind the best price from +$10.
    Smallest profit locked from +$15. A losing trade is closed when the opposite score >= 6.
  - Risk 1.25 % of a fixed $2,000 per trade (results are summed, like the author's monthly
    resets, not compounded).

Simplified: one position at a time (the EA allows 2), no news filter, no loss-streak pause,
no drawdown pauses. Costs per round trip: $0.30 (Exness-like raw spread) or 0.02 % of price.
Gold cost ~$1,000 in 2009, so a fixed $20 stop was 2 % of price then and 0.5 % in 2026; the
"scaled" variant uses a stop of 0.55 % of price instead (= $20 at ~$3,600).

Usage: python3 nyao_rebuild_backtest.py [path/to/xau_5m.pkl]
"""
import os, sys
import numpy as np, pandas as pd

AUTHOR = {2022: -5.3, 2023: -9.0, 2024: 0.9, 2025: 65.3}


def scores(d):
    c, h, l = d["close"], d["high"], d["low"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    ema = c.ewm(span=200, adjust=False).mean()
    hi, lo = h.rolling(200).max(), l.rolling(200).min()
    rng = ((c - (hi + lo) / 2) / ((hi - lo) / 2)).fillna(0)
    path = c.diff().abs().rolling(100).sum()
    eff = np.tanh(((c - c.shift(100)) / path) / 0.25)
    mom = np.tanh((c - c.shift(192)) / (12 * atr))
    s = (rng + np.tanh((c - ema) / (4 * atr)) + eff + mom) / 4
    s_smooth = (2 * s + s.shift(1)) / 3          # closed bars i=1 (weight 2) and i=2 (weight 1)
    return s_smooth.fillna(0).to_numpy()


def d1_filter(d):
    day = (d.index + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    dc = d["close"].groupby(day).last()
    ema = dc.ewm(span=50, adjust=False).mean()
    buy = (dc >= ema * 1.005) & (ema > ema.shift(1))
    sell = (dc <= ema * 0.995) & (ema < ema.shift(1))
    allow = (buy.astype(int) - sell.astype(int)).shift(1).fillna(0)   # last CLOSED daily bar
    return allow.reindex(day).to_numpy()


def simulate(d, s, allow, stop_mode="fixed", cost_mode="raw"):
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    t = d.index
    n, trades, i = len(o), [], 300
    while i < n - 1:
        side = 1 if (allow[i] > 0 and s[i] >= 0) else (-1 if (allow[i] < 0 and s[i] <= 0) else 0)
        if side == 0:
            i += 1
            continue
        j = i + 1
        en = o[j]
        D = 20.0 if stop_mode == "fixed" else en * 0.0055
        cost = 0.30 if cost_mode == "raw" else en * 0.0002
        sl = en - side * D
        best, cp, ex, k = en, 1, None, j
        while k < n:
            # 1. stop (checked first: conservative)
            if (side > 0 and l[k] <= sl) or (side < 0 and h[k] >= sl):
                ex = (min(o[k], sl) if side > 0 else max(o[k], sl)) if k > j else sl
                break
            # 2. favourable extreme of the bar
            fav = h[k] if side > 0 else l[k]
            if side * (fav - best) > 0:
                best = fav
            move = side * (best - en)
            # 3. checkpoint(s) reached during the bar: keep while the score agrees, else close
            closed = False
            while move >= cp * D:
                if side * s[k] > 0:
                    sl = side * max(side * sl, side * (en + side * 0.5 * cp * D))
                    cp += 1
                else:
                    ex, closed = en + side * cp * D, True
                    break
            if closed:
                break
            # 4. smallest-profit lock from +$15, trailing $D from +$10 (both scaled by D/20)
            if move >= 0.75 * D:
                sl = side * max(side * sl, side * (en + side * cost))
            if move >= 0.5 * D:
                sl = side * max(side * sl, side * (best - side * D))
            # 5. trend-flip exit for a losing trade (opposite score >= 6 <=> side * s <= -0.2)
            if side * (c[k] - en) < 0 and side * s[k] <= -0.2:
                ex = o[k + 1] if k + 1 < n else c[k]
                k += 1
                break
            k += 1
        if ex is None:
            ex = c[min(k, n - 1)]
        trades.append((t[j], side * (ex - en) / D - cost / D))
        i = k + 1
    return pd.DataFrame(trades, columns=["t", "R"]).set_index("t")["R"]


def yearly(R, risk=1.25):
    y = R.groupby(R.index.year).sum() * risk
    m = R.groupby([R.index.year, R.index.month]).sum() * risk
    return y, m


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "data", "xau_5m.pkl")
    d = pd.read_pickle(path)
    s, allow = scores(d), d1_filter(d)
    out = {}
    for stop in ("fixed", "scaled"):
        for cost in ("raw", "pct"):
            R = simulate(d, s, allow, stop, cost)
            y, m = yearly(R)
            out[(stop, cost)] = (R, y, m)
    tab = pd.DataFrame({f"stop {a} / frais {b}": v[1] for (a, b), v in out.items()})
    tab["auteur (MT5)"] = pd.Series(AUTHOR)
    print("Rendement annuel en % (1,25 % de risque par trade sur 2 000 $ fixes, non composé) :")
    print(tab.round(1).to_string())
    print()
    for (a, b), (R, y, m) in out.items():
        pre, post = y[y.index <= 2021], y[y.index >= 2022]
        eq = (m.cumsum())
        dd = (eq - eq.cummax()).min()
        print(f"stop {a:6s} frais {b:3s}: {len(R)} trades, gagnants {(R > 0).mean():.0%}, R moyen {R.mean():+.3f}, "
              f"PF {R[R > 0].sum() / -R[R < 0].sum():.2f} | 2009-2021 {pre.sum():+.0f} % ({(pre > 0).sum()}/{len(pre)} ans +) "
              f"| 2022-2026 {post.sum():+.0f} % | mois + {(m > 0).mean():.0%} | pire repli {dd:.0f} pts")

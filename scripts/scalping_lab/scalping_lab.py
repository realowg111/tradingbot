"""Scalping lab: three families of automated scalps (hold <= 30 minutes, automatic TP and SL),
tested on 1-minute bars: Nasdaq 100 (QQQ 2014-2024, regular session) and gold (2009-2026).

  S1. Trend-pullback scalp (Nasdaq): trade only in the direction of the day given by the validated
      noise-boundary strategy (close above the upper band = long only, below the lower band =
      short only). Long when a 1-minute bar dips to the EMA(9) and the next bar closes above that
      bar's high; entry at the next open; SL = lowest low of the last 5 bars; TP = 1.5 R.
  S2. VWAP reversion with limit orders: a resting limit at VWAP - 2 sd (long) / VWAP + 2 sd (short),
      sd = standard deviation of (close - VWAP) since the session start; filled only if the price
      trades through the limit (not if the bar opens beyond it); TP = VWAP, SL = VWAP -/+ 3 sd;
      after a trade, no new entry until the price is back inside the bands.
  S3. Volatility burst: a 1-minute bar whose range is > 3x ATR(20) and that closes in its top 20 %
      (bottom 20 %) -> follow it at the next open; SL = the bar's other end; TP = 1 R.
All: one position at a time, max holding 30 minutes (15 for S3), flat at the session end;
if SL and TP are both inside one bar the SL wins; limit orders get no TP on their fill bar.
Windows (New York time): Nasdaq 10:00-15:30 entries, flat 15:59; gold 03:00-11:30 entries
(London + New York morning), flat 12:00.
Costs per round trip: Nasdaq 0.01 % (CFD US100 / MNQ), gold 0.007 % (ECN); x3 stress.
Results in R; with 0.5 % of equity risked per trade, the yearly return in % = 0.5 x sum of R.

Usage: python3 scalping_lab.py --qqq qqq.parquet --gold <HistData raw dir>
"""
import argparse, itertools, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "nine_am_cr"))
from nine_am_cr_backtest import load_qqq, load_gold   # noqa: E402

SPLIT = 2019
RISK = 0.5   # % of equity per trade


def by_day(d, start, end):
    t = (d.index.hour * 60 + d.index.minute).to_numpy()
    keep = (t >= start) & (t < end) & (d.index.dayofweek < 5)
    d, t = d[keep], t[keep]
    day = d.index.normalize()
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    v = d["volume"].to_numpy() if "volume" in d else np.ones(len(d))
    b = np.flatnonzero(np.r_[True, day[1:] != day[:-1], True])
    return [(day[a], t[a:z], o[a:z], h[a:z], l[a:z], c[a:z], v[a:z]) for a, z in zip(b[:-1], b[1:]) if z - a > 60]


def walk(o, h, l, c, t, j, side, en, sl, tp, max_bars, flat, tp_on_first=True):
    """(exit price, exit bar) of a trade entered on bar j."""
    for k in range(j, min(len(c), j + max_bars)):
        if t[k] >= flat:
            return (c[k - 1] if k > j else en), k
        if (side > 0 and l[k] <= sl) or (side < 0 and h[k] >= sl):
            return (sl if k == j else (min(o[k], sl) if side > 0 else max(o[k], sl))), k
        if (k > j or tp_on_first) and ((side > 0 and h[k] >= tp) or (side < 0 and l[k] <= tp)):
            return tp, k
    k = min(len(c), j + max_bars) - 1
    return c[k], k


def vwap_sd(h, l, c, v):
    tp = (h + l + c) / 3
    vw = np.cumsum(tp * v) / np.cumsum(v)
    dev = c - vw
    n = np.arange(1, len(c) + 1)
    m1, m2 = np.cumsum(dev) / n, np.cumsum(dev * dev) / n
    return vw, np.sqrt(np.maximum(m2 - m1 * m1, 0))


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


# ------------------------------------------------------------------ strategies (one day -> trades)

def s1_trend_pullback(day, regime, e0, e1, flat, tp_r=1.5, hold=30):
    _, t, o, h, l, c, v = day
    e9 = ema(c, 9)
    out, k = [], 5
    while k < len(c) - 1:
        if not (e0 <= t[k] < e1):
            k += 1; continue
        side = regime[k - 1]
        sig = (side > 0 and l[k - 1] <= e9[k - 1] and c[k] > h[k - 1]) or \
              (side < 0 and h[k - 1] >= e9[k - 1] and c[k] < l[k - 1])
        if not sig:
            k += 1; continue
        j = k + 1
        en = o[j]
        sl = l[k - 4:k + 1].min() if side > 0 else h[k - 4:k + 1].max()
        risk = side * (en - sl)
        if risk <= 0:
            k += 1; continue
        ex, kx = walk(o, h, l, c, t, j, side, en, sl, en + side * tp_r * risk, hold, flat)
        out.append((side * (ex - en) / risk, risk / en))
        k = kx + 1
    return out


def s2_vwap_reversion(day, e0, e1, flat, kin=2.0, kout=3.0, hold=30):
    _, t, o, h, l, c, v = day
    vw, sd = vwap_sd(h, l, c, v)
    out, k, armed = [], 30, True
    while k < len(c):
        if not (e0 <= t[k] < e1) or sd[k - 1] <= 0:
            k += 1; continue
        lo_lim, hi_lim = vw[k - 1] - kin * sd[k - 1], vw[k - 1] + kin * sd[k - 1]
        if not armed:                                  # re-arm only once price is back inside the bands
            armed = lo_lim < c[k - 1] < hi_lim
            k += 1; continue
        side = 1 if l[k] < lo_lim else (-1 if h[k] > hi_lim else 0)
        if side == 0 or (l[k] < lo_lim and h[k] > hi_lim) or (side > 0 and o[k] < lo_lim) or (side < 0 and o[k] > hi_lim):
            k += 1; continue
        lim = lo_lim if side > 0 else hi_lim
        en = min(o[k], lim) if side > 0 else max(o[k], lim)
        sl = vw[k - 1] - side * kout * sd[k - 1]
        tp = vw[k - 1]
        risk = side * (en - sl)
        if risk <= 0 or side * (tp - en) <= 0:
            k += 1; continue
        ex, kx = walk(o, h, l, c, t, k, side, en, sl, tp, hold, flat, tp_on_first=False)
        out.append((side * (ex - en) / risk, risk / en))
        k, armed = kx + 1, False
    return out


def s3_vol_burst(day, e0, e1, flat, mult=3.0, tp_r=1.0, hold=15):
    _, t, o, h, l, c, v = day
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).rolling(20).mean().shift(1).to_numpy()
    out, k = [], 21
    while k < len(c) - 1:
        if not (e0 <= t[k] < e1) or np.isnan(atr[k]) or atr[k] <= 0:
            k += 1; continue
        rng = h[k] - l[k]
        if rng <= mult * atr[k]:
            k += 1; continue
        pos = (c[k] - l[k]) / rng
        side = 1 if pos >= 0.8 else (-1 if pos <= 0.2 else 0)
        if side == 0:
            k += 1; continue
        j = k + 1
        en = o[j]
        sl = l[k] if side > 0 else h[k]
        risk = side * (en - sl)
        if risk <= 0:
            k += 1; continue
        ex, kx = walk(o, h, l, c, t, j, side, en, sl, en + side * tp_r * risk, hold, flat)
        out.append((side * (ex - en) / risk, risk / en))
        k = kx + 1
    return out


# ------------------------------------------------------------------ Nasdaq regime (noise boundary)

def nasdaq_regimes(days):
    """Per day, per minute: +1 above the noise area, -1 below, 0 inside (needs 14 past sessions)."""
    moves, prev_close, out = [], None, {}
    for day in days:
        dt, t, o, h, l, c, v = day
        m = t - 570
        if m[0] != 0:
            moves.append(None); prev_close = c[-1]; continue
        o0 = o[0]
        mv = np.full(390, np.nan)
        mv[m[m < 390]] = np.abs(c[m < 390] / o0 - 1)
        mv = pd.Series(mv).ffill().to_numpy()
        hist = [x for x in moves[-14:] if x is not None]
        if len(hist) == 14 and prev_close is not None:
            sig = np.nanmean(np.vstack(hist), axis=0)[np.minimum(m, 389)]
            top, bot = max(o0, prev_close), min(o0, prev_close)
            out[dt] = np.where(c > top * (1 + sig), 1, np.where(c < bot * (1 - sig), -1, 0))
        moves.append(mv)
        prev_close = c[-1]
    return out


# ------------------------------------------------------------------ evaluation

def summarize(rows, cost):
    if not rows:
        return {"trades/jour": 0}
    df = pd.DataFrame(rows, columns=["day", "R", "risk"]).set_index("day")
    R = df["R"] - cost / df["risk"]
    span = lambda x: max(0.25, (x.index[-1] - x.index[0]).days / 365.25) if len(x) else 1.0
    pre, post = R[R.index.year < SPLIT], R[R.index.year >= SPLIT]
    eq = R.cumsum() * RISK
    days = R.index.nunique()
    return {"trades/jour": len(R) / max(1, len(set(R.index))) * days / max(1, days),
            "trades/an": len(R) / span(R), "gagnants": (R > 0).mean(), "R moyen": R.mean(),
            "PF": R[R > 0].sum() / -R[R < 0].sum() if (R < 0).any() else np.nan,
            "%/an": R.sum() * RISK / span(R),
            "%/an avant 2019": pre.sum() * RISK / span(pre) if len(pre) else np.nan,
            "%/an depuis 2019": post.sum() * RISK / span(post) if len(post) else np.nan,
            "pire baisse %": (eq - eq.cummax()).min(), "frais en R": (cost / df["risk"]).mean()}


def collect(days, fn, **kw):
    rows = []
    for day in days:
        for R, risk in fn(day, **kw):
            rows.append((day[0], R, risk))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--qqq"); ap.add_argument("--gold")
    a = ap.parse_args()
    results, grids = [], []

    if a.qqq:
        days = by_day(load_qqq(a.qqq), 570, 960)
        reg = nasdaq_regimes(days)
        rdays = [d for d in days if d[0] in reg]
        cost = 0.0001
        cands = {
            "S1 pullback dans la tendance": (lambda dd, **k: s1_trend_pullback(dd, reg[dd[0]], 600, 930, 959, **k), rdays,
                                             [dict(tp_r=x, hold=y) for x, y in itertools.product([1.0, 1.5, 2.0], [15, 30])]),
            "S2 retour au VWAP (limite)": (lambda dd, **k: s2_vwap_reversion(dd, 600, 930, 959, **k), days,
                                           [dict(kin=x, kout=x + 1, hold=y) for x, y in itertools.product([1.5, 2.0, 2.5], [15, 30])]),
            "S3 explosion de volatilité": (lambda dd, **k: s3_vol_burst(dd, 600, 930, 959, **k), days,
                                           [dict(mult=x, tp_r=y) for x, y in itertools.product([2.5, 3.0, 4.0], [1.0, 2.0])]),
        }
        for name, (fn, dd, grid) in cands.items():
            rows = collect(dd, fn)
            for cname, cc in (("sans frais", 0.0), ("réels 0,01 %", cost), ("x3", 3 * cost)):
                results.append({"marché": "Nasdaq", "scalp": name, "frais": cname, **summarize(rows, cc)})
            g = [summarize(collect(dd, fn, **kw), cost).get("%/an", np.nan) for kw in grid]
            grids.append(f"Nasdaq {name}: {sum(x > 0 for x in g)}/{len(g)} variantes positives, médiane {np.nanmedian(g):+.1f} %/an")

    if a.gold:
        days = by_day(load_gold(a.gold), 180, 720)
        cost = 0.00007
        cands = {
            "S2 retour au VWAP (limite)": (lambda dd, **k: s2_vwap_reversion(dd, 210, 690, 719, **k),
                                           [dict(kin=x, kout=x + 1, hold=y) for x, y in itertools.product([1.5, 2.0, 2.5], [15, 30])]),
            "S3 explosion de volatilité": (lambda dd, **k: s3_vol_burst(dd, 210, 690, 719, **k),
                                           [dict(mult=x, tp_r=y) for x, y in itertools.product([2.5, 3.0, 4.0], [1.0, 2.0])]),
        }
        for name, (fn, grid) in cands.items():
            rows = collect(days, fn)
            for cname, cc in (("sans frais", 0.0), ("ECN 0,007 %", cost), ("x3", 3 * cost)):
                results.append({"marché": "Or", "scalp": name, "frais": cname, **summarize(rows, cc)})
            g = [summarize(collect(days, fn, **kw), cost).get("%/an", np.nan) for kw in grid]
            grids.append(f"Or {name}: {sum(x > 0 for x in g)}/{len(g)} variantes positives, médiane {np.nanmedian(g):+.1f} %/an")

    df = pd.DataFrame(results).drop(columns=["trades/jour"], errors="ignore")
    df["gagnants"] = df["gagnants"].map(lambda x: f"{x:.0%}")
    print(df.round(2).to_string(index=False))
    print("\nGrilles (frais réels) :")
    print("\n".join("  " + g for g in grids))

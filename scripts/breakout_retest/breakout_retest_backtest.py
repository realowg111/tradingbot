"""Backtest of the "breakout and retest" day-trading setup (TikTok @theagtg.micah, Nasdaq futures).

Rules as stated in the video (short side; the long side is the mirror on a resistance):
  1. Support: a level the candles bounced from at least 3 times.
  2. Breakout: price closes below the support.
  3. No entry on the breakout: wait for the return (retest) of price up to the same level.
  4. Entry when price turns down again at the retest, on a strong bearish engulfing candle.
     Stop above the retest high, target the lows (here: 2 R, then a grid).

Mechanical version (each choice is varied in the grid):
  - Swing lows/highs: bar whose low/high is the extreme of +-3 bars (known 3 bars later).
  - A support exists once 3 swing lows within 0.25 ATR(14) of each other appear in the last
    120 bars of the same session; its level is their average.
  - Breakout: a close below the level minus 0.1 ATR. Retest: within the next 30 bars, a high
    back within 0.25 ATR of the level; the setup dies if a close comes back above level + 0.5 ATR.
  - Signal: bearish engulfing (red candle whose body covers the previous green body) during the
    retest. Entry at the next bar open; stop = highest high since the breakout + 0.05 ATR;
    target 2 R; one position at a time; everything closed at the end of the session.

Sessions (New York time): Nasdaq 09:30-16:00; gold and EURUSD 03:00-16:55.
Results in R; with 1 % risk per trade the yearly % return is the yearly sum of R.

Usage: python3 breakout_retest_backtest.py --qqq qqq.parquet --gold <HistData raw> --eurusd <OANDA raw>
"""
import argparse, itertools, os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nine_am_cr"))
from nine_am_cr_backtest import load_qqq, load_gold, load_eurusd   # noqa: E402

SPLIT = 2019


def resample(d, minutes):
    if minutes == 1:
        return d
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return d.resample(f"{minutes}min", label="left", closed="left").agg(agg).dropna()


def session_trades(o, h, l, c, atr, swl, swh, k=3, touches=3, window=120, tol=0.25, brk=0.1,
                   retest_bars=30, inval=0.5, target_r=2.0):
    """All trades of one session. swl/swh: bool arrays (swing low/high at bar i, known at i+k)."""
    n, out = len(c), []
    lows, highs = [], []                              # (bar, price) of confirmed swings
    sup = res = None                                  # active levels
    setup = None                                      # (side, level, t_break, extreme)
    pos = None                                        # (side, entry, stop, target)
    for i in range(1, n):
        a = atr[i]
        if np.isnan(a) or a <= 0:
            continue
        # manage an open position first
        if pos is not None:
            side, en, st, tg = pos
            if (side < 0 and h[i] >= st) or (side > 0 and l[i] <= st):
                ex = (max(o[i], st) if side < 0 else min(o[i], st))
                out.append(side * (ex - en) / (side * (en - st))); pos = None
            elif (side < 0 and l[i] <= tg) or (side > 0 and h[i] >= tg):
                out.append(target_r); pos = None
            if pos is not None:
                continue
        # confirm swings (bar i-k becomes a swing once k bars passed)
        j = i - k
        if j >= 0:
            if swl[j]:
                lows.append((j, l[j]))
                near = [p for b, p in lows if i - b <= window and abs(p - l[j]) <= tol * a]
                if len(near) >= touches:
                    sup = float(np.mean(near))
            if swh[j]:
                highs.append((j, h[j]))
                near = [p for b, p in highs if i - b <= window and abs(p - h[j]) <= tol * a]
                if len(near) >= touches:
                    res = float(np.mean(near))
        # breakouts start a setup
        if setup is None:
            if sup is not None and c[i] < sup - brk * a:
                setup, sup = [-1, sup, i, h[i]], None
            elif res is not None and c[i] > res + brk * a:
                setup, res = [1, res, i, l[i]], None
            continue
        side, lvl, tb, ext = setup
        setup[3] = ext = max(ext, h[i]) if side < 0 else min(ext, l[i])
        if i - tb > retest_bars or side * (lvl - c[i]) > inval * a:        # expired or reclaimed
            setup = None
            continue
        touched = (h[i] >= lvl - tol * a) if side < 0 else (l[i] <= lvl + tol * a)
        engulf = (c[i] < o[i] and c[i - 1] > o[i - 1] and o[i] >= c[i - 1] and c[i] <= o[i - 1]) if side < 0 else \
                 (c[i] > o[i] and c[i - 1] < o[i - 1] and o[i] <= c[i - 1] and c[i] >= o[i - 1])
        if touched and engulf and i + 1 < n:
            en = o[i + 1]
            st = ext + 0.05 * a if side < 0 else ext - 0.05 * a
            risk = side * (en - st)
            if risk > 0:
                pos = (side, en, st, en + side * target_r * risk)
                out_risk = risk / en
                out.append(("open", out_risk))
            setup = None
    if pos is not None:
        side, en, st, tg = pos
        out.append(side * (c[-1] - en) / (side * (en - st)))
    # pair each ("open", risk) marker with the result that follows it
    res_, risk = [], None
    for x in out:
        if isinstance(x, tuple):
            risk = x[1]
        elif risk is not None:
            res_.append((x, risk)); risk = None
    return res_


def run(d, minutes, start, end, **kw):
    b = resample(d, minutes)
    t = (b.index.hour * 60 + b.index.minute).to_numpy()
    b = b[(t >= start) & (t < end) & (b.index.dayofweek < 5)]
    o, h, l, c = (b[x].to_numpy() for x in ("open", "high", "low", "close"))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    k = 3
    lo_ext = pd.Series(l).rolling(2 * k + 1, center=True).min().to_numpy()
    hi_ext = pd.Series(h).rolling(2 * k + 1, center=True).max().to_numpy()
    swl, swh = (l == lo_ext), (h == hi_ext)
    day = b.index.normalize()
    bounds = np.flatnonzero(np.r_[True, day[1:] != day[:-1], True])
    rows = []
    for a_, z in zip(bounds[:-1], bounds[1:]):
        if z - a_ < 20:
            continue
        for R, risk in session_trades(o[a_:z], h[a_:z], l[a_:z], c[a_:z], atr[a_:z], swl[a_:z], swh[a_:z], **kw):
            rows.append((day[a_], R, risk))
    return pd.DataFrame(rows, columns=["day", "R", "risk"]).set_index("day")


def summarize(tr, cost):
    if len(tr) == 0:
        return {"trades/an": 0}
    R = tr["R"] - cost / tr["risk"]
    span = lambda x: max(0.5, (x.index[-1] - x.index[0]).days / 365.25) if len(x) else 1.0
    pre, post = R[R.index.year < SPLIT], R[R.index.year >= SPLIT]
    y = R.groupby(R.index.year).sum()
    eq = R.cumsum()
    return {"trades/an": len(R) / span(R), "gagnants": (R > 0).mean(), "R moyen": R.mean(),
            "%/an (1 % risque)": R.sum() / span(R), "avant 2019": pre.sum() / span(pre) if len(pre) else np.nan,
            "depuis 2019": post.sum() / span(post) if len(post) else np.nan,
            "pire repli (R)": (eq - eq.cummax()).min(), "années +": f"{(y > 0).sum()}/{len(y)}",
            "stop (% prix)": tr["risk"].mean() * 100}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--qqq"); ap.add_argument("--gold"); ap.add_argument("--eurusd")
    a = ap.parse_args()
    markets = []
    if a.qqq: markets.append(("Nasdaq", load_qqq(a.qqq), 570, 960, {"sans frais": 0, "futures/CFD 0,005 %": 0.00005, "0,01 %": 0.0001}))
    if a.gold: markets.append(("Or", load_gold(a.gold), 180, 1015, {"sans frais": 0, "ECN 0,007 %": 0.00007, "standard 0,02 %": 0.0002}))
    if a.eurusd: markets.append(("EUR/USD", load_eurusd(a.eurusd), 180, 1015, {"sans frais": 0, "ECN 0,007 %": 0.00007}))

    rows = []
    for name, d, s, e, costs in markets:
        real = list(costs.values())[1]
        for tf in (1, 5):
            tr = run(d, tf, s, e)
            for cname, cost in costs.items():
                rows.append({"marché": f"{name} {tf} min", "frais": cname, **summarize(tr, cost)})
            yr = (tr["R"] - real / tr["risk"]).groupby(tr.index.year).sum()
            print(f"{name} {tf} min, par année (frais réalistes) : " + " ".join(f"{k}:{v:+.0f}" for k, v in yr.items()))
        grid = []
        for tch, tol, tgt, rb in itertools.product([2, 3], [0.15, 0.25, 0.5], [1.0, 2.0, 3.0], [15, 30]):
            g = summarize(run(d, 5, s, e, touches=tch, tol=tol, target_r=tgt, retest_bars=rb), real)
            grid.append(g.get("%/an (1 % risque)", 0))
        g = np.array(grid)
        print(f"  grille 36 variantes en 5 min (frais réalistes) : médiane {np.median(g):+.1f} %/an, "
              f"positives {int((g > 0).sum())}/36, min {g.min():+.1f}, max {g.max():+.1f}\n")
    df = pd.DataFrame(rows)
    df["gagnants"] = df["gagnants"].map(lambda x: f"{x:.0%}")
    print(df.round(2).to_string(index=False))

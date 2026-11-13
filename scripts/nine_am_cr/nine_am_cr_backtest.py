"""Backtest of the "9am CR model" (TikTok @massimotsr), on 1-minute bars, New York time.

Rules as stated in the video:
  1. Mark the high and low of the 08:00-09:00 one-hour candle.
  2. If the 09:00 hourly candle hits the 08:00 high first -> look for a short, target the 08:00 low.
     If it hits the 08:00 low first -> look for a long, target the 08:00 high.
  3. Entry on the 1-minute chart once both signatures appear after the sweep:
     - IFVG: a candle closes beyond the far edge of a fair value gap that went the other way
       (short: closes below the bottom of a bullish FVG, low[i] > high[i-2]);
     - order block: a down-close candle closes below the last up-close candle (mirror for longs).
     Entry at the next minute's open.
  4. Stop at the swing high made since the sweep (swing low for longs), target the other side
     of the 08:00 candle. One trade per day.

Choices the video leaves open (defaults, then a grid): the setup must trigger before 10:00
(the "next hourly candle"); the FVG must have formed within the last 30 minutes; "closes below
the up-close candle" = below its low; trades not finished are closed at 16:00 New York.
If stop and target sit in the same minute the stop wins. Results are in R (1 R = the stop
distance); with 1 % risk per trade, the yearly return in % is the yearly sum of R.

Usage: python3 nine_am_cr_backtest.py --qqq qqq.parquet --gold <HistData raw dir> --eurusd <OANDA raw dir>
"""
import argparse, glob, itertools, os, sys
import numpy as np, pandas as pd

SPLIT = 2019


# ---------------------------------------------------------------- loaders (1-minute, NY time, naive)

def load_qqq(path):
    d = pd.read_parquet(path)
    d.index = pd.to_datetime(d.pop("Timestamp"))          # already New York time
    d.columns = [c.lower() for c in d.columns]
    return d[["open", "high", "low", "close"]]


def load_gold(raw):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xau_daytrade"))
    from prepare_data import load_m1
    d = load_m1(raw)
    d.index = d.index.tz_localize(None)
    return d


def load_eurusd(raw):
    parts = []
    for f in sorted(glob.glob(os.path.join(raw, "*.parquet"))):
        x = pd.read_parquet(f)
        x.index = pd.DatetimeIndex(pd.to_datetime(x.pop("time"), unit="s", utc=True)).tz_convert("America/New_York").tz_localize(None)
        parts.append(x[["open", "high", "low", "close"]])
    d = pd.concat(parts).sort_index()
    return d[~d.index.duplicated()]


# ---------------------------------------------------------------- strategy

def day_trade(t, o, h, l, c, deadline=600, fvg_lookback=30, ob_level="low", exit_t=960, min_rr=0.0):
    """t = minutes since midnight for one day's bars (sorted). Returns (R_gross, risk_frac) or None."""
    in8 = (t >= 480) & (t < 540)
    if in8.sum() < 30:
        return None
    H8, L8 = h[in8].max(), l[in8].min()
    if H8 <= L8:
        return None
    start = np.searchsorted(t, 540)
    side, sweep = 0, None
    for i in range(start, len(t)):
        if t[i] >= deadline:
            return None
        if side == 0:
            up, dn = h[i] >= H8, l[i] <= L8
            if up and dn:
                return None
            if up or dn:
                side, sweep = (-1 if up else 1), i       # sweep of the high -> short
            else:
                continue
        # signatures on the close of bar i (bar i may be the sweep bar itself)
        lo_i = max(2, i - fvg_lookback)
        if side < 0:
            fvg = [h[k - 2] for k in range(lo_i, i) if l[k] > h[k - 2]]            # bullish FVG bottoms
            ups = [k for k in range(i - 1, max(0, i - fvg_lookback) - 1, -1) if c[k] > o[k]]
            if not fvg or not ups or c[i] >= o[i]:
                continue
            ob = l[ups[0]] if ob_level == "low" else o[ups[0]]
            if not (c[i] < fvg[-1] and c[i] < ob):
                continue
            stop, target = h[sweep:i + 1].max(), L8
        else:
            fvg = [l[k - 2] for k in range(lo_i, i) if h[k] < l[k - 2]]            # bearish FVG tops
            dns = [k for k in range(i - 1, max(0, i - fvg_lookback) - 1, -1) if c[k] < o[k]]
            if not fvg or not dns or c[i] <= o[i]:
                continue
            ob = h[dns[0]] if ob_level == "low" else o[dns[0]]
            if not (c[i] > fvg[-1] and c[i] > ob):
                continue
            stop, target = l[sweep:i + 1].min(), H8
        j = i + 1
        if j >= len(t) or t[j] >= exit_t:
            return None
        en = o[j]
        risk = side * (en - stop)
        if risk <= 0 or side * (target - en) <= min_rr * risk:
            return None
        for k in range(j, len(t)):
            if t[k] >= exit_t:
                return side * (c[k - 1] - en) / risk, risk / en
            if (side < 0 and h[k] >= stop) or (side > 0 and l[k] <= stop):
                ex = stop if k == j else (max(o[k], stop) if side < 0 else min(o[k], stop))
                return side * (ex - en) / risk, risk / en
            if (side < 0 and l[k] <= target) or (side > 0 and h[k] >= target):
                return side * (target - en) / risk, risk / en
        return side * (c[-1] - en) / risk, risk / en
    return None


def run(d, **kw):
    t_all = (d.index.hour * 60 + d.index.minute).to_numpy()
    day = d.index.normalize()
    keep = (t_all >= 480) & (t_all < 1020)
    d, t_all, day = d[keep], t_all[keep], day[keep]
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    bounds = np.flatnonzero(np.r_[True, day[1:] != day[:-1], True])
    rows = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if day[a].dayofweek >= 5:
            continue
        r = day_trade(t_all[a:b], o[a:b], h[a:b], l[a:b], c[a:b], **kw)
        if r is not None:
            rows.append((day[a], *r))
    return pd.DataFrame(rows, columns=["day", "R", "risk"]).set_index("day")


def summarize(tr, cost):
    R = tr["R"] - cost / tr["risk"]                     # cost in % of price -> in R
    y = R.groupby(R.index.year).sum()
    pre, post = R[R.index.year < SPLIT], R[R.index.year >= SPLIT]
    eq = R.cumsum()
    span = lambda x: max(0.5, (x.index[-1] - x.index[0]).days / 365.25) if len(x) else 1.0
    return {"trades/an": len(R) / span(R), "gagnants": (R > 0).mean(), "R moyen": R.mean(),
            "PF": R[R > 0].sum() / -R[R < 0].sum() if (R < 0).any() else np.nan,
            "%/an à 1 % de risque": R.sum() / span(R), "avant 2019": pre.sum() / span(pre),
            "depuis 2019": post.sum() / span(post),
            "pire repli (R)": (eq - eq.cummax()).min(), "années +": f"{(y > 0).sum()}/{len(y)}",
            "stop moyen (% prix)": tr["risk"].mean() * 100}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--qqq"); ap.add_argument("--gold"); ap.add_argument("--eurusd")
    a = ap.parse_args()
    markets = []
    if a.qqq: markets.append(("Nasdaq (QQQ)", load_qqq(a.qqq), {"sans frais": 0, "courtier/CFD 0,01 %": 0.0001}))
    if a.gold: markets.append(("Or (XAUUSD)", load_gold(a.gold), {"sans frais": 0, "ECN 0,007 %": 0.00007, "standard 0,02 %": 0.0002}))
    if a.eurusd: markets.append(("EUR/USD", load_eurusd(a.eurusd), {"sans frais": 0, "ECN 0,007 %": 0.00007, "standard 0,012 %": 0.00012}))

    rows = []
    for name, d, costs in markets:
        tr = run(d)
        print(f"{name}: {d.index[0].date()} -> {d.index[-1].date()}, {len(tr)} trades")
        for cname, cost in costs.items():
            rows.append({"marché": name, "frais": cname, **summarize(tr, cost)})
        yr = (tr["R"] - list(costs.values())[1] / tr["risk"]).groupby(tr.index.year).sum()
        print("  par année (%, 1 % de risque, frais réalistes) : " + " ".join(f"{k}:{v:+.0f}" for k, v in yr.items()))
        grid = []
        for dl, lb, obl, ex in itertools.product([600, 660], [15, 30, 60], ["low", "open"], [720, 960]):
            g = summarize(run(d, deadline=dl, fvg_lookback=lb, ob_level=obl, exit_t=ex), list(costs.values())[1])
            grid.append(g["%/an à 1 % de risque"])
        g = np.array(grid)
        print(f"  grille 24 variantes (frais réalistes) : médiane {np.median(g):+.1f} %/an, positives {int((g > 0).sum())}/24, "
              f"min {g.min():+.1f}, max {g.max():+.1f}\n")
    df = pd.DataFrame(rows)
    df["gagnants"] = df["gagnants"].map(lambda x: f"{x:.0%}")
    print(df.round(2).to_string(index=False))

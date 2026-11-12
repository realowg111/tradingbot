"""Day-trading strategies on XAUUSD, 5-minute bars, 2009-2026 (HistData via prepare_data.py).

Every strategy is flat by 16:55 New York time (no overnight swap). Default parameters are fixed
before looking at results (values from the source papers or the usual practitioner settings);
a sensitivity grid around them is reported separately.

  A. ORB first bar (Zarattini & Aziz 2023): direction of the first bar after the open, stop at the
     other end of that bar, target 10R, else exit at the close.
  B. Asian range breakout: range 18:00-03:00 ET, stop order on either side from 03:00 to 11:00,
     stop at the middle of the range, target 2R.
  C. Noise-boundary intraday momentum (Zarattini, Aziz & Barbon 2024, "Beat the Market"):
     long above open*(1+sigma), short below open*(1-sigma), sigma = mean absolute move from the
     open at that time of day over the last 14 sessions; checked every 30 minutes.
  D. Intraday momentum (Gao, Han, Li & Zhou 2018; Baltussen et al. 2021): the return since the
     18:00 session open predicts the 13:00-13:30 ET window before the COMEX gold settlement.

Execution: signals on a bar close are filled at the next bar open; stop orders fill at the level
(or the open if it gaps through); if stop and target are both inside one bar the stop wins.
Costs: a round-trip cost in % of price (spread + slippage), base 0.02 %, stress 0.06 %.
Sizing: notional = min(4, 1 % / gold's 20-day daily volatility) x equity, set each day.

Usage: python3 xau_daytrade_backtest.py [path/to/xau_5m.pkl]
"""
import itertools, os, sys
import numpy as np, pandas as pd

COST = 0.0002     # ~0.80 $ per round trip at 3 900 $: retail CFD spread + slippage
ECN = 0.00007     # ~0.25 $: raw-spread ECN account with commission
STRESS = 0.0006
SPLIT = "2018-01-01"
FLAT = "16:55"


def sm(hhmm):
    """Clock time in New York -> minutes since the 18:00 session open."""
    h, m = map(int, hhmm.split(":"))
    return (h * 60 + m - 18 * 60) % 1440


def load(path):
    d = pd.read_pickle(path)
    t = d.index.hour * 60 + d.index.minute
    d["sm"] = (t - 18 * 60) % 1440
    d["day"] = (d.index + pd.Timedelta(hours=6)).date   # session day starts 18:00 the evening before
    days = {}
    for k, g in d.groupby("day", sort=True):
        if len(g) < 200:                                  # skip holidays / half sessions
            continue
        days[pd.Timestamp(k)] = tuple(g[c].to_numpy() for c in ("sm", "open", "high", "low", "close"))
    return days


def first_at(s, t):
    i = np.searchsorted(s, t)
    return i if i < len(s) else None


def last_before(s, t):
    i = np.searchsorted(s, t, side="right") - 1
    return i if i >= 0 else None


def walk(o, h, l, c, i0, i1, side, entry, stop, target):
    """Exit price of a trade entered on bar i0, forced out at the close of bar i1."""
    for j in range(i0, i1 + 1):
        if side > 0:
            if l[j] <= stop:
                return o[j] if (j > i0 and o[j] < stop) else stop
            if target is not None and h[j] >= target:
                return target
        else:
            if h[j] >= stop:
                return o[j] if (j > i0 and o[j] > stop) else stop
            if target is not None and l[j] <= target:
                return target
    return c[i1]


# ---------------------------------------------------------------- strategies (one day -> list of trades)
# A trade is (side, entry, exit). Returns are computed afterwards so costs can change.

def orb_first_bar(day, open_t="08:20", bar_min=5, target_r=10):
    s, o, h, l, c = day
    t0, t1 = sm(open_t), sm(open_t) + bar_min
    i_end = last_before(s, sm(FLAT))
    rng = (s >= t0) & (s < t1)
    if rng.sum() < bar_min // 5 or i_end is None:
        return []
    idx = np.flatnonzero(rng)
    op, cl, hi, lo = o[idx[0]], c[idx[-1]], h[idx].max(), l[idx].min()
    if cl == op:
        return []
    side = 1 if cl > op else -1
    i0 = idx[-1] + 1
    if i0 > i_end:
        return []
    entry, stop = o[i0], (lo if side > 0 else hi)
    risk = side * (entry - stop)
    if risk <= 0:
        return []
    target = entry + side * target_r * risk if target_r else None
    return [(side, entry, walk(o, h, l, c, i0, i_end, side, entry, stop, target))]


def asian_breakout(day, range_end="03:00", last_entry="11:00", stop_mode="mid", target_r=2.0):
    s, o, h, l, c = day
    r = s < sm(range_end)
    i_end = last_before(s, sm(FLAT))
    if r.sum() < 60 or i_end is None:
        return []
    hi, lo = h[r].max(), l[r].min()
    mid = (hi + lo) / 2
    for j in np.flatnonzero((s >= sm(range_end)) & (s < sm(last_entry))):
        up, dn = h[j] > hi, l[j] < lo
        if up and dn:
            return []
        if up or dn:
            side = 1 if up else -1
            entry = max(o[j], hi) if up else min(o[j], lo)
            stop = mid if stop_mode == "mid" else (lo if up else hi)
            risk = side * (entry - stop)
            target = entry + side * target_r * risk if target_r else None
            return [(side, entry, walk(o, h, l, c, j, i_end, side, entry, stop, target))]
    return []


def noise_boundary(days, open_t="08:20", lookback=14, every=30):
    """Needs the history of previous days, so it runs over all days at once. Returns {day: trades}."""
    t0, tf = sm(open_t), sm(FLAT)
    grid = np.arange(t0, tf + 5, 5)                       # 5-minute grid from the open to the flat time
    moves, out = [], {}
    for k, (s, o, h, l, c) in days.items():
        pos = np.searchsorted(s, grid)
        ok = (pos < len(s)) & (s[np.minimum(pos, len(s) - 1)] == grid)
        if not ok[0]:
            moves.append(None)
            out[k] = []
            continue
        i_open = pos[0]
        ref = o[i_open]
        closes = np.full(len(grid), np.nan)
        closes[ok] = c[pos[ok]]
        hist = [m for m in moves[-lookback:] if m is not None and not np.isnan(m).all()]
        moves.append(np.abs(closes / ref - 1))
        trades = []
        if len(hist) == lookback:
            sigma = np.nanmean(np.vstack(hist), axis=0)
            i_end = last_before(s, tf)
            side, entry = 0, None
            for g in range(every // 5 - 1, len(grid) - 1, every // 5):   # decision on the close of each block
                if not ok[g] or np.isnan(sigma[g]):
                    continue
                x = closes[g]
                want = 1 if x > ref * (1 + sigma[g]) else (-1 if x < ref * (1 - sigma[g]) else 0)
                if want != side:
                    j = pos[g] + 1
                    if j > i_end:
                        break
                    if side:
                        trades.append((side, entry, o[j]))
                    side, entry = want, (o[j] if want else None)
            if side:
                trades.append((side, entry, c[i_end]))
        out[k] = trades
    return out


def intraday_momentum(day, sig_start="18:00", sig_end="13:00", exit_t="13:30"):
    s, o, h, l, c = day
    a, b, e = first_at(s, sm(sig_start)), last_before(s, sm(sig_end) - 5), last_before(s, sm(exit_t) - 5)
    if a is None or b is None or e is None or e <= b + 1 or s[b] != sm(sig_end) - 5:
        return []
    r = c[b] / o[a] - 1
    if r == 0:
        return []
    side = 1 if r > 0 else -1
    return [(side, o[b + 1], c[e])]


# ---------------------------------------------------------------- evaluation

def daily_close(days):
    idx = list(days)
    return pd.Series([d[4][last_before(d[0], sm(FLAT))] for d in days.values()], index=idx)


def returns(trades_by_day, closes, cost):
    vol = closes.pct_change().rolling(20).std().shift(1)
    lev = (0.01 / vol).clip(upper=4).fillna(0)
    pnl, rows = pd.Series(0.0, index=closes.index), []
    for k, trades in trades_by_day.items():
        for side, en, ex in trades:
            r = side * (ex / en - 1) - cost
            rows.append((k, r))
            pnl[k] += lev[k] * r
    tr = pd.DataFrame(rows, columns=["day", "r"]).set_index("day")["r"] if rows else pd.Series(dtype=float)
    return pnl, tr


def stats(pnl, tr):
    if len(pnl) < 20:
        return {}
    eq = (1 + pnl).cumprod()
    yrs = (pnl.index[-1] - pnl.index[0]).days / 365.25
    sd = pnl.std()
    win, loss = tr[tr > 0].sum(), -tr[tr < 0].sum()
    return {"trades/an": len(tr) / yrs, "gagnants": (tr > 0).mean() if len(tr) else np.nan,
            "PF": win / loss if loss > 0 else np.nan, "moy. trade (pb)": tr.mean() * 1e4 if len(tr) else np.nan,
            "CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "max DD": (eq / eq.cummax() - 1).min(),
            "Sharpe": pnl.mean() / sd * np.sqrt(252) if sd > 0 else 0.0}


def run_all(name, trades_by_day, closes):
    pnl, tr = returns(trades_by_day, closes, COST)
    full, is_, oos = stats(pnl, tr), stats(pnl[:SPLIT], tr[:SPLIT]), stats(pnl[SPLIT:], tr[SPLIT:])
    sh = {c: stats(*returns(trades_by_day, closes, c))["Sharpe"] for c in (0.0, ECN, STRESS)}
    row = {"stratégie": name, **full, "Sharpe 09-17": is_["Sharpe"], "Sharpe 18-26": oos["Sharpe"],
           "CAGR 18-26": oos["CAGR"], "Sharpe sans frais": sh[0.0], "Sharpe ECN": sh[ECN], "Sharpe frais x3": sh[STRESS]}
    yearly = (1 + pnl).groupby(pnl.index.year).prod() - 1
    return row, yearly, pnl


def per_day(fn, days, **kw):
    return {k: fn(d, **kw) for k, d in days.items()}


STRATS = {
    "A. ORB 1re bougie 08:20": lambda days: per_day(orb_first_bar, days),
    "B. Cassure range asiatique": lambda days: per_day(asian_breakout, days),
    "C. Noise boundary 08:20": lambda days: noise_boundary(days),
    "D. Momentum intraday 13:00": lambda days: per_day(intraday_momentum, days),
}

GRIDS = {
    "A": (lambda days, t, b, r: per_day(orb_first_bar, days, open_t=t, bar_min=b, target_r=r),
          list(itertools.product(["03:00", "08:20", "09:30"], [5, 15, 30], [2, 10, None]))),
    "B": (lambda days, e, sm_, r: per_day(asian_breakout, days, range_end=e, stop_mode=sm_, target_r=r),
          list(itertools.product(["02:00", "03:00", "04:00"], ["mid", "opp"], [1.0, 2.0, None]))),
    "C": (lambda days, t, lb, ev: noise_boundary(days, open_t=t, lookback=lb, every=ev),
          list(itertools.product(["03:00", "08:20", "09:30"], [10, 14, 20], [15, 30, 60]))),
    "D": (lambda days, a, w: per_day(intraday_momentum, days, sig_start=a, sig_end=w[0], exit_t=w[1]),
          list(itertools.product(["18:00", "08:20"], [("13:00", "13:30"), ("12:30", "13:30"), ("15:30", "16:55"), ("16:00", "16:55")])))
}


def fmt(df):
    df = df.copy()
    for col in df.columns:
        if col in ("gagnants", "CAGR", "max DD", "CAGR 18-26"):
            df[col] = df[col].map(lambda x: f"{x:+.1%}" if col != "gagnants" else f"{x:.0%}")
        elif df[col].dtype.kind == "f":
            df[col] = df[col].map(lambda x: f"{x:.2f}")
    return df.to_string(index=False)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "data", "xau_5m.pkl")
    days = load(path)
    closes = daily_close(days)
    print(f"{len(days)} séances, {closes.index[0].date()} -> {closes.index[-1].date()}\n")

    rows, years = [], {}
    bh = closes.pct_change().fillna(0)
    rows.append({"stratégie": "Achat-conservation or", **stats(bh, pd.Series(dtype=float)),
                 "Sharpe 09-17": stats(bh[:SPLIT], pd.Series(dtype=float))["Sharpe"],
                 "Sharpe 18-26": stats(bh[SPLIT:], pd.Series(dtype=float))["Sharpe"],
                 "CAGR 18-26": stats(bh[SPLIT:], pd.Series(dtype=float))["CAGR"]})
    for name, fn in STRATS.items():
        row, yearly, _ = run_all(name, fn(days), closes)
        rows.append(row)
        years[name.split(".")[0]] = yearly
    print(fmt(pd.DataFrame(rows)))
    print("\nRendement par année (taille ~1x le notionnel):")
    print(pd.DataFrame(years).map(lambda x: f"{x:+.1%}").to_string())

    print("\nSensibilité aux paramètres (Sharpe par configuration, frais de base):")
    for key, (fn, grid) in GRIDS.items():
        res = []
        for g in grid:
            pnl, tr = returns(fn(days, *g), closes, COST)
            res.append((g, stats(pnl[:SPLIT], tr[:SPLIT])["Sharpe"], stats(pnl[SPLIT:], tr[SPLIT:])["Sharpe"]))
        a = np.array([[r[1], r[2]] for r in res])
        print(f"  {key}: {len(grid)} configs | 09-17 médiane {np.median(a[:, 0]):+.2f}, positives {int((a[:, 0] > 0).sum())}"
              f" | 18-26 médiane {np.median(a[:, 1]):+.2f}, positives {int((a[:, 1] > 0).sum())}")
        best = max(res, key=lambda r: r[1])
        print(f"     meilleure config sur 09-17 {best[0]}: Sharpe 09-17 {best[1]:+.2f} -> 18-26 {best[2]:+.2f}")

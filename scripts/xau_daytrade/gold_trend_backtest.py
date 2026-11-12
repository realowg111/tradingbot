"""Trend-following robots on gold (XAUUSD), daily closes 2009-2026 built from the 5-minute data.

Positions last days to weeks, so the CFD swap matters and is charged on every day held.
Parameters are textbook values fixed before looking at results; a grid shows the sensitivity.

  1. TSMOM (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017): signal = average sign
     of the 1, 3, 6 and 12-month returns, volatility-targeted, decided on Friday's close.
  2. SMA 50/200: long when the 50-day average is above the 200-day one, flat otherwise.
  3. Donchian 55/20 (Turtle rules): long on a 55-day high, out on a 20-day low (short the mirror).

Costs: 0.02 % of the traded notional + swap 0.01 %/day on the held notional (stress: 0.06 % and
0.03 %/day). Trades happen at the next day's close after the signal (no look-ahead).

Usage: python3 gold_trend_backtest.py [path/to/xau_5m.pkl] [chart.png]
"""
import itertools, os, sys
import numpy as np, pandas as pd

SPLIT = "2018-01-01"
BASE, STRESS = (0.0002, 0.0001), (0.0006, 0.0003)


def daily(path):
    d = pd.read_pickle(path)
    day = (d.index + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    c = d["close"].groupby(day).last()
    n = d["close"].groupby(day).size()
    return c[n >= 200]


def run(px, w, costs=BASE):
    fee, swap = costs
    r = px.pct_change().fillna(0)
    held = w.shift(1).fillna(0)                      # decided at close t, earns from t to t+1
    turn = w.diff().abs().fillna(w.abs()).shift(1).fillna(0)
    days = px.index.to_series().diff().dt.days.fillna(1).clip(upper=4)   # weekend swap
    net = held * r - turn * fee - held.abs() * swap * days
    return net


def stats(net):
    net = net[net.ne(0).cummax()]
    yrs = (net.index[-1] - net.index[0]).days / 365.25
    eq = (1 + net).cumprod()
    yearly = (1 + net).groupby(net.index.year).prod() - 1
    return {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "max DD": (eq / eq.cummax() - 1).min(),
            "Sharpe": net.mean() / net.std() * np.sqrt(252), "années +": f"{(yearly > 0).sum()}/{len(yearly)}",
            "pire année": yearly.min()}


def vol_scale(px, target=0.15, n=60, cap=2.0):
    v = px.pct_change().rolling(n).std() * np.sqrt(252)
    return (target / v).clip(upper=cap)


def weekly(w, px):
    """Hold Friday's decision for the whole following week."""
    fri = px.index.dayofweek == 4
    return w.where(fri).ffill().fillna(0)


def tsmom(px, lookbacks=(21, 63, 126, 252), long_only=True, target=0.15):
    sig = sum(np.sign(px / px.shift(n) - 1) for n in lookbacks) / len(lookbacks)
    if long_only:
        sig = sig.clip(lower=0)
    return weekly((sig * vol_scale(px, target)).fillna(0), px)


def sma_cross(px, fast=50, slow=200):
    return (px.rolling(fast).mean() > px.rolling(slow).mean()).astype(float)


def donchian(px, entry=55, exit_=20, long_only=True):
    hi_e, lo_e = px.rolling(entry).max().shift(1), px.rolling(entry).min().shift(1)
    hi_x, lo_x = px.rolling(exit_).max().shift(1), px.rolling(exit_).min().shift(1)
    pos, out = 0.0, []
    for p, he, le, hx, lx in zip(px, hi_e, lo_e, hi_x, lo_x):
        if pos > 0 and p < lx: pos = 0.0
        if pos < 0 and p > hx: pos = 0.0
        if pos == 0 and p > he: pos = 1.0
        if pos == 0 and p < le and not long_only: pos = -1.0
        out.append(pos)
    return pd.Series(out, index=px.index)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "data", "xau_5m.pkl")
    px = daily(path)
    print(f"Or quotidien {px.index[0].date()} -> {px.index[-1].date()} ({len(px)} jours)\n")

    strats = {
        "Achat-conservation or": pd.Series(1.0, index=px.index),
        "1. TSMOM long seul (vol 15 %)": tsmom(px),
        "1b. TSMOM long/short": tsmom(px, long_only=False),
        "2. SMA 50/200 long seul": sma_cross(px),
        "3. Donchian 55/20 long seul": donchian(px),
        "3b. Donchian 55/20 long/short": donchian(px, long_only=False),
    }
    rows, nets = [], {}
    for name, w in strats.items():
        net = run(px, w)
        nets[name] = net
        full, a, b, s = stats(net), stats(net[:SPLIT]), stats(net[SPLIT:]), stats(run(px, w, STRESS))
        rows.append({"robot": name, **full, "exposition": w.abs().mean(), "CAGR 09-17": a["CAGR"],
                     "CAGR 18-26": b["CAGR"], "Sharpe 09-17": a["Sharpe"], "Sharpe 18-26": b["Sharpe"],
                     "CAGR frais x3": s["CAGR"]})
    df = pd.DataFrame(rows)
    for c in ("CAGR", "max DD", "pire année", "CAGR 09-17", "CAGR 18-26", "CAGR frais x3", "exposition"):
        df[c] = df[c].map(lambda x: f"{x:+.1%}" if c != "exposition" else f"{x:.0%}")
    print(df.round(2).to_string(index=False))

    print("\nRendement par année :")
    yr = pd.DataFrame({k.split(" ")[0]: (1 + v).groupby(v.index.year).prod() - 1 for k, v in nets.items()})
    print(yr.map(lambda x: f"{x:+.0%}").to_string())

    print("\nSensibilité TSMOM long seul (CAGR / Sharpe / max DD) :")
    for lbs, tgt in itertools.product([(21,), (63,), (126,), (252,), (21, 63, 126, 252)], [0.10, 0.15, 0.20]):
        st = stats(run(px, tsmom(px, lbs, True, tgt)))
        print(f"  fenêtres {str(lbs):20s} vol {tgt:.0%} : {st['CAGR']:+.1%} / {st['Sharpe']:.2f} / {st['max DD']:+.1%}")
    print("\nSensibilité Donchian long seul :")
    for e, x in itertools.product([20, 55, 100], [10, 20, 50]):
        if x < e:
            st = stats(run(px, donchian(px, e, x)))
            print(f"  {e}/{x} : {st['CAGR']:+.1%} / {st['Sharpe']:.2f} / {st['max DD']:+.1%}")

    if len(sys.argv) > 2:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 5))
        for k in ["Achat-conservation or", "1. TSMOM long seul (vol 15 %)", "2. SMA 50/200 long seul", "3. Donchian 55/20 long seul"]:
            ax.plot((1 + nets[k]).cumprod() * 10000, label=k)
        ax.set_yscale("log"); ax.set_ylabel("Capital (départ 10 000 €, échelle log)")
        ax.axvline(pd.Timestamp(SPLIT), color="grey", ls="--", lw=1)
        ax.set_title("Or 2009-2026 : robots de tendance vs achat simple (frais et swap inclus)")
        ax.legend(); ax.grid(alpha=.3); fig.tight_layout(); fig.savefig(sys.argv[2], dpi=130)

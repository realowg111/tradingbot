"""Gold / silver hedge backtest (MoonX forex/CFD data, Gemini PAXG as cross-check).
Reuses the engine of hedge_backtest.py with CFD costs: spread per side + overnight swap on both sides.
"""
import itertools
import numpy as np, pandas as pd
import hedge_backtest as hb
from hedge_backtest import load, run, stats, buy_hold, trend_hedge, beta_hedge, pairs, evaluate

def cfd_costs():
    hb.FEE, hb.FUND_DAY, hb.SWAP_BOTH = 0.0003, 0.0001, True    # ~0.03% spread/side, ~0.01%/day swap

def perp_costs():
    hb.FEE, hb.FUND_DAY, hb.SWAP_BOTH = 0.0006, 0.0003, False

BPD_FX = 252 / 365          # 252 trading bars per year -> correct annualisation

def show(rows):
    df = pd.DataFrame(rows)
    for c in ("total", "cagr", "maxdd"): df[c] = df[c].map(lambda x: f"{x:+.1%}")
    for c in ("sharpe", "calmar"): df[c] = df[c].map(lambda x: f"{x:.2f}")
    print(df.to_string(index=False))

if __name__ == "__main__":
    cfd_costs()
    px = pd.concat({s: load(s) for s in ["XAUUSD", "XAGUSD"]}, axis=1, sort=True).dropna()
    split = int(len(px) * 0.6)
    print("Metals", px.index[0].date(), "->", px.index[-1].date(), len(px), "bars, split", px.index[split].date())
    rows = []
    for a in ["XAUUSD", "XAGUSD"]:
        rows += evaluate(lambda p, a=a: buy_hold(p, a), px, BPD_FX, f"Buy&Hold {a}", split)[0]
        rows += evaluate(lambda p, a=a: trend_hedge(p, a, 50), px, BPD_FX, f"Trend hedge {a} SMA50", split)[0]
    rows += evaluate(lambda p: beta_hedge(p, "XAGUSD", "XAUUSD"), px, BPD_FX, "Beta hedge long XAG / short XAU", split)[0]

    grid = list(itertools.product([20, 30, 60], [1.5, 2.0, 2.5]))
    best = max(grid, key=lambda g: stats(*run(pairs(px, "XAGUSD", "XAUUSD", *g).iloc[:split], px.iloc[:split], BPD_FX), BPD_FX, "")["sharpe"])
    rows += evaluate(lambda p: pairs(p, "XAGUSD", "XAUUSD", *best), px, BPD_FX, f"Pairs XAG/XAU (win{best[0]}, z{best[1]})", split)[0]
    allg = [run(pairs(px, "XAGUSD", "XAUUSD", *g), px, BPD_FX)[0].iloc[-1] - 1 for g in grid]
    print(f"  grid XAG/XAU: median {np.median(allg):+.1%}, min {min(allg):+.1%}, max {max(allg):+.1%}, positive {sum(x>0 for x in allg)}/9")
    show(rows)

    print("\nTrend-hedge robustness (total full period / OOS):")
    for a in ["XAUUSD", "XAGUSD"]:
        line = []
        for n in (20, 30, 50, 75, 100):
            w = trend_hedge(px, a, n)
            e = run(w, px, BPD_FX)[0]; e2 = run(w.iloc[split:], px.iloc[split:], BPD_FX)[0]
            line.append(f"SMA{n}: {e.iloc[-1]-1:+.0%}/{e2.iloc[-1]-1:+.0%}")
        bh = px[a].iloc[-1] / px[a].iloc[0] - 1
        print(f"  {a} (prix seul {bh:+.0%}): " + ", ".join(line))

    # Cross-check on Gemini PAXG (7 days/week) and BTC -> gold rotation
    perp_costs()
    cx = pd.concat({"BTC": load("BTC"), "PAXG": load("PAXG")}, axis=1).dropna()
    print("\nCrypto + PAXG", cx.index[0].date(), "->", cx.index[-1].date(), len(cx), "days")
    rows = []
    rows += evaluate(lambda p: buy_hold(p, "PAXG"), cx, 1, "Buy&Hold PAXG")[0]
    rows += evaluate(lambda p: trend_hedge(p, "PAXG", 50), cx, 1, "Trend hedge PAXG SMA50")[0]
    rows += evaluate(lambda p: buy_hold(p, "BTC"), cx, 1, "Buy&Hold BTC (meme periode)")[0]
    rows += evaluate(lambda p: trend_hedge(p, "BTC", 50), cx, 1, "Trend hedge BTC SMA50")[0]
    def rotation(p, n=50):
        sma = p["BTC"].rolling(n).mean()
        on = (p["BTC"] > sma) | sma.isna()
        return pd.DataFrame({"BTC": on.astype(float), "PAXG": (~on).astype(float)}, index=p.index)
    rows += evaluate(rotation, cx, 1, "Rotation BTC -> or quand BTC < SMA50")[0]
    rows += evaluate(lambda p: pd.DataFrame({"BTC": 0.5, "PAXG": 0.5}, index=p.index), cx, 1, "50% BTC + 50% or (statique)")[0]
    show(rows)
    print(f"  correlation BTC/PAXG daily returns: {cx.pct_change().corr().iloc[0,1]:+.2f}")

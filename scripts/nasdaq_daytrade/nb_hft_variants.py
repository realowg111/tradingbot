"""Fast-execution layers on top of the validated noise-boundary strategy (Nasdaq, QQQ 1-minute).

Same signals, size and costs as qqq_intraday_momentum.py; only the execution changes:
  V0  baseline: market entry at the next minute, exit checked every 30 minutes.
  V1  limit entry on a pullback: when a signal fires, a limit order waits at max(upper band, VWAP)
      for a long (min(lower band, VWAP) for a short) until the next 30-minute check; filled only if
      the price trades back to it (better price, but some signals are missed).
  V2  minute exit: the exit rule (close back below max(upper band, VWAP) for a long) is checked on
      every 1-minute close instead of every 30 minutes; exit at the next minute's open.
  V3  V1 + V2.
Usage: python3 nb_hft_variants.py qqq.parquet
"""
import sys
import numpy as np, pandas as pd
from qqq_intraday_momentum import load, stats

COSTS = {"sans frais": 0.0, "réels 0,01 %": 0.0001, "x3 0,03 %": 0.0003}


def bands(opn, close, vol):
    o0, prev = opn[0], close[389].shift(1)
    sigma = (close.div(o0, axis=0) - 1).abs().rolling(14).mean().shift(1)
    top = pd.concat([o0, prev], axis=1).max(axis=1).to_numpy()[:, None]
    bot = pd.concat([o0, prev], axis=1).min(axis=1).to_numpy()[:, None]
    U, L = top * (1 + sigma.to_numpy()), bot * (1 - sigma.to_numpy())
    V = ((close * vol).cumsum(axis=1) / vol.cumsum(axis=1).replace(0, np.nan)).to_numpy()
    lev = (0.02 / close[389].pct_change().rolling(14).std().shift(1)).clip(upper=4).to_numpy()
    return U, L, V, lev


def run(opn, close, high, low, vol, limit_entry, minute_exit):
    U, L, V, lev = bands(opn, close, vol)
    C, O, H, Lo = close.to_numpy(), opn.to_numpy(), high.to_numpy(), low.to_numpy()
    O = np.where(np.isnan(O), C, O)
    rows = []
    for d in range(len(C)):
        if np.isnan(U[d, 30]) or np.isnan(lev[d]):
            continue
        pos, en, pend, plim = 0, 0.0, 0, 0.0
        trades = []
        for k in range(30, 390):
            x = C[d, k - 1]
            check = (k % 30 == 0) and k <= 360
            # pending limit order
            if pend and pos == 0:
                if (pend > 0 and Lo[d, k] <= plim) or (pend < 0 and H[d, k] >= plim):
                    pos, en = pend, (min(O[d, k], plim) if pend > 0 else max(O[d, k], plim))
                    pend = 0
            # exits
            if pos and (check or minute_exit):
                if (pos > 0 and x < max(U[d, k - 1], V[d, k - 1])) or (pos < 0 and x > min(L[d, k - 1], V[d, k - 1])):
                    trades.append(pos * (O[d, k] / en - 1)); pos = 0
            # entries at the 30-minute checks
            if check and pos == 0:
                pend = 0
                side = 1 if x > U[d, k - 1] else (-1 if x < L[d, k - 1] else 0)
                if side:
                    if limit_entry:
                        lim = max(U[d, k - 1], V[d, k - 1]) if side > 0 else min(L[d, k - 1], V[d, k - 1])
                        if side * (x - lim) > 0:
                            pend, plim = side, lim
                    else:
                        pos, en = side, O[d, k]
        if pos:
            trades.append(pos * (C[d, 389] / en - 1))
        for r in trades:
            rows.append((close.index[d], r, lev[d]))
    return pd.DataFrame(rows, columns=["day", "r", "lev"])


def pnl(t, idx, cost):
    return ((t["r"] - cost) * t["lev"]).groupby(t["day"]).sum().reindex(idx, fill_value=0.0)


if __name__ == "__main__":
    path = sys.argv[1]
    opn, close, vol = load(path)
    x = pd.read_parquet(path); x.index = pd.to_datetime(x.pop("Timestamp")); x.columns = [c.lower() for c in x.columns]
    m = x.index.hour * 60 + x.index.minute
    x = x[(m >= 570) & (m < 960)]
    x = x.assign(minute=x.index.hour * 60 + x.index.minute - 570, day=x.index.normalize())
    high = x.pivot_table(index="day", columns="minute", values="high", aggfunc="max").reindex(index=close.index, columns=range(390)).ffill(axis=1)
    low = x.pivot_table(index="day", columns="minute", values="low", aggfunc="min").reindex(index=close.index, columns=range(390)).ffill(axis=1)
    idx = close.index
    rows = []
    for name, le, me in [("V0 base (marché, sortie /30 min)", False, False), ("V1 entrée limite sur repli", True, False),
                         ("V2 sortie surveillée chaque minute", False, True), ("V3 limite + sortie chaque minute", True, True)]:
        t = run(opn, close, high, low, vol, le, me)
        for cname, c in COSTS.items():
            p = pnl(t, idx, c)
            s, a, b = stats(p), stats(p[p.index.year < 2019]), stats(p[p.index.year >= 2019])
            r = t["r"] - c
            rows.append({"version": name, "frais": cname, "trades/jour": len(t) / len(idx), "gagnants": (r > 0).mean(),
                         "CAGR": s["CAGR"], "max DD": s["max DD"], "Sharpe": s["Sharpe"], "CAGR 14-18": a["CAGR"], "CAGR 19-24": b["CAGR"]})
    df = pd.DataFrame(rows)
    for c in ("CAGR", "max DD", "CAGR 14-18", "CAGR 19-24"):
        df[c] = df[c].map(lambda v: f"{v:+.1%}")
    df["gagnants"] = df["gagnants"].map(lambda v: f"{v:.0%}")
    print(df.round(2).to_string(index=False))

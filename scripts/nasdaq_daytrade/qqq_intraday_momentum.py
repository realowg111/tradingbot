"""Intraday momentum on the Nasdaq 100 (QQQ), after Zarattini, Aziz & Barbon (2024),
"Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)".

Data: QQQ 1-minute bars 2014-01 -> 2024-01 (Hugging Face Maxim37/timeseries-1m-QQQ-10y),
regular session 09:30-16:00 New York time only.

Rules as in the paper:
  - Noise area: sigma(t) = mean over the last 14 sessions of |close(t) / open - 1| at the
    same minute of the session. Upper band = max(open, previous close) * (1 + sigma(t)),
    lower band = min(open, previous close) * (1 - sigma(t)).
  - Every 30 minutes from 10:00 to 15:30: long if the close is above the upper band, short if
    below the lower band. Trailing stop: a long is closed when the close falls below
    max(upper band, VWAP), a short when it rises above min(lower band, VWAP).
  - Everything is closed at the end of the session (15:59 close). No overnight position.
  - Size: min(4, 2 % / daily volatility of QQQ over 14 days) x equity.
Unlike the paper, trades are filled at the open of the next minute (not at the signal close).

Costs per round trip, in % of price: paper-like broker (commission + slippage ~0.003 %),
CFD US100 (~0.01 %), stress (0.03 %).

Usage: python3 qqq_intraday_momentum.py path/to/qqq.parquet [chart.png]
"""
import sys
import numpy as np, pandas as pd

COSTS = {"courtier actions (0,003 %)": 0.00003, "CFD US100 (0,01 %)": 0.0001, "stress (0,03 %)": 0.0003}
SPLIT = 2019


def load(path):
    d = pd.read_parquet(path)
    d.index = pd.to_datetime(d.pop("Timestamp"))
    d.columns = [c.lower() for c in d.columns]
    m = d.index.hour * 60 + d.index.minute
    d = d[(m >= 570) & (m < 960)]                       # 09:30 .. 15:59
    d = d.assign(minute=(d.index.hour * 60 + d.index.minute - 570), day=d.index.normalize())
    piv = {k: d.pivot_table(index="day", columns="minute", values=k, aggfunc="last") for k in ("open", "close", "volume")}
    full = range(390)
    close = piv["close"].reindex(columns=full).ffill(axis=1)
    opn = piv["open"].reindex(columns=full)
    vol = piv["volume"].reindex(columns=full).fillna(0)
    ok = opn[0].notna() & (piv["close"].notna().sum(axis=1) >= 300)   # full sessions only
    return opn[ok], close[ok], vol[ok]


def backtest(opn, close, vol, lookback=14, every=30, vm=1.0):
    o0 = opn[0]
    prev_c = close[389].shift(1)
    move = (close.div(o0, axis=0) - 1).abs()
    sigma = move.rolling(lookback).mean().shift(1) * vm          # previous 14 sessions only
    ub = sigma.mul(pd.concat([o0, prev_c], axis=1).max(axis=1), axis=0) + pd.concat([o0, prev_c], axis=1).max(axis=1).to_numpy()[:, None]
    lb = pd.concat([o0, prev_c], axis=1).min(axis=1).to_numpy()[:, None] * (1 - sigma)
    vwap = (close * vol).cumsum(axis=1) / vol.cumsum(axis=1).replace(0, np.nan)
    daily_ret = close[389].pct_change()
    lev = (0.02 / daily_ret.rolling(14).std().shift(1)).clip(upper=4)

    C, O, U, L, V = close.to_numpy(), opn.to_numpy(), ub.to_numpy(), lb.to_numpy(), vwap.to_numpy()
    checks = list(range(every, 390, every))                         # 10:00, 10:30, ... 15:30
    trades = []                                                    # (day, side, entry, exit)
    for di in range(len(C)):
        if np.isnan(U[di, 30]) or np.isnan(lev.iloc[di]):
            continue
        pos, entry = 0, None
        for m in checks:
            x = C[di, m - 1]                                       # close of the bar ending at the check
            if np.isnan(x):
                continue
            nxt = O[di, m] if not np.isnan(O[di, m]) else C[di, m]
            if pos > 0 and x < max(U[di, m - 1], V[di, m - 1]):
                trades.append((di, pos, entry, nxt)); pos = 0
            elif pos < 0 and x > min(L[di, m - 1], V[di, m - 1]):
                trades.append((di, pos, entry, nxt)); pos = 0
            if pos == 0:
                if x > U[di, m - 1]:
                    pos, entry = 1, nxt
                elif x < L[di, m - 1]:
                    pos, entry = -1, nxt
        if pos:
            trades.append((di, pos, entry, C[di, 389]))
    t = pd.DataFrame(trades, columns=["di", "side", "entry", "exit"])
    t["day"] = close.index[t["di"]]
    t["r"] = t["side"] * (t["exit"] / t["entry"] - 1)
    t["lev"] = lev.iloc[t["di"]].to_numpy()
    return t, daily_ret


def stats(daily):
    yrs = (daily.index[-1] - daily.index[0]).days / 365.25
    eq = (1 + daily).cumprod()
    return {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "max DD": (eq / eq.cummax() - 1).min(),
            "Sharpe": daily.mean() / daily.std() * np.sqrt(252)}


def daily_pnl(t, index, cost):
    pnl = ((t["r"] - cost) * t["lev"]).groupby(t["day"]).sum()
    return pnl.reindex(index, fill_value=0.0)


if __name__ == "__main__":
    opn, close, vol = load(sys.argv[1])
    print(f"QQQ {close.index[0].date()} -> {close.index[-1].date()}, {len(close)} séances\n")
    t, bh = backtest(opn, close, vol)
    idx = close.index
    rows, curves = [], {}
    bh = bh.fillna(0)
    rows.append({"version": "Achat-conservation QQQ", **stats(bh), "CAGR 14-18": stats(bh[bh.index.year < SPLIT])["CAGR"],
                 "CAGR 19-24": stats(bh[bh.index.year >= SPLIT])["CAGR"]})
    curves["Achat-conservation QQQ"] = bh
    for name, cost in COSTS.items():
        p = daily_pnl(t, idx, cost)
        curves[name] = p
        rows.append({"version": f"Momentum intraday, frais {name}", **stats(p),
                     "CAGR 14-18": stats(p[p.index.year < SPLIT])["CAGR"], "CAGR 19-24": stats(p[p.index.year >= SPLIT])["CAGR"]})
    df = pd.DataFrame(rows)
    for c in ("CAGR", "max DD", "CAGR 14-18", "CAGR 19-24"):
        df[c] = df[c].map(lambda x: f"{x:+.1%}")
    print(df.round(2).to_string(index=False))
    r = t["r"] - COSTS["CFD US100 (0,01 %)"]
    print(f"\nTrades : {len(t)} ({len(t) / len(idx):.2f} par jour), gagnants {(r > 0).mean():.0%}, "
          f"gain moyen / perte moyenne {r[r > 0].mean() / -r[r < 0].mean():.2f}, levier moyen {t['lev'].mean():.2f}")
    print(f"Longs : {r[t.side > 0].sum():+.2f}   Shorts : {r[t.side < 0].sum():+.2f} (somme des rendements non levés)")

    p = curves["CFD US100 (0,01 %)"]
    yr = pd.DataFrame({"momentum (CFD)": (1 + p).groupby(p.index.year).prod() - 1,
                       "QQQ": (1 + bh).groupby(bh.index.year).prod() - 1})
    print("\nPar année :\n" + yr.map(lambda x: f"{x:+.0%}").to_string())

    print("\nSensibilité (frais CFD) : fenêtre x fréquence x largeur de bande -> CAGR / Sharpe / max DD")
    for lb_, ev, vm in [(10, 30, 1), (20, 30, 1), (14, 15, 1), (14, 60, 1), (14, 30, 0.8), (14, 30, 1.2), (14, 30, 1.5)]:
        tt, _ = backtest(opn, close, vol, lb_, ev, vm)
        st = stats(daily_pnl(tt, idx, COSTS["CFD US100 (0,01 %)"]))
        print(f"  {lb_} j, {ev} min, x{vm} : {st['CAGR']:+.1%} / {st['Sharpe']:.2f} / {st['max DD']:+.1%}")

    if len(sys.argv) > 2:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 5))
        for k, v in curves.items():
            ax.plot((1 + v).cumprod() * 10000, label=k)
        ax.set_yscale("log"); ax.set_ylabel("Capital (départ 10 000, échelle log)")
        ax.set_title("Nasdaq (QQQ) 2014-2024 : momentum intraday vs achat simple")
        ax.legend(); ax.grid(alpha=.3); fig.tight_layout(); fig.savefig(sys.argv[2], dpi=130)

"""Intraday candidates on Bitcoin (Binance BTCUSDT 1-minute, 2020-01 -> 2026-11, Hugging Face
vaquum/binance_btcusdt_1m_klines). Days are UTC days; every position is closed by 23:59 UTC.

  1. Intraday time-series momentum (Shen, Urquhart & Wang 2022, "Bitcoin intraday time series
     momentum", The Financial Review): the first half-hour return (00:00-00:30 UTC) predicts
     the last half hour; trade 23:30-24:00 in its direction.
  2. Noise-boundary momentum (Zarattini, Aziz & Barbon 2024) with the paper's settings, the UTC
     00:00 open as the day open: 14-day noise area, decisions every 30 minutes, VWAP trailing stop.
Size for both: min(4, 2 % / 14-day daily volatility) x equity (about 0.6x for Bitcoin).
Costs per round trip: none, 0.10 % (taker fees 0.05 % per side on futures), 0.30 % (x3).
Periods: 2020-2022 and 2023-2026.

Usage: python3 btc_intraday.py path/to/btc.parquet
"""
import itertools, sys
import numpy as np, pandas as pd

COSTS = {"sans frais": 0.0, "taker 0,10 %": 0.001, "x3 0,30 %": 0.003}
SPLIT = 2023


def load(path):
    d = pd.read_parquet(path, columns=["datetime", "open", "high", "low", "close", "volume"])
    d.index = pd.DatetimeIndex(d.pop("datetime")).tz_convert(None)
    d = d[~d.index.duplicated()]
    d = d.assign(minute=d.index.hour * 60 + d.index.minute, day=d.index.normalize())
    piv = {k: d.pivot_table(index="day", columns="minute", values=k, aggfunc="last").reindex(columns=range(1440))
           for k in ("open", "close", "volume")}
    close = piv["close"].ffill(axis=1)
    ok = piv["close"].notna().sum(axis=1) >= 1300
    return piv["open"][ok], close[ok], piv["volume"][ok].fillna(0)


def stats(p):
    yrs = (p.index[-1] - p.index[0]).days / 365.25
    eq = (1 + p).cumprod()
    return {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "max DD": (eq / eq.cummax() - 1).min(),
            "Sharpe": p.mean() / p.std() * np.sqrt(365) if p.std() > 0 else 0.0}


def leverage(close):
    return (0.02 / close[1439].pct_change().rolling(14).std().shift(1)).clip(upper=4)


def momentum(close, sig_end=30, start=1410):
    sig = np.sign(close[sig_end - 1] / close[1439].shift(1) - 1)
    r = sig * (close[1439] / close[start - 1] - 1)
    return pd.DataFrame({"r": r, "lev": leverage(close), "n": 1}).dropna()


def noise_boundary(opn, close, vol, lookback=14, every=30, vm=1.0):
    o0, prev = opn[0], close[1439].shift(1)
    sigma = (close.div(o0, axis=0) - 1).abs().rolling(lookback).mean().shift(1) * vm
    top = pd.concat([o0, prev], axis=1).max(axis=1).to_numpy()[:, None]
    bot = pd.concat([o0, prev], axis=1).min(axis=1).to_numpy()[:, None]
    U, L = top * (1 + sigma.to_numpy()), bot * (1 - sigma.to_numpy())
    V = ((close * vol).cumsum(axis=1) / vol.cumsum(axis=1).replace(0, np.nan)).to_numpy()
    C, O = close.to_numpy(), opn.to_numpy()
    lev = leverage(close)
    rows = []
    for d in range(len(C)):
        if np.isnan(U[d, every]) or np.isnan(lev.iloc[d]):
            continue
        pos, en, tot, n = 0, None, 0.0, 0
        for m in range(every, 1440, every):
            x = C[d, m - 1]
            nxt = O[d, m] if not np.isnan(O[d, m]) else x
            if pos > 0 and x < max(U[d, m - 1], V[d, m - 1]) or pos < 0 and x > min(L[d, m - 1], V[d, m - 1]):
                tot += pos * (nxt / en - 1); n += 1; pos = 0
            if pos == 0:
                if x > U[d, m - 1]: pos, en = 1, nxt
                elif x < L[d, m - 1]: pos, en = -1, nxt
        if pos:
            tot += pos * (C[d, 1439] / en - 1); n += 1
        if n:
            rows.append((close.index[d], tot, lev.iloc[d], n))
    return pd.DataFrame(rows, columns=["day", "r", "lev", "n"]).set_index("day")


def pnl(t, idx, cost):
    return ((t["r"] - cost * t["n"]) * t["lev"]).reindex(idx, fill_value=0.0)


if __name__ == "__main__":
    opn, close, vol = load(sys.argv[1])
    idx = close.index
    print(f"BTC {idx[0].date()} -> {idx[-1].date()}, {len(idx)} jours\n")
    bh = close[1439].pct_change().fillna(0)
    rows = [{"stratégie": "Achat-conservation BTC", "frais": "-", **stats(bh),
             "CAGR 20-22": stats(bh[bh.index.year < SPLIT])["CAGR"], "CAGR 23-26": stats(bh[bh.index.year >= SPLIT])["CAGR"]}]
    cands = {"1. Momentum dernière demi-heure (Shen 2022)": momentum(close),
             "2. Noise boundary BTC": noise_boundary(opn, close, vol)}
    for name, t in cands.items():
        for cname, cost in COSTS.items():
            p = pnl(t, idx, cost)
            rows.append({"stratégie": name, "frais": cname, **stats(p), "trades/an": t["n"].sum() / (len(idx) / 365),
                         "CAGR 20-22": stats(p[p.index.year < SPLIT])["CAGR"], "CAGR 23-26": stats(p[p.index.year >= SPLIT])["CAGR"]})
    df = pd.DataFrame(rows)
    for c in ("CAGR", "max DD", "CAGR 20-22", "CAGR 23-26"):
        df[c] = df[c].map(lambda v: f"{v:+.1%}")
    print(df.round(2).to_string(index=False))

    print("\nGrille momentum (frais taker) : fin du signal x début du trade -> CAGR / Sharpe")
    for se, st in itertools.product([30, 60, 120], [1380, 1410]):
        s = stats(pnl(momentum(close, se, st), idx, COSTS["taker 0,10 %"]))
        print(f"  signal 00:00->{se} min, trade dès {st // 60}:{st % 60:02d} : {s['CAGR']:+.1%} / {s['Sharpe']:.2f}")
    print("\nGrille noise boundary (frais taker) : fenêtre x fréquence x bande")
    for lb, ev, vm in [(10, 30, 1), (20, 30, 1), (14, 60, 1), (14, 120, 1), (14, 30, 1.5), (14, 60, 1.5)]:
        s = stats(pnl(noise_boundary(opn, close, vol, lb, ev, vm), idx, COSTS["taker 0,10 %"]))
        print(f"  {lb} j, {ev} min, x{vm} : {s['CAGR']:+.1%} / {s['Sharpe']:.2f} / {s['max DD']:+.1%}")

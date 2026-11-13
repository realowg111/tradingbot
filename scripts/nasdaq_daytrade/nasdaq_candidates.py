"""More published day-trading candidates on the Nasdaq 100 (QQQ 1-minute, 2014-2024), next to the
noise-boundary momentum of qqq_intraday_momentum.py, with the same tests.

  B. 5-minute opening range breakout (Zarattini & Aziz 2023, "Can Day Trading Really Be
     Profitable?", SSRN 4416622): direction of the first 5-minute candle (09:30-09:35), entry at
     09:35, stop at the other end of that candle, target 10 R, else exit at 16:00.
     Size: 1 % of equity at risk, leverage capped at 4.
  C. Market intraday momentum (Gao, Han, Li & Zhou 2018, Journal of Financial Economics):
     the return from the previous close to 10:00 predicts the last half hour; trade 15:30-16:00
     in its direction. Size: min(4, 2 % / 14-day daily volatility), as for the noise boundary.

Usage: python3 nasdaq_candidates.py path/to/qqq.parquet
"""
import itertools, sys
import numpy as np, pandas as pd
from qqq_intraday_momentum import load, backtest, stats, daily_pnl

COSTS = {"sans frais": 0.0, "réels 0,01 %": 0.0001, "x3 0,03 %": 0.0003}
SPLIT = 2019


def orb(opn, close, high, low, bar=5, target_r=10.0, risk=0.01, maxlev=4.0):
    O, C, H, L = opn.to_numpy(), close.to_numpy(), high.to_numpy(), low.to_numpy()
    rows = []
    for d in range(len(C)):
        o0, c0 = O[d, 0], C[d, bar - 1]
        hi, lo = np.nanmax(H[d, :bar]), np.nanmin(L[d, :bar])
        if np.isnan(o0) or np.isnan(c0) or c0 == o0:
            continue
        side = 1 if c0 > o0 else -1
        en = O[d, bar] if not np.isnan(O[d, bar]) else C[d, bar]
        stop = lo if side > 0 else hi
        r = side * (en - stop)
        if not r > 0:
            continue
        tgt = en + side * target_r * r
        ex = C[d, 389]
        for k in range(bar, 390):
            if np.isnan(H[d, k]):
                continue
            if (side > 0 and L[d, k] <= stop) or (side < 0 and H[d, k] >= stop):
                ex = stop if k == bar else (min(O[d, k], stop) if side > 0 else max(O[d, k], stop)); break
            if (side > 0 and H[d, k] >= tgt) or (side < 0 and L[d, k] <= tgt):
                ex = tgt; break
        lev = min(maxlev, risk / (r / en))
        rows.append((close.index[d], side * (ex / en - 1), lev))
    return pd.DataFrame(rows, columns=["day", "r", "lev"])


def last_half_hour(close, sig_end=30, start=360, end=389):
    """Signal: previous close -> close at 09:30+sig_end; trade 09:30+start -> 16:00 close."""
    prev = close[389].shift(1)
    sig = np.sign(close[sig_end - 1] / prev - 1)
    r = sig * (close[end] / close[start - 1] - 1)
    vol = close[389].pct_change().rolling(14).std().shift(1)
    lev = (0.02 / vol).clip(upper=4)
    t = pd.DataFrame({"day": close.index, "r": r.to_numpy(), "lev": lev.to_numpy()}).dropna()
    return t[t["r"] != 0]


def report(name, t, idx):
    out = []
    for cname, cost in COSTS.items():
        p = daily_pnl(t, idx, cost)
        s, a, b = stats(p), stats(p[p.index.year < SPLIT]), stats(p[p.index.year >= SPLIT])
        out.append({"stratégie": name, "frais": cname, "trades": len(t), "CAGR": s["CAGR"], "max DD": s["max DD"],
                    "Sharpe": s["Sharpe"], "CAGR 14-18": a["CAGR"], "CAGR 19-24": b["CAGR"]})
    return out


if __name__ == "__main__":
    d = pd.read_parquet(sys.argv[1])
    opn, close, vol = load(sys.argv[1])
    # high / low grids for the ORB
    x = d.copy(); x.index = pd.to_datetime(x.pop("Timestamp")); x.columns = [c.lower() for c in x.columns]
    m = x.index.hour * 60 + x.index.minute
    x = x[(m >= 570) & (m < 960)]
    x = x.assign(minute=x.index.hour * 60 + x.index.minute - 570, day=x.index.normalize())
    high = x.pivot_table(index="day", columns="minute", values="high", aggfunc="max").reindex(index=close.index, columns=range(390))
    low = x.pivot_table(index="day", columns="minute", values="low", aggfunc="min").reindex(index=close.index, columns=range(390))
    idx = close.index

    rows = []
    tA, _ = backtest(opn, close, vol)
    rows += report("A. Noise boundary (Zarattini 2024)", tA, idx)
    tB = orb(opn, close, high, low)
    rows += report("B. ORB 5 min, 10R (Zarattini & Aziz 2023)", tB, idx)
    tC = last_half_hour(close)
    rows += report("C. Dernière demi-heure (Gao et al. 2018)", tC, idx)
    df = pd.DataFrame(rows)
    for c in ("CAGR", "max DD", "CAGR 14-18", "CAGR 19-24"):
        df[c] = df[c].map(lambda v: f"{v:+.1%}")
    print(df.round(2).to_string(index=False))

    rb = tB["r"] - COSTS["réels 0,01 %"]
    print(f"\nORB : gagnants {(rb > 0).mean():.0%}, levier moyen {tB['lev'].mean():.2f}")
    print("\nGrille ORB (frais réels) : bougie x objectif -> CAGR / Sharpe / max DD")
    for bar, tg in itertools.product([5, 15, 30], [2, 5, 10, 1000]):
        st = stats(daily_pnl(orb(opn, close, high, low, bar, tg), idx, COSTS["réels 0,01 %"]))
        print(f"  {bar} min, {tg if tg < 1000 else 'clôture'}R : {st['CAGR']:+.1%} / {st['Sharpe']:.2f} / {st['max DD']:+.1%}")
    print("\nGrille dernière demi-heure (frais réels) : fin du signal x fenêtre de trade")
    for se, (s0, e0) in itertools.product([30, 60, 360], [(360, 389), (330, 389), (375, 389)]):
        if se >= s0:
            continue
        st = stats(daily_pnl(last_half_hour(close, se, s0, e0), idx, COSTS["réels 0,01 %"]))
        print(f"  signal jusqu'à +{se} min, trade {s0}->{e0} : {st['CAGR']:+.1%} / {st['Sharpe']:.2f} / {st['max DD']:+.1%}")

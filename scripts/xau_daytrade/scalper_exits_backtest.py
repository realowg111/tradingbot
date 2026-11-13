"""Does the video's "small losses, bigger gains" exit management make the 12-indicator scalper
profitable? Same entries as scalper_backtest.py (8 of 10 votes aligned, 5-minute bars, 03:00-16:55
New York), with exit techniques seen in the video:
  - cut early: close as soon as the vote score falls below `cut` in the trade's direction
    (signal fading) instead of waiting for the stop;
  - break-even: once the trade is +be ATR in profit, the stop moves to the entry price;
  - trailing stop: once +trail_start ATR in profit, the stop follows the best price at trail ATR;
  - target: TP in ATR (None = no fixed target, the trailing stop or the cut closes the trade).
Initial stop 1 ATR, max holding 12 bars (1 hour). Stop wins when stop and target sit in one bar;
break-even and trailing are updated on the bar close (so they act from the next bar).

Usage: python3 scalper_exits_backtest.py xau_5m.pkl
"""
import itertools, sys
import numpy as np, pandas as pd
from scalper_backtest import votes, atr

COSTS = {"sans frais": 0.0, "ECN 0,007 %": 0.00007}
SPLIT = pd.Timestamp("2018-01-01", tz="America/New_York")


def simulate(d, score, a, thr=8, sl=1.0, tp=None, cut=None, be=None, trail=None, trail_start=1.0, hold=12):
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    m = (d.index.hour * 60 + d.index.minute).to_numpy()
    day = (d.index + pd.Timedelta(hours=6)).normalize().to_numpy()
    open_ok, flat = (m >= 180) & (m < 1015), m >= 1015
    sig = np.where(score >= thr, 1, np.where(score <= -thr, -1, 0))
    out, i, n = [], 0, len(o) - 1
    while i < n:
        if sig[i] == 0 or not open_ok[i + 1] or day[i + 1] != day[i] or not a[i] > 0:
            i += 1; continue
        side, j, A = sig[i], i + 1, a[i]
        en = o[j]
        stop = en - side * sl * A
        target = en + side * tp * A if tp else None
        best, ex, k = en, None, j
        while k <= n and k < j + hold and day[k] == day[j]:
            if (side > 0 and l[k] <= stop) or (side < 0 and h[k] >= stop):
                ex = stop if k == j else (min(o[k], stop) if side > 0 else max(o[k], stop)); break
            if target is not None and ((side > 0 and h[k] >= target) or (side < 0 and l[k] <= target)):
                ex = target; break
            if flat[k]:
                ex = c[k]; break
            best = max(best, h[k]) if side > 0 else min(best, l[k])
            gain = side * (best - en) / A
            if be is not None and gain >= be:
                stop = side * max(side * stop, side * en)
            if trail is not None and gain >= trail_start:
                stop = side * max(side * stop, side * (best - side * trail * A))
            if cut is not None and side * score[k] < cut:                  # signal fading -> leave at next open
                ex = o[k + 1] if k + 1 <= n else c[k]; k += 1; break
            k += 1
        if ex is None:
            ex = c[min(k, n)]
        out.append((d.index[j], side * (ex - en) / en, side * (ex - en) / (sl * A)))
        i = max(k, j) + 1
    return pd.DataFrame(out, columns=["t", "r", "R"]).set_index("t")


def stats(t, cost, risk_frac):
    R = t["R"] - cost / risk_frac
    yrs = (R.index[-1] - R.index[0]).days / 365.25
    win, loss = R[R > 0], R[R < 0]
    pre, post = R[R.index < SPLIT], R[R.index >= SPLIT]
    return {"trades/jour": len(R) / yrs / 252, "gagnants": (R > 0).mean(),
            "gain moy (R)": win.mean(), "perte moy (R)": -loss.mean(), "R moyen": R.mean(),
            "%/an à 1 %": R.sum() / yrs, "avant 2018": pre.sum() / ((pre.index[-1] - pre.index[0]).days / 365.25),
            "depuis 2018": post.sum() / ((post.index[-1] - post.index[0]).days / 365.25)}


if __name__ == "__main__":
    d = pd.read_pickle(sys.argv[1])
    score, a = votes(d), atr(d)
    risk = pd.Series(np.nan, index=d.index)
    configs = {
        "Base actuelle (TP 0,5 / SL 1,5)": dict(sl=1.5, tp=0.5),
        "Coupe rapide si le signal faiblit": dict(sl=1.0, tp=1.0, cut=3),
        "+ stop à l'entrée dès +0,5 ATR": dict(sl=1.0, tp=1.0, cut=3, be=0.5),
        "Coupe + break-even + stop suiveur, sans TP": dict(sl=1.0, tp=None, cut=3, be=0.5, trail=0.75, trail_start=1.0, hold=24),
        "Coupe + stop suiveur, TP 3 ATR": dict(sl=1.0, tp=3.0, cut=3, be=0.5, trail=0.75, trail_start=1.0, hold=24),
    }
    rows = []
    for name, kw in configs.items():
        t = simulate(d, score, a, **kw)
        rf = (kw["sl"] * pd.Series(a, index=d.index).reindex(t.index) / d["open"].reindex(t.index)).to_numpy()
        for cname, cost in COSTS.items():
            rows.append({"sorties": name, "frais": cname, **stats(t, cost, rf)})
    df = pd.DataFrame(rows)
    df["gagnants"] = df["gagnants"].map(lambda x: f"{x:.0%}")
    print(df.round(2).to_string(index=False))

    print("\nGrille (frais ECN) : seuil de coupe x break-even x stop suiveur -> %/an à 1 % de risque")
    g = []
    for cut, be, tr in itertools.product([0, 3, 5], [None, 0.3, 0.5], [None, 0.5, 1.0]):
        kw = dict(sl=1.0, tp=None if tr else 1.0, cut=cut, be=be, trail=tr, trail_start=1.0, hold=24)
        t = simulate(d, score, a, **kw)
        rf = (pd.Series(a, index=d.index).reindex(t.index) / d["open"].reindex(t.index)).to_numpy()
        s = stats(t, COSTS["ECN 0,007 %"], rf)
        g.append(s["%/an à 1 %"])
        print(f"  coupe <{cut}  BE {be}  suiveur {tr} : {s['%/an à 1 %']:+.1f} %/an, gagnants {s['gagnants']:.0%}, "
              f"gain moy {s['gain moy (R)']:.2f} R / perte moy {s['perte moy (R)']:.2f} R")
    print(f"  -> {sum(x > 0 for x in g)}/{len(g)} variantes positives")

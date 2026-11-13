"""Gauge-based exit for the LiveTikTok burst, on 2024-2025 gold 5-minute bars.

Entry: the side of the 12-indicator gauge (score of scalper_backtest.votes, |score| >= 2,
i.e. >= 60 % confidence). Burst sized at 85 % of the balance in margin (1:500), no individual
stops, target +3 % of the balance.
Exits compared:
  fixed  : fixed loss steps (-0.5 / -1 / -1.5 % : biggest position, next, all), measured without spread
  gauge  : hold while the gauge is not clearly against the burst; close everything when the
           gauge reaches T against it (score <= -T for a buy), with a hard safety stop at -5 %
Every run: 500 at start, 30 days max, 99 starts. Adverse extreme of a bar applied first.
Usage: python3 tiktok_gauge_exit_sim.py xau_5m.pkl
"""
import sys
import numpy as np, pandas as pd
from scalper_backtest import votes

W = np.array([0.30, 0.20, 0.15, 0.10, 0.05, 0.05, 0.05])
SPREAD, LEV, STOPOUT, TARGET, MU = 0.25, 500, 0.5, 0.03, 0.85


def run(o, h, l, c, sc, s0, s1, mode, T):
    eq, wins, nb = 500.0, 0, 0
    i = s0
    while i < s1 - 1:
        side = 1 if sc[i] >= 2 else (-1 if sc[i] <= -2 else 0)
        if side == 0:
            i += 1; continue
        j = i + 1; p0 = o[j]
        lots = MU * eq * LEV / (100 * p0) * W
        openp = np.ones(7, bool)
        cost = SPREAD * lots.sum() * 100
        realized = -cost
        stage, res, m = 0, None, j
        nb += 1
        while m < s1:
            k = (lots * openp).sum() * 100
            adverse = l[m] if side > 0 else h[m]
            fav = h[m] if side > 0 else l[m]
            margin = k * p0 / LEV
            if eq + realized + side * (adverse - p0) * k <= STOPOUT * margin:
                res = STOPOUT * margin - eq; break
            move_adv = side * (adverse - p0) * k              # price move part only (no spread)
            if mode == "fixed":
                lim = [-0.005, -0.01, -0.015]
                closed_all = False
                while stage < 3 and move_adv + (realized + cost) <= lim[stage] * eq:
                    px = p0 + side * (lim[stage] * eq - (realized + cost)) / max(k, 1e-9)
                    if stage < 2:
                        b = np.argmax(np.where(openp, lots, -1)); realized += side * (px - p0) * lots[b] * 100; openp[b] = False
                    else:
                        realized += side * (px - p0) * (lots * openp).sum() * 100; openp[:] = False; closed_all = True
                    stage += 1
                    k = (lots * openp).sum() * 100
                    move_adv = side * (adverse - p0) * k
                if closed_all or not openp.any():
                    res = realized; break
            else:
                if realized + move_adv <= -0.05 * eq:            # hard safety stop
                    res = -0.05 * eq; break
            if realized + side * (fav - p0) * k >= TARGET * eq:
                res = TARGET * eq; wins += 1; break
            if mode == "gauge" and side * sc[m] <= -T:           # gauge clearly against: cut at the close
                res = realized + side * (c[m] - p0) * k; break
            m += 1
        if res is None:
            res = realized + side * (c[min(m, s1 - 1)] - p0) * (lots * openp).sum() * 100
        eq += res
        if eq < 50:
            return eq, nb, wins, m - s0, True
        i = m + 1
    return eq, nb, wins, s1 - s0, False


if __name__ == "__main__":
    d = pd.read_pickle(sys.argv[1])
    sc_all = votes(d)
    keep = d.index >= "2024-01-01"
    o, h, l, c = (d[x].to_numpy()[keep] for x in ("open", "high", "low", "close"))
    sc = sc_all[keep]
    bpd = 276
    starts = np.arange(1, len(c) - 30 * bpd, 5 * bpd)
    print("sortie | comptes perdus | duree mediane avant perte | solde final median | rafales gagnees")
    for mode, T in [("fixed", 0), ("gauge", 2), ("gauge", 4), ("gauge", 6), ("gauge", 8)]:
        r = [run(o, h, l, c, sc, s, min(len(c), s + 30 * bpd), mode, T) for s in starts]
        lost = [x for x in r if x[4]]
        name = "paliers fixes -0.5/-1/-1.5 %" if mode == "fixed" else f"jauge contre nous >= {50 + 5 * T} %"
        med = np.median([x[3] for x in lost]) / bpd if lost else float("nan")
        print(f"{name:32s} | {len(lost) / len(r):5.0%} | {med:5.1f} j | {np.median([x[0] for x in r]):7.0f} | "
              f"{sum(x[2] for x in r) / sum(x[1] for x in r):4.0%}")

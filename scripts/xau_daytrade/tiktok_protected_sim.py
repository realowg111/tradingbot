"""LiveTikTok, protected version, on 2024-2025 gold 5-minute bars (same method as tiktok_live_sim.py).

Same style: contrarian burst after each bar (buy after a down bar, sell after an up bar), no
individual stops, burst closed at +3 % of the balance. Protections compared one by one:
  - smaller bursts (share of balance used as margin, 1:500 leverage),
  - trend filter (contrarian only in the direction of the 50-hour EMA),
  - stepwise reduction: biggest position closed at -2 %, next at -3.5 %, everything at -5 %,
  - maximum duration (15 minutes = 3 bars) without gain.
Burst weights 0.30/0.20/0.15/0.10/0.05/0.05/0.05. Adverse extreme of a bar is applied first.
Usage: python3 tiktok_protected_sim.py xau_5m.pkl
"""
import sys
import numpy as np, pandas as pd

W = np.array([0.30, 0.20, 0.15, 0.10, 0.05, 0.05, 0.05])
SPREAD, LEV, STOPOUT, TARGET = 0.25, 500, 0.5, 0.03


def run(o, h, l, c, ema, s0, s1, mu, trend, reduce, tmax):
    eq, peak, wins, n_b = 500.0, 500.0, 0, 0
    i = s0
    while i < s1 - 1:
        side = -int(np.sign(c[i] - c[i - 1])) if i > 0 else 0
        if side == 0:
            i += 1; continue
        if trend and side != (1 if c[i] > ema[i] else -1):
            i += 1; continue
        j = i + 1; p0 = o[j]
        lots = mu * eq * LEV / (100 * p0) * W               # 7 positions
        open_ = np.ones(7, bool)
        cost = SPREAD * lots.sum() * 100
        realized = -cost
        stage, res, m = 0, None, j
        n_b += 1
        while m < s1:
            adverse = l[m] if side > 0 else h[m]
            fav = h[m] if side > 0 else l[m]
            k = (lots * open_).sum() * 100
            # adverse first
            pnl_adv = realized + side * (adverse - p0) * k
            margin = (lots * open_).sum() * 100 * p0 / LEV
            if eq + pnl_adv <= STOPOUT * margin:
                res = STOPOUT * margin - eq; break
            if reduce:
                lim = [-0.02, -0.035, -0.05]
                while stage < 3 and pnl_adv <= lim[stage] * eq:
                    px = p0 + side * (lim[stage] * eq - realized) / max(k, 1e-9)
                    if stage < 2:
                        b = np.argmax(np.where(open_, lots, -1)); realized += side * (px - p0) * lots[b] * 100; open_[b] = False
                    else:
                        realized += side * (px - p0) * (lots * open_).sum() * 100; open_[:] = False
                    stage += 1
                    k = (lots * open_).sum() * 100
                    pnl_adv = realized + side * (adverse - p0) * k
                if not open_.any():
                    res = realized; break
            if realized + side * (fav - p0) * k >= TARGET * eq:
                res = TARGET * eq; wins += 1; break
            if tmax and m - j + 1 >= tmax:
                cur = realized + side * (c[m] - p0) * k
                if cur <= 0:
                    res = cur; break
            m += 1
        if res is None:
            res = realized + side * (c[min(m, s1 - 1)] - p0) * (lots * open_).sum() * 100
        eq += res; peak = max(peak, eq)
        if eq < 50:
            return eq, peak, n_b, wins, m - s0, True
        i = m + 1
    return eq, peak, n_b, wins, s1 - s0, False


if __name__ == "__main__":
    d = pd.read_pickle(sys.argv[1])
    ema = d["close"].ewm(span=600, adjust=False).mean().to_numpy()
    keep = d.index >= "2024-01-01"
    o, h, l, c = (d[x].to_numpy()[keep] for x in ("open", "high", "low", "close"))
    ema = ema[keep]
    bpd = 276
    starts = np.arange(1, len(c) - 30 * bpd, 5 * bpd)
    print("30 jours max par essai, 500 au depart, or 2024-2025\n")
    print("version | comptes perdus | duree mediane avant perte | solde final median | rafales gagnees")
    for name, mu, tr, red, tm in [("live (70 % de marge, rien)", 0.70, False, False, 0),
                                  ("20 % de marge seulement", 0.20, False, False, 0),
                                  ("20 % + filtre de tendance", 0.20, True, False, 0),
                                  ("20 % + reduction -2/-3.5/-5 %", 0.20, False, True, 0),
                                  ("20 % + tendance + reduction + 15 min", 0.20, True, True, 3),
                                  ("10 % + tendance + reduction + 15 min", 0.10, True, True, 3)]:
        r = [run(o, h, l, c, ema, s, min(len(c), s + 30 * bpd), mu, tr, red, tm) for s in starts]
        lost = [x for x in r if x[5]]
        med_d = np.median([x[4] for x in lost]) / bpd if lost else float("nan")
        print(f"{name:38s} | {len(lost) / len(r):5.0%} | {med_d:5.1f} j | {np.median([x[0] for x in r]):8.0f} | "
              f"{sum(x[3] for x in r) / sum(x[2] for x in r):4.0%}")

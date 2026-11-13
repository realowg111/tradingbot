"""Simulation of the TikTok "HFT ROBOT" live on real gold prices.

Rules read on the phone in the live:
  - bursts of 6 positions in the direction of the indicators, total 0.51 lot per 500 of balance
    (0.08 / 0.08 / 0.05 / 0.10 / 0.15 / 0.05), no stop, no take-profit;
  - the burst is held through drawdowns and closed all at once when it is +3 % of the balance;
  - then a new burst (after a few seconds of analysis).
Broker assumptions: leverage 1:500 (margin = notional / 500), stop-out when equity falls to 50 %
of the used margin (the broker closes everything), spread 0.25 $ per round trip, no commission.

Direction: the vote score of scalper_backtest.py (sign of the 10 votes) on 5-minute bars.
Each run starts with 500 at a different date of 2024-2025 and lasts at most 30 days; a run ends
early if equity falls under 50 (account lost).
Inside a 5-minute bar the adverse extreme is applied before the favourable one (prudent).

Usage: python3 tiktok_live_sim.py xau_5m.pkl
"""
import sys
import numpy as np, pandas as pd
from scalper_backtest import votes

LOT_PER_500 = 0.51
TARGET = 0.03
LEVERAGE = 500
STOPOUT = 0.50
SPREAD = 0.25


def run(o, h, l, c, sc, start, end):
    eq, peak, bursts, wins, stopouts = 500.0, 500.0, 0, 0, 0
    i = start
    while i < end - 1:
        side = 1 if sc[i] > 0 else (-1 if sc[i] < 0 else 0)
        if side == 0:
            i += 1; continue
        j = i + 1
        p0 = o[j]
        lots = LOT_PER_500 * eq / 500.0
        k = lots * 100.0                                   # $ per 1 $ of gold
        margin = k * p0 / LEVERAGE
        cost = SPREAD * k
        target_pnl = TARGET * eq
        stop_pnl = STOPOUT * margin - eq                   # pnl at which equity = 50 % of margin
        tgt_price = p0 + side * (target_pnl + cost) / k
        so_price = p0 + side * (stop_pnl + cost) / k
        bursts += 1
        res, m = None, j
        while m < end:
            adverse = l[m] if side > 0 else h[m]
            fav = h[m] if side > 0 else l[m]
            if side * (adverse - so_price) <= 0:
                res = stop_pnl; stopouts += 1; break
            if side * (fav - tgt_price) >= 0:
                res = target_pnl; wins += 1; break
            m += 1
        if res is None:
            res = side * (c[end - 1] - p0) * k - cost; m = end - 1
        eq += res
        peak = max(peak, eq)
        if eq < 50:
            return eq, peak, bursts, wins, stopouts, m - start, True
        i = m + 1
    return eq, peak, bursts, wins, stopouts, end - start, False


if __name__ == "__main__":
    d = pd.read_pickle(sys.argv[1])
    sc = votes(d)
    d = d[d.index >= "2024-01-01"]
    sc = sc[-len(d):]
    o, h, l, c = (d[x].to_numpy() for x in ("open", "high", "low", "close"))
    idx = d.index
    bars_per_day = 276
    starts = np.arange(0, len(d) - 30 * bars_per_day, 5 * bars_per_day)
    rows = []
    for s in starts:
        e = min(len(d), s + 30 * bars_per_day)
        eq, peak, b, w, so, dur, ruined = run(o, h, l, c, sc, s, e)
        rows.append({"debut": idx[s].date(), "solde final": eq, "plus haut": peak, "rafales": b, "gagnees": w,
                     "stop-out": so, "jours": dur / bars_per_day, "compte perdu": ruined})
    r = pd.DataFrame(rows)
    n = len(r)
    print(f"{n} essais de 30 jours max, 500 au depart, or 2024-2025 (levier 1:500, stop-out 50 %)\n")
    print(f"Compte perdu (< 50) : {r['compte perdu'].mean():.0%} des essais")
    lost = r[r["compte perdu"]]
    if len(lost):
        print(f"  temps avant de tout perdre : mediane {lost['jours'].median():.1f} jour(s), "
              f"25 % des cas en moins de {lost['jours'].quantile(.25):.1f} jour(s)")
        print(f"  rafales gagnees avant la perte : mediane {lost['gagnees'].median():.0f}")
        print(f"  plus haut atteint avant la perte : mediane {lost['plus haut'].median():.0f} (depart 500)")
    print(f"Comptes encore en vie apres 30 jours : {(~r['compte perdu']).mean():.0%}")
    alive = r[~r["compte perdu"]]
    if len(alive):
        print(f"  solde final median des survivants : {alive['solde final'].median():.0f}")
    print(f"Taux de rafales gagnees (toutes) : {r['gagnees'].sum() / r['rafales'].sum():.0%}")
    print(f"Stop-out (le courtier ferme tout) : {r['stop-out'].sum()} sur {r['rafales'].sum()} rafales\n")
    pd.set_option("display.width", 200)
    print(r.round(1).to_string(index=False))

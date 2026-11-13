"""S1 trend-pullback scalp (Nasdaq) with bigger targets and session windows, to see whether
larger wins per trade can beat the costs that killed the 1.5 R version.
Usage: python3 s1_bigger_targets.py qqq.parquet
"""
import itertools, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nine_am_cr"))
import numpy as np
from nine_am_cr_backtest import load_qqq
from scalping_lab import by_day, nasdaq_regimes, s1_trend_pullback, collect, summarize

days = by_day(load_qqq(sys.argv[1]), 570, 960)
reg = nasdaq_regimes(days)
rdays = [d for d in days if d[0] in reg]
print("TP (R) | durée max | fenêtre | trades/an | gagnants | R moyen net | %/an net | avant 2019 | depuis 2019 | frais x3 | pire baisse")
for tp, hold, (e0, e1, lab) in itertools.product([1.5, 3.0, 5.0], [30, 120], [(600, 930, "10h-15h30"), (600, 720, "10h-12h")]):
    fn = lambda dd, **k: s1_trend_pullback(dd, reg[dd[0]], e0, e1, 959, tp_r=tp, hold=hold)
    rows = collect(rdays, fn)
    s, s3 = summarize(rows, 0.0001), summarize(rows, 0.0003)
    print(f"{tp:6.1f} | {hold:9d} | {lab:8s} | {s['trades/an']:9.0f} | {s['gagnants']:8.0%} | {s['R moyen']:+11.3f} | {s['%/an']:+8.1f} |"
          f" {s['%/an avant 2019']:+10.1f} | {s['%/an depuis 2019']:+11.1f} | {s3['%/an']:+8.1f} | {s['pire baisse %']:+.1f}")

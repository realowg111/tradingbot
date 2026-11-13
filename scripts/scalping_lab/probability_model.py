"""Directional-probability scalper ("sentiment & confiance" gauge of the video, done properly).

Every 5 minutes of the Nasdaq session (10:00-15:30 New York), a gradient-boosting model reads
the 12 indicators shown in the video plus the validated noise-boundary regime and estimates
p = probability that the price touches +3 ATR(1 min) before -3 ATR within 30 minutes.
  - long  if p >= threshold      (confidence = p)
  - short if p <= 1 - threshold  (confidence = 1 - p)
TP = SL = 3 ATR from the next bar's open, max holding 30 minutes, flat at 15:59, one position
at a time, SL first when both are inside one bar.

Honest test (walk-forward): for each year Y from 2017, the model is trained only on the years
before Y and then used, frozen, on Y. Nothing of year Y is seen in training.
Data: QQQ 1-minute bars 2014-2024. Costs 0.01 % per round trip (x3 stress). 0.5 % risk per trade.

Usage: python3 probability_model.py qqq.parquet
"""
import os, sys
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "nine_am_cr"))
from nine_am_cr_backtest import load_qqq            # noqa: E402
from scalping_lab import by_day, walk, nasdaq_regimes, ema, vwap_sd   # noqa: E402

K_ATR, HORIZON, STEP, RISK = 3.0, 30, 5, 0.5
COST = 0.0001
FEATURES = ["rsi14", "macd", "ema20", "ema200", "bb", "volratio", "vwap", "mom5", "mom15",
            "brk_hi", "brk_lo", "structure", "regime", "minute", "ret_open"]


def day_features(day, regime):
    dt, t, o, h, l, c, v = day
    s = pd.Series(c)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).rolling(14, min_periods=5).mean().to_numpy()
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
    macd = ema(c, 12) - ema(c, 26)
    hist = macd - ema(macd, 9)
    mid, sd20 = s.rolling(20, min_periods=5).mean().to_numpy(), s.rolling(20, min_periods=5).std().to_numpy()
    vw, _ = vwap_sd(h, l, c, v)
    hi20 = pd.Series(h).rolling(20, min_periods=5).max().shift(1).to_numpy()
    lo20 = pd.Series(l).rolling(20, min_periods=5).min().shift(1).to_numpy()
    hi12 = pd.Series(h).rolling(12, min_periods=5).max().to_numpy()
    lo12 = pd.Series(l).rolling(12, min_periods=5).min().to_numpy()
    atr100 = pd.Series(tr).rolling(100, min_periods=20).mean().to_numpy()
    a = np.where(atr > 0, atr, np.nan)
    f = pd.DataFrame({
        "rsi14": rsi, "macd": hist / a, "ema20": (c - ema(c, 20)) / a, "ema200": (c - ema(c, 200)) / a,
        "bb": (c - mid) / (2 * sd20 + 1e-12), "volratio": atr / atr100, "vwap": (c - vw) / a,
        "mom5": (c - np.r_[np.full(5, np.nan), c[:-5]]) / a, "mom15": (c - np.r_[np.full(15, np.nan), c[:-15]]) / a,
        "brk_hi": (c - hi20) / a, "brk_lo": (c - lo20) / a, "structure": (c - lo12) / (hi12 - lo12 + 1e-12),
        "regime": regime, "minute": t, "ret_open": (c / o[0] - 1) / (a / c),
    })
    return f, atr


def build(days, regs):
    rows = []
    for day in days:
        if day[0] not in regs:
            continue
        dt, t, o, h, l, c, v = day
        f, atr = day_features(day, regs[day[0]])
        for k in range(30, len(c) - 1):
            if t[k] < 600 or t[k] > 930 or (t[k] - 570) % STEP != 0 or not atr[k] > 0:
                continue
            j = k + 1
            en, dist = o[j], K_ATR * atr[k]
            exl, kl = walk(o, h, l, c, t, j, 1, en, en - dist, en + dist, HORIZON, 959)
            exs, ks = walk(o, h, l, c, t, j, -1, en, en + dist, en - dist, HORIZON, 959)
            rows.append({"day": dt, "k": k, "t": t[k], **f.iloc[k].to_dict(),
                         "R_long": (exl - en) / dist, "R_short": (en - exs) / dist,
                         "exit_long": t[kl], "exit_short": t[ks], "risk": dist / en})
    return pd.DataFrame(rows)


def simulate(df, p, thr, cost):
    """One position at a time; returns trade R after costs, indexed by day."""
    out, busy_until, cur_day = [], -1, None
    for (day, tt, rl, rs, xl, xs, risk), pp in zip(df[["day", "t", "R_long", "R_short", "exit_long", "exit_short", "risk"]].itertuples(index=False), p):
        if day != cur_day:
            cur_day, busy_until = day, -1
        if tt <= busy_until:
            continue
        if pp >= thr:
            out.append((day, rl - cost / risk)); busy_until = xl
        elif pp <= 1 - thr:
            out.append((day, rs - cost / risk)); busy_until = xs
    return pd.Series([r for _, r in out], index=pd.DatetimeIndex([d for d, _ in out]), dtype=float)


if __name__ == "__main__":
    days = by_day(load_qqq(sys.argv[1]), 570, 960)
    regs = nasdaq_regimes(days)
    df = build(days, regs).dropna(subset=FEATURES[:-1]).reset_index(drop=True)
    df["y"] = (df["R_long"] > 0).astype(int)
    years = df["day"].dt.year
    print(f"{len(df)} décisions, {df['day'].nunique()} séances ; touche +3 ATR d'abord : {df['y'].mean():.1%}\n")

    p = np.full(len(df), np.nan)
    for Y in range(2017, years.max() + 1):
        tr, te = years < Y, years == Y
        if te.sum() == 0:
            continue
        m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=31,
                                           min_samples_leaf=200, l2_regularization=1.0, random_state=0)
        m.fit(df.loc[tr, FEATURES], df.loc[tr, "y"])
        p[te.to_numpy()] = m.predict_proba(df.loc[te, FEATURES])[:, 1]
    test = ~np.isnan(p)
    dt, pt = df[test].reset_index(drop=True), p[test]

    # calibration: does "70 % confidence" really win 70 % of the time?
    conf = np.maximum(pt, 1 - pt)
    won = np.where(pt >= 0.5, dt["R_long"] > 0, dt["R_short"] > 0)
    print("Calibration (hors échantillon, 2017-2024) : confiance annoncée -> taux de réussite réel")
    for lo_, hi_ in [(0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 1.0)]:
        sel = (conf >= lo_) & (conf < hi_)
        if sel.sum():
            print(f"  {lo_:.0%}-{hi_:.0%} : {sel.sum():6d} décisions, réussite réelle {won[sel].mean():.1%}")

    print(f"\nTrading hors échantillon 2017-2024 (TP = SL = {K_ATR:.0f} ATR, {RISK} % de risque par trade) :")
    print("  seuil | trades/an | gagnants | R moyen net | %/an net | 2017-2019 | 2020-2024 | frais x3 %/an")
    for thr in (0.55, 0.6, 0.65, 0.7):
        R = simulate(dt, pt, thr, COST)
        if len(R) < 20:
            print(f"  {thr:.2f} | trop peu de trades ({len(R)})"); continue
        yrs = (R.index[-1] - R.index[0]).days / 365.25
        a_, b_ = R[R.index.year < 2020], R[R.index.year >= 2020]
        R3 = simulate(dt, pt, thr, 3 * COST)
        print(f"  {thr:.2f} | {len(R) / yrs:9.0f} | {(R > 0).mean():8.0%} | {R.mean():+11.3f} | {R.sum() * RISK / yrs:+8.1f} |"
              f" {a_.sum() * RISK / 3:+9.1f} | {b_.sum() * RISK / max(0.5, (b_.index[-1] - b_.index[0]).days / 365.25) if len(b_) else 0:+9.1f} |"
              f" {R3.sum() * RISK / yrs:+.1f}")
        if thr == 0.6:
            yr = R.groupby(R.index.year).sum() * RISK
            print("        par année : " + " ".join(f"{k}:{v:+.0f}%" for k, v in yr.items()))

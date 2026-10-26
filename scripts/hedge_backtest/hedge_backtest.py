"""Backtest of hedge strategies doable with MoonX futures (long + short perps).
Signals use close[t]; positions earn return of bar t+1 (no look-ahead).
Costs: taker fee per side per leg, funding paid by longs / received by shorts.
"""
import os, sys, itertools
import numpy as np, pandas as pd

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FEE = 0.0006          # 0.06% per side (typical perp taker fee)
FUND_DAY = 0.0003     # 0.01% per 8h = 0.03%/day, longs pay shorts (typical positive funding)

def load(sym, tf="1d"):
    df = pd.read_csv(f"{D}/{sym}_{tf}.csv")
    return pd.Series(df["close"].values, index=pd.to_datetime(df["time"], unit="ms"))

def run(weights, prices, bars_per_day):
    """weights: DataFrame of target notional weights per asset (fraction of equity), decided at close t."""
    rets = prices.pct_change().fillna(0)
    w = weights.shift(1).fillna(0)                      # trade at next bar
    gross = (w * rets).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).shift(1).fillna(0)
    fees = turnover * FEE
    funding = (w.clip(lower=0).sum(axis=1) - (-w.clip(upper=0)).sum(axis=1)) * FUND_DAY / bars_per_day
    net = gross - fees - funding
    eq = (1 + net).cumprod()
    return eq, net, turnover

def stats(eq, net, turnover, bars_per_day, name):
    n = len(net)
    yrs = n / bars_per_day / 365
    tot = eq.iloc[-1] - 1
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    sd = net.std()
    sharpe = net.mean() / sd * np.sqrt(365 * bars_per_day) if sd > 0 else 0
    dd = (eq / eq.cummax() - 1).min()
    return dict(strat=name, total=tot, cagr=cagr, sharpe=sharpe, maxdd=dd,
                trades=int((turnover > 0).sum()), calmar=cagr / abs(dd) if dd < 0 else np.nan)

# ---------- strategies ----------
def buy_hold(p, a):
    return pd.DataFrame({a: 1.0}, index=p.index)

def static_hedge(p, a, ratio=0.5):
    # long 1x + short `ratio` on same perp = net long (1-ratio). Fees on both legs at open only.
    return pd.DataFrame({a: 1.0 - ratio}, index=p.index)

def trend_hedge(p, a, n=50):
    # hold long; open a 100% short hedge (=> flat) when close < SMA(n)
    sma = p[a].rolling(n).mean()
    w = np.where(p[a] > sma, 1.0, 0.0)
    w[: n] = 1.0
    return pd.DataFrame({a: w}, index=p.index)

def trend_hedge_partial(p, a, n=50, h=0.5):
    sma = p[a].rolling(n).mean()
    w = np.where(p[a] > sma, 1.0, 1.0 - h)
    w[: n] = 1.0
    return pd.DataFrame({a: w}, index=p.index)

def beta_hedge(p, a, b, win=60):
    # long a, short beta*b continuously (cross-hedge of market risk)
    ra, rb = np.log(p[a]).diff(), np.log(p[b]).diff()
    beta = (ra.rolling(win).cov(rb) / rb.rolling(win).var()).clip(0, 2).fillna(1.0)
    beta = beta.round(1)  # avoid daily micro-rebalancing
    return pd.DataFrame({a: 1.0, b: -beta}, index=p.index)

def pairs(p, a, b, win=60, z_in=2.0, z_out=0.0, z_stop=4.0, gross=1.0):
    la, lb = np.log(p[a]), np.log(p[b])
    beta = la.rolling(win).cov(lb) / lb.rolling(win).var()
    spread = la - beta * lb
    z = (spread - spread.rolling(win).mean()) / spread.rolling(win).std()
    pos = np.zeros(len(p)); cur = 0
    for i in range(len(p)):
        zi = z.iloc[i]
        if np.isnan(zi): pos[i] = 0; continue
        if cur == 0:
            if zi > z_in: cur = -1          # spread rich: short a, long b
            elif zi < -z_in: cur = 1
        elif cur == 1 and (zi >= -z_out or zi < -z_stop): cur = 0
        elif cur == -1 and (zi <= z_out or zi > z_stop): cur = 0
        pos[i] = cur
    bt_raw = beta.clip(0.2, 3).fillna(1).values
    bt = np.ones(len(p)); last = 1.0
    for i in range(len(p)):           # freeze hedge ratio at entry, no daily rebalancing
        if pos[i] != 0 and (i == 0 or pos[i-1] != pos[i]): last = bt_raw[i]
        bt[i] = last
    wa = pos * gross / (1 + bt)
    wb = -pos * gross * bt / (1 + bt)
    return pd.DataFrame({a: wa, b: wb}, index=p.index)

# ---------- run ----------
def evaluate(builder, prices, bpd, name, split=None):
    w = builder(prices)
    out = []
    eq, net, to = run(w, prices, bpd)
    out.append(stats(eq, net, to, bpd, name))
    if split is not None:
        for tag, sl in (("IS", slice(None, split)), ("OOS", slice(split, None))):
            e, n_, t = run(w.iloc[sl], prices.iloc[sl], bpd)
            out.append(stats(e, n_, t, bpd, f"{name} [{tag}]"))
    return out, eq

if __name__ == "__main__":
    px = pd.concat({s: load(s) for s in ["BTC", "ETH", "SOL"]}, axis=1).dropna()
    split = int(len(px) * 0.6)
    print("period", px.index[0].date(), "->", px.index[-1].date(), "split at", px.index[split].date())
    rows, curves = [], {}

    def add(name, f, prices=px, bpd=1, sp=split):
        r, eq = evaluate(f, prices, bpd, name, sp)
        rows.extend(r); curves[name] = eq

    for a in ["BTC", "ETH", "SOL"]:
        add(f"Buy&Hold {a}", lambda p, a=a: buy_hold(p, a))
    add("Hedge statique 50% BTC", lambda p: static_hedge(p, "BTC"))
    for n in (20, 50, 100):
        add(f"Trend hedge BTC SMA{n}", lambda p, n=n: trend_hedge(p, "BTC", n))
    add("Trend hedge 50% BTC SMA50", lambda p: trend_hedge_partial(p, "BTC", 50, 0.5))
    add("Trend hedge ETH SMA50", lambda p: trend_hedge(p, "ETH", 50))
    add("Beta hedge long BTC / short ETH", lambda p: beta_hedge(p, "BTC", "ETH"))
    add("Beta hedge long ETH / short BTC", lambda p: beta_hedge(p, "ETH", "BTC"))

    # pairs: grid search on IS only, then report OOS of the IS winner
    grid = list(itertools.product([30, 60, 90], [1.5, 2.0, 2.5]))
    for a, b in [("ETH", "BTC"), ("SOL", "BTC"), ("SOL", "ETH")]:
        best = None
        for win, zin in grid:
            w = pairs(px, a, b, win, zin)
            e, n_, t = run(w.iloc[:split], px.iloc[:split], 1)
            s = stats(e, n_, t, 1, "")
            if best is None or s["sharpe"] > best[0]:
                best = (s["sharpe"], win, zin)
        _, win, zin = best
        add(f"Pairs {a}/{b} (win{win}, z{zin})", lambda p, a=a, b=b, win=win, zin=zin: pairs(p, a, b, win, zin))
        # robustness: all grid points full period
        allg = []
        for wn, zn in grid:
            e, n_, t = run(pairs(px, a, b, wn, zn), px, 1)
            allg.append(stats(e, n_, t, 1, "")["total"])
        print(f"  grid {a}/{b}: total return over 9 params -> median {np.median(allg):+.1%}, "
              f"min {min(allg):+.1%}, max {max(allg):+.1%}, positive {sum(x>0 for x in allg)}/9")

    print("Trend-hedge robustness (total return, full period / OOS):")
    for a in ["BTC","ETH","SOL"]:
        line=[]
        for n in (20,30,50,75,100,150):
            w=trend_hedge(px,a,n); e,n_,t=run(w,px,1); e2,n2,t2=run(w.iloc[split:],px.iloc[split:],1)
            line.append(f"SMA{n}: {e.iloc[-1]-1:+.0%}/{e2.iloc[-1]-1:+.0%}")
        bh=px[a].iloc[-1]/px[a].iloc[0]-1
        print(f"  {a} (prix seul {bh:+.0%}): "+", ".join(line))
    # 4h pairs ETH/BTC (83 days)
    p4 = pd.concat({s: load(s, "4h") for s in ["BTC", "ETH"]}, axis=1).dropna()
    for win in (60, 120):
        r, eq = evaluate(lambda p, win=win: pairs(p, "ETH", "BTC", win, 2.0), p4, 6, f"Pairs ETH/BTC 4h (win{win}, z2)")
        rows.extend(r)
    r, eq = evaluate(lambda p: buy_hold(p, "BTC"), p4, 6, "Buy&Hold BTC 4h (83j)"); rows.extend(r)

    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200); pd.set_option("display.max_rows", 200)
    fmt = df.copy()
    for c in ("total", "cagr", "maxdd"): fmt[c] = fmt[c].map(lambda x: f"{x:+.1%}")
    for c in ("sharpe", "calmar"): fmt[c] = fmt[c].map(lambda x: f"{x:.2f}")
    print(fmt.to_string(index=False))
    df.to_csv(os.path.join(D, "..", "results.csv"), index=False)

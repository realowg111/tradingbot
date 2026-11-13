"""Build EURUSD 5-minute bars (New York time) from OANDA 1-minute bars mirrored on Hugging Face
(bunqi/OANDA_EURUSD_EURUSD, folder 1/, one parquet file per month, UTC unix timestamps).
Same output format as prepare_data.py, so every backtest script runs unchanged on EURUSD.

Usage: python3 prepare_eurusd.py <dir with YYYY-MM.parquet files> <output.pkl>
"""
import glob, os, sys
import pandas as pd

if __name__ == "__main__":
    raw, out = sys.argv[1], sys.argv[2]
    parts = []
    for f in sorted(glob.glob(os.path.join(raw, "*.parquet"))):
        d = pd.read_parquet(f)
        d.index = pd.to_datetime(d.pop("time"), unit="s", utc=True).dt.tz_convert("America/New_York")
        parts.append(d[["open", "high", "low", "close"]])
    m1 = pd.concat(parts).sort_index()
    m1 = m1[~m1.index.duplicated()]
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    m5 = m1.resample("5min", label="left", closed="left").agg(agg).dropna()
    m5.to_pickle(out)
    print(f"{len(m5)} bars, {m5.index[0]} -> {m5.index[-1]}")

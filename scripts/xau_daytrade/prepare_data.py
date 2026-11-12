"""Download HistData XAUUSD M1 bars (mirror on Hugging Face) and build 5-minute bars in New York time.

Usage: python3 prepare_data.py [data_dir]
Writes <data_dir>/xau_5m.pkl (index tz America/New_York, columns open/high/low/close).
HistData MT files are bid prices. Their docs say EST without DST, but the daily break shows the
stamps actually follow European DST (see load_m1).
"""
import os, sys, subprocess
import pandas as pd

REPO = "https://huggingface.co/datasets/fokan/xauusd-2009-2026/resolve/main"
FILES = [str(y) for y in range(2009, 2026)] + ["202601"]


def download(raw):
    os.makedirs(raw, exist_ok=True)
    for f in FILES:
        path = os.path.join(raw, f"y{f}.csv")
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            subprocess.run(["curl", "-sSL", "--retry", "3", "-o", path, f"{REPO}/DAT_MT_XAUUSD_M1_{f}.csv"], check=True)


def load_m1(raw):
    parts = []
    for f in FILES:
        df = pd.read_csv(os.path.join(raw, f"y{f}.csv"), header=None,
                         names=["d", "t", "open", "high", "low", "close", "v"])
        ts = pd.to_datetime(df["d"] + " " + df["t"], format="%Y.%m.%d %H:%M")
        # Stamps follow European DST: stamp = Berlin time - 6h (checked: the 17:00-18:00 ET daily
        # break then lands at the same New York hour all year, including the March/October gap weeks).
        loc = (ts + pd.Timedelta(hours=6)).dt.tz_localize("Europe/Berlin", ambiguous="NaT", nonexistent="NaT")
        df.index = loc.dt.tz_convert("America/New_York")
        df = df[df.index.notna()]
        parts.append(df[["open", "high", "low", "close"]])
    m1 = pd.concat(parts).sort_index()
    return m1[~m1.index.duplicated()]


def to_5m(m1):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return m1.resample("5min", label="left", closed="left").agg(agg).dropna()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "data")
    raw = os.path.join(out, "raw")
    download(raw)
    m5 = to_5m(load_m1(raw))
    m5.to_pickle(os.path.join(out, "xau_5m.pkl"))
    print(f"{len(m5)} bars, {m5.index[0]} -> {m5.index[-1]}")

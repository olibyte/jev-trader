"""Throwaway measurement. Reads local Parquet bars, writes bars and reference levels for bench.mjs.

Run: PYTHONDONTWRITEBYTECODE=1 <research venv python> dump.py <data_dir> <out_dir>
"""

import gzip
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from jevtrader.states import STUDY, CASH, levels, state_rows

data_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
END = date(2026, 10, 9)
bars_out, levels_out, rows_out = {}, {}, {}
total_rows = 0
f32 = bytearray()
f64 = bytearray()
for s in (*STUDY, CASH):
    bars = pl.read_parquet(data_dir / "market" / f"{s}.parquet").filter(pl.col("date") <= END)
    total_rows += bars.height
    bars_out[s] = {
        "date": [d.isoformat() for d in bars["date"]],
        **{c: bars[c].to_list() for c in ("open", "high", "low", "close")},
    }
    days = np.array([(d - date(1970, 1, 1)).days for d in bars["date"]], dtype=np.int32)
    ohlc = bars.select("open", "high", "low", "close").to_numpy()
    f32 += days.tobytes() + ohlc.astype(np.float32).tobytes()
    f64 += days.tobytes() + ohlc.astype(np.float64).tobytes()
    if s != CASH:
        lv = levels(bars)
        levels_out[s] = {c: [None if v is None else str(v) for v in lv[c]] for c in lv.columns if c != "date"}
        r = state_rows(s, bars)
        rows_out[s] = {"date": [d.isoformat() for d in r["date"]], "split": r["split"].to_list()}

(out / "bars.json").write_text(json.dumps(bars_out))
(out / "levels.json").write_text(json.dumps(levels_out))
(out / "rows.json").write_text(json.dumps(rows_out))
(out / "bars.f32.bin").write_bytes(bytes(f32))
(out / "bars.f64.bin").write_bytes(bytes(f64))
print("symbols", len(bars_out), "total bars", total_rows)
for name in ("bars.json", "bars.f32.bin", "bars.f64.bin"):
    raw = (out / name).read_bytes()
    print(f"{name}: raw {len(raw)/1e6:.2f} MB, gzip -9 {len(gzip.compress(raw, 9))/1e6:.2f} MB")

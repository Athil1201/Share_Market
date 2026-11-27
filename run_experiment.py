"""CLI: run the experiment for every stock and print an honest summary."""
import pandas as pd
from core import STOCKS, run

pd.set_option("display.float_format", lambda x: f"{x:.3f}")
for name, tk in list(STOCKS.items())[:5]:
    r = run(tk)
    print(f"\n=== {name} ({tk}) | test-period share of up-days: {r['up_rate']:.1%} ===")
    print(r["table"])

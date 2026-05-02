"""
prepare_kaggle.py
-----------------
Converts the Kaggle S&P 500 dataset (camnugent/sandp500) into
internal blotter + broker confirm CSVs with realistic injected breaks.

Usage:
    python prepare_kaggle.py --input all_stocks_5yr.csv --n 500 --seed 42
    python prepare_kaggle.py --input all_stocks_5yr.csv --n 1000 --output-dir ../data

Dataset: https://www.kaggle.com/datasets/camnugent/sandp500
Expected columns: date, open, high, low, close, volume, Name
"""

import argparse
import json
import os
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# ── Break injection rates (realistic ops environment) ──────────────────────
BREAK_RATES = {
    "price_mismatch":       0.08,   # 8%  of trades get a broker price shift >1%
    "qty_mismatch":         0.05,   # 5%  quantity differs
    "side_mismatch":        0.03,   # 3%  buy/sell flipped
    "settle_date_mismatch": 0.04,   # 4%  broker books T+3 instead of T+2
    "missing_in_broker":    0.05,   # 5%  broker never sent a confirm
    "missing_in_internal":  0.03,   # 3%  broker has an extra trade
}


def load_sp500(path: str, n: int, seed: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    # Rename 'name' -> 'symbol' if present
    if "name" in df.columns:
        df.rename(columns={"name": "symbol"}, inplace=True)

    required = {"date", "close", "volume", "symbol"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}. Found: {list(df.columns)}")

    df = df.dropna(subset=["close", "volume", "symbol"])
    df = df[df["close"] > 0]
    df = df[df["volume"] > 0]

    # Sample n rows reproducibly
    df = df.sample(n=min(n, len(df)), random_state=seed).reset_index(drop=True)
    return df


def derive_trades(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    trades = pd.DataFrame()
    trades["trade_id"]        = ["TRD-" + str(i).zfill(6) for i in range(len(df))]
    trades["symbol"]          = df["symbol"].values
    trades["price"]           = df["close"].round(4).values
    # Quantity: scale volume down to a realistic lot size
    trades["quantity"]        = (df["volume"] / 1000).clip(lower=1).round(0).astype(int).values
    # Side: BUY if close >= open (upday), else SELL — fallback random if open missing
    if "open" in df.columns:
        trades["side"] = np.where(df["close"].values >= df["open"].values, "BUY", "SELL")
    else:
        trades["side"] = rng.choice(["BUY", "SELL"], size=len(df))
    # T+2 settlement
    trades["settlement_date"] = pd.to_datetime(df["date"]).apply(
        lambda d: (d + timedelta(days=2)).strftime("%Y-%m-%d")
    ).values

    return trades


def inject_breaks(internal: pd.DataFrame, seed: int):
    rng = np.random.default_rng(seed)
    broker = internal.copy()
    manifest = []   # ground truth for validation

    n = len(internal)
    indices = list(range(n))

    def sample_idx(rate, exclude=set()):
        pool = [i for i in indices if i not in exclude]
        k = max(1, int(len(pool) * rate))
        return rng.choice(pool, size=min(k, len(pool)), replace=False).tolist()

    used = set()

    # 1. PRICE_MISMATCH — shift broker price by 1.5–4%
    price_idx = sample_idx(BREAK_RATES["price_mismatch"], used)
    for i in price_idx:
        shift = rng.uniform(0.015, 0.04) * rng.choice([-1, 1])
        orig = broker.at[i, "price"]
        broker.at[i, "price"] = round(orig * (1 + shift), 4)
        manifest.append({"trade_id": broker.at[i, "trade_id"], "break_type": "PRICE_MISMATCH",
                         "internal_value": orig, "broker_value": broker.at[i, "price"]})
    used.update(price_idx)

    # 2. QTY_MISMATCH — broker quantity off by ±5–20%
    qty_idx = sample_idx(BREAK_RATES["qty_mismatch"], used)
    for i in qty_idx:
        shift = rng.uniform(0.05, 0.20) * rng.choice([-1, 1])
        orig = broker.at[i, "quantity"]
        broker.at[i, "quantity"] = max(1, int(orig * (1 + shift)))
        manifest.append({"trade_id": broker.at[i, "trade_id"], "break_type": "QTY_MISMATCH",
                         "internal_value": orig, "broker_value": broker.at[i, "quantity"]})
    used.update(qty_idx)

    # 3. SIDE_MISMATCH — flip BUY/SELL
    side_idx = sample_idx(BREAK_RATES["side_mismatch"], used)
    for i in side_idx:
        orig = broker.at[i, "side"]
        broker.at[i, "side"] = "SELL" if orig == "BUY" else "BUY"
        manifest.append({"trade_id": broker.at[i, "trade_id"], "break_type": "SIDE_MISMATCH",
                         "internal_value": orig, "broker_value": broker.at[i, "side"]})
    used.update(side_idx)

    # 4. SETTLE_DATE_MISMATCH — broker books T+3 instead of T+2
    settle_idx = sample_idx(BREAK_RATES["settle_date_mismatch"], used)
    for i in settle_idx:
        orig = broker.at[i, "settlement_date"]
        new_date = (pd.to_datetime(orig) + timedelta(days=1)).strftime("%Y-%m-%d")
        broker.at[i, "settlement_date"] = new_date
        manifest.append({"trade_id": broker.at[i, "trade_id"], "break_type": "SETTLE_DATE_MISMATCH",
                         "internal_value": orig, "broker_value": new_date})
    used.update(settle_idx)

    # 5. MISSING_IN_BROKER — drop rows from broker file
    missing_broker_idx = sample_idx(BREAK_RATES["missing_in_broker"], used)
    missing_broker_ids = set(broker.iloc[missing_broker_idx]["trade_id"].tolist())
    for tid in missing_broker_ids:
        manifest.append({"trade_id": tid, "break_type": "MISSING_IN_BROKER",
                         "internal_value": "present", "broker_value": "absent"})
    broker = broker[~broker["trade_id"].isin(missing_broker_ids)].reset_index(drop=True)
    used.update(missing_broker_idx)

    # 6. MISSING_IN_INTERNAL — inject phantom broker trades
    k_extra = max(1, int(n * BREAK_RATES["missing_in_internal"]))
    phantom_ids = ["TRD-XTRA-" + str(i).zfill(4) for i in range(k_extra)]
    symbols = internal["symbol"].sample(k_extra, random_state=int(seed)).values
    prices  = internal["price"].sample(k_extra, random_state=int(seed)+1).values
    qtys    = internal["quantity"].sample(k_extra, random_state=int(seed)+2).values
    sides   = rng.choice(["BUY", "SELL"], size=k_extra)
    dates   = internal["settlement_date"].sample(k_extra, random_state=int(seed)+3).values

    phantoms = pd.DataFrame({
        "trade_id": phantom_ids, "symbol": symbols, "price": prices,
        "quantity": qtys, "side": sides, "settlement_date": dates
    })
    broker = pd.concat([broker, phantoms], ignore_index=True)
    for tid in phantom_ids:
        manifest.append({"trade_id": tid, "break_type": "MISSING_IN_INTERNAL",
                         "internal_value": "absent", "broker_value": "present"})

    return internal, broker, manifest


def main():
    parser = argparse.ArgumentParser(description="Prepare S&P500 Kaggle data for TradeRecon")
    parser.add_argument("--input",      required=True,  help="Path to all_stocks_5yr.csv")
    parser.add_argument("--n",          type=int, default=500, help="Number of trades to sample")
    parser.add_argument("--seed",       type=int, default=42)
    parser.add_argument("--output-dir", default="../data")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"[1/4] Loading {args.input} ...")
    raw = load_sp500(args.input, args.n, args.seed)
    print(f"      Loaded {len(raw)} rows from {raw['symbol'].nunique()} symbols")

    print("[2/4] Deriving trades ...")
    internal = derive_trades(raw, args.seed)
    print(f"      {len(internal)} trades | BUY: {(internal['side']=='BUY').sum()} | SELL: {(internal['side']=='SELL').sum()}")

    print("[3/4] Injecting breaks into broker file ...")
    internal, broker, manifest = inject_breaks(internal, args.seed)

    break_summary = {}
    for m in manifest:
        break_summary[m["break_type"]] = break_summary.get(m["break_type"], 0) + 1
    print(f"      Injected {len(manifest)} breaks: {break_summary}")

    print("[4/4] Writing output files ...")
    int_path  = os.path.join(args.output_dir, "internal_trades.csv")
    brk_path  = os.path.join(args.output_dir, "broker_confirms.csv")
    man_path  = os.path.join(args.output_dir, "break_manifest.json")

    internal.to_csv(int_path, index=False)
    broker.to_csv(brk_path, index=False)
    with open(man_path, "w") as f:
        # Convert numpy types before dumping
        def to_python(obj):
         if hasattr(obj, 'item'):
            return obj.item()
         if isinstance(obj, dict):
            return {k: to_python(v) for k, v in obj.items()}
         if isinstance(obj, list):
            return [to_python(i) for i in obj]
        return obj

    with open(man_path, "w") as f:
        json.dump(to_python({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_trades": len(internal),
            "total_breaks": len(manifest),
            "break_summary": break_summary,
            "breaks": manifest
        }), f, indent=2)
        
    print(f"\n✓ internal_trades.csv  → {int_path}  ({len(internal)} rows)")
    print(f"✓ broker_confirms.csv  → {brk_path}  ({len(broker)} rows)")
    print(f"✓ break_manifest.json  → {man_path}  ({len(manifest)} ground-truth breaks)")
    print("\nNow run: python app.py")
    print("Then POST /api/reconcile with the two CSV files, or")
    print("     GET  /api/validate   to auto-load + score engine accuracy")


if __name__ == "__main__":
    main()

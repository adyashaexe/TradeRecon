from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import io
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

PRICE_TOLERANCE = 0.01          # 1% price tolerance
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


# ─────────────────────────────────────────────────────────────
# CORE UTILITIES
# ─────────────────────────────────────────────────────────────

def parse_csv(file_bytes):
    return pd.read_csv(io.BytesIO(file_bytes))


def normalize_columns(df, source):
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df["source"] = source
    return df


def classify_break(internal_row, broker_row):
    breaks = []

    # Price mismatch
    try:
        int_price = float(internal_row["price"])
        brk_price = float(broker_row["price"])
        diff = abs(int_price - brk_price) / max(abs(int_price), 0.0001)
        if diff > PRICE_TOLERANCE:
            breaks.append(
                f"PRICE_MISMATCH (internal={int_price:.4f}, "
                f"broker={brk_price:.4f}, diff={diff*100:.2f}%)"
            )
    except Exception:
        breaks.append("PRICE_PARSE_ERROR")

    # Quantity mismatch
    try:
        int_qty = float(internal_row["quantity"])
        brk_qty = float(broker_row["quantity"])
        if int_qty != brk_qty:
            breaks.append(f"QTY_MISMATCH (internal={int_qty:.0f}, broker={brk_qty:.0f})")
    except Exception:
        breaks.append("QTY_PARSE_ERROR")

    # Side mismatch
    try:
        int_side = str(internal_row.get("side", "")).strip().upper()
        brk_side = str(broker_row.get("side", "")).strip().upper()
        if int_side and brk_side and int_side != brk_side:
            breaks.append(f"SIDE_MISMATCH (internal={int_side}, broker={brk_side})")
    except Exception:
        pass

    # Settlement date mismatch
    try:
        int_date = str(internal_row.get("settlement_date", "")).strip()
        brk_date = str(broker_row.get("settlement_date", "")).strip()
        if int_date and brk_date and int_date != brk_date:
            breaks.append(
                f"SETTLE_DATE_MISMATCH (internal={int_date}, broker={brk_date})"
            )
    except Exception:
        pass

    return breaks


def run_reconciliation(internal_df, broker_df):
    results = []
    summary = {
        "total_internal":       len(internal_df),
        "total_broker":         len(broker_df),
        "matched":              0,
        "matched_with_breaks":  0,
        "missing_in_broker":    0,
        "missing_in_internal":  0,
        "total_breaks":         0,
        "break_types":          {},
    }

    internal_ids = set(internal_df["trade_id"].astype(str))
    broker_ids   = set(broker_df["trade_id"].astype(str))

    internal_map = {str(r["trade_id"]): r for _, r in internal_df.iterrows()}
    broker_map   = {str(r["trade_id"]): r for _, r in broker_df.iterrows()}

    # Matched trades (present in both)
    for tid in internal_ids & broker_ids:
        int_row = internal_map[tid]
        brk_row = broker_map[tid]
        breaks  = classify_break(int_row, brk_row)

        status = "MATCHED" if not breaks else "BREAK"
        if status == "MATCHED":
            summary["matched"] += 1
        else:
            summary["matched_with_breaks"] += 1
            summary["total_breaks"] += len(breaks)
            for b in breaks:
                btype = b.split("(")[0].strip()
                summary["break_types"][btype] = summary["break_types"].get(btype, 0) + 1

        results.append({
            "trade_id":        tid,
            "symbol":          str(int_row.get("symbol", "")),
            "side":            str(int_row.get("side", "")),
            "quantity":        str(int_row.get("quantity", "")),
            "internal_price":  str(int_row.get("price", "")),
            "broker_price":    str(brk_row.get("price", "")),
            "internal_settle": str(int_row.get("settlement_date", "")),
            "broker_settle":   str(brk_row.get("settlement_date", "")),
            "status":          status,
            "breaks":          breaks,
            "break_count":     len(breaks),
        })

    # Missing in broker
    for tid in internal_ids - broker_ids:
        int_row = internal_map[tid]
        summary["missing_in_broker"] += 1
        summary["total_breaks"] += 1
        summary["break_types"]["MISSING_IN_BROKER"] = (
            summary["break_types"].get("MISSING_IN_BROKER", 0) + 1
        )
        results.append({
            "trade_id":        tid,
            "symbol":          str(int_row.get("symbol", "")),
            "side":            str(int_row.get("side", "")),
            "quantity":        str(int_row.get("quantity", "")),
            "internal_price":  str(int_row.get("price", "")),
            "broker_price":    "—",
            "internal_settle": str(int_row.get("settlement_date", "")),
            "broker_settle":   "—",
            "status":          "BREAK",
            "breaks":          ["MISSING_IN_BROKER"],
            "break_count":     1,
        })

    # Missing in internal
    for tid in broker_ids - internal_ids:
        brk_row = broker_map[tid]
        summary["missing_in_internal"] += 1
        summary["total_breaks"] += 1
        summary["break_types"]["MISSING_IN_INTERNAL"] = (
            summary["break_types"].get("MISSING_IN_INTERNAL", 0) + 1
        )
        results.append({
            "trade_id":        tid,
            "symbol":          str(brk_row.get("symbol", "")),
            "side":            str(brk_row.get("side", "")),
            "quantity":        str(brk_row.get("quantity", "")),
            "internal_price":  "—",
            "broker_price":    str(brk_row.get("price", "")),
            "internal_settle": "—",
            "broker_settle":   str(brk_row.get("settlement_date", "")),
            "status":          "BREAK",
            "breaks":          ["MISSING_IN_INTERNAL"],
            "break_count":     1,
        })

    results.sort(key=lambda x: (0 if x["status"] == "BREAK" else 1, x["trade_id"]))

    summary["match_rate"] = round(
        (summary["matched"] / max(summary["total_internal"], 1)) * 100, 2
    )
    return results, summary


# ─────────────────────────────────────────────────────────────
# VALIDATION — score engine accuracy against break_manifest.json
# ─────────────────────────────────────────────────────────────

def score_against_manifest(results, manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)

    # Build ground truth: trade_id -> set of injected break types
    ground_truth = {}
    for entry in manifest["breaks"]:
        tid  = entry["trade_id"]
        btyp = entry["break_type"]
        ground_truth.setdefault(tid, set()).add(btyp)

    # Build detected: trade_id -> set of detected break types
    detected = {}
    for r in results:
        if r["status"] == "BREAK":
            detected[r["trade_id"]] = {
                b.split("(")[0].strip() for b in r["breaks"]
            }

    all_types = [
        "PRICE_MISMATCH", "QTY_MISMATCH", "SIDE_MISMATCH",
        "SETTLE_DATE_MISMATCH", "MISSING_IN_BROKER", "MISSING_IN_INTERNAL",
    ]

    per_type = {}
    for btype in all_types:
        tp = sum(1 for tid, types in ground_truth.items()
                 if btype in types and btype in detected.get(tid, set()))
        fp = sum(1 for tid, types in detected.items()
                 if btype in types and btype not in ground_truth.get(tid, set()))
        fn = sum(1 for tid, types in ground_truth.items()
                 if btype in types and btype not in detected.get(tid, set()))

        precision = tp / (tp + fp) if (tp + fp) else None
        recall    = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * precision * recall / (precision + recall)
              if (precision and recall) else None)

        per_type[btype] = {
            "true_positives":  tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision":  round(precision * 100, 2) if precision is not None else None,
            "recall":     round(recall    * 100, 2) if recall    is not None else None,
            "f1_score":   round(f1        * 100, 2) if f1        is not None else None,
        }

    total_gt  = sum(len(v) for v in ground_truth.values())
    total_det = sum(len(v) for v in detected.values())
    total_tp  = sum(v["true_positives"] for v in per_type.values())
    overall_p = total_tp / total_det if total_det else 0
    overall_r = total_tp / total_gt  if total_gt  else 0
    overall_f1 = (
        2 * overall_p * overall_r / (overall_p + overall_r)
        if (overall_p + overall_r) else 0
    )

    return {
        "total_ground_truth_breaks": total_gt,
        "total_detected_breaks":     total_det,
        "overall_precision":         round(overall_p  * 100, 2),
        "overall_recall":            round(overall_r  * 100, 2),
        "overall_f1_score":          round(overall_f1 * 100, 2),
        "per_type":                  per_type,
    }


# ─────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/api/reconcile", methods=["POST"])
def reconcile():
    """Upload internal + broker CSVs, receive full reconciliation report."""
    try:
        if "internal" not in request.files or "broker" not in request.files:
            return jsonify({"error": "Both 'internal' and 'broker' files are required"}), 400

        internal_df = normalize_columns(
            parse_csv(request.files["internal"].read()), "internal"
        )
        broker_df = normalize_columns(
            parse_csv(request.files["broker"].read()), "broker"
        )

        for col in ["trade_id", "symbol", "quantity", "price"]:
            if col not in internal_df.columns:
                return jsonify({"error": f"Internal file missing column: '{col}'"}), 400
            if col not in broker_df.columns:
                return jsonify({"error": f"Broker file missing column: '{col}'"}), 400

        results, summary = run_reconciliation(internal_df, broker_df)

        return jsonify({
            "summary":      summary,
            "trades":       results,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/validate", methods=["GET"])
def validate():
    """
    Auto-loads the Kaggle-prepared CSVs from /data, runs reconciliation,
    and scores accuracy against break_manifest.json ground truth.
    Requires prepare_kaggle.py to have been run first.
    """
    try:
        int_path = os.path.join(DATA_DIR, "internal_trades.csv")
        brk_path = os.path.join(DATA_DIR, "broker_confirms.csv")
        man_path = os.path.join(DATA_DIR, "break_manifest.json")

        for p in [int_path, brk_path, man_path]:
            if not os.path.exists(p):
                return jsonify({
                    "error": (
                        f"File not found: {os.path.basename(p)}. "
                        "Run: python prepare_kaggle.py --input all_stocks_5yr.csv"
                    )
                }), 404

        internal_df = normalize_columns(pd.read_csv(int_path), "internal")
        broker_df   = normalize_columns(pd.read_csv(brk_path), "broker")

        results, summary = run_reconciliation(internal_df, broker_df)
        accuracy = score_against_manifest(results, man_path)

        return jsonify({
            "summary":      summary,
            "accuracy":     accuracy,
            "trades":       results,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "dataset":      "S&P 500 — kaggle.com/datasets/camnugent/sandp500",
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sample", methods=["GET"])
def get_sample():
    """Hardcoded mini CSVs for quick UI testing without any file upload."""
    internal_csv = """trade_id,symbol,side,quantity,price,settlement_date
T001,AAPL,BUY,100,182.50,2026-05-06
T002,MSFT,SELL,200,415.30,2026-05-06
T003,GOOGL,BUY,50,175.20,2026-05-06
T004,TSLA,SELL,75,245.80,2026-05-06
T005,AMZN,BUY,30,198.60,2026-05-06
T006,NVDA,BUY,120,875.00,2026-05-06
T007,META,SELL,90,520.10,2026-05-06
T008,JPM,BUY,150,210.40,2026-05-06
T009,GS,SELL,60,480.20,2026-05-06
T010,BAC,BUY,300,38.90,2026-05-06"""

    broker_csv = """trade_id,symbol,side,quantity,price,settlement_date
T001,AAPL,BUY,100,182.50,2026-05-06
T002,MSFT,SELL,200,416.80,2026-05-06
T003,GOOGL,BUY,55,175.20,2026-05-06
T004,TSLA,BUY,75,245.80,2026-05-06
T005,AMZN,BUY,30,198.60,2026-05-07
T006,NVDA,BUY,120,875.00,2026-05-06
T007,META,SELL,90,520.10,2026-05-06
T008,JPM,BUY,150,210.40,2026-05-06
T011,IBM,BUY,200,195.30,2026-05-06"""

    return jsonify({
        "internal_csv": internal_csv,
        "broker_csv":   broker_csv,
        "description": (
            "T001 clean | T002 price break | T003 qty break | "
            "T004 side break | T005 settle date break | "
            "T009/T010 missing in broker | T011 missing in internal"
        ),
    })


@app.route("/api/health", methods=["GET"])
def health():
    kaggle_ready = all(
        os.path.exists(os.path.join(DATA_DIR, f))
        for f in ["internal_trades.csv", "broker_confirms.csv", "break_manifest.json"]
    )
    return jsonify({
        "status":       "ok",
        "service":      "TradeRecon API",
        "kaggle_ready": kaggle_ready,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
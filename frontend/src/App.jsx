import { useState, useCallback, useRef } from "react";

const API_BASE = "http://localhost:5000/api";

const BREAK_COLORS = {
  PRICE_MISMATCH: "#f59e0b",
  QTY_MISMATCH: "#f97316",
  SIDE_MISMATCH: "#ef4444",
  SETTLE_DATE_MISMATCH: "#a78bfa",
  MISSING_IN_BROKER: "#ec4899",
  MISSING_IN_INTERNAL: "#06b6d4",
};

function BreakBadge({ label }) {
  const key = Object.keys(BREAK_COLORS).find((k) => label.startsWith(k));
  const color = key ? BREAK_COLORS[key] : "#6b7280";
  return (
    <span
      style={{
        display: "inline-block",
        background: color + "22",
        border: `1px solid ${color}66`,
        color: color,
        borderRadius: 3,
        padding: "1px 7px",
        fontSize: 10,
        fontFamily: "'IBM Plex Mono', monospace",
        letterSpacing: 0.5,
        marginRight: 4,
        marginBottom: 2,
      }}
    >
      {label.split("(")[0].trim()}
    </span>
  );
}

function StatCard({ label, value, accent, sub }) {
  return (
    <div
      style={{
        background: "#0d1117",
        border: `1px solid ${accent}44`,
        borderTop: `2px solid ${accent}`,
        padding: "16px 20px",
        flex: 1,
        minWidth: 140,
      }}
    >
      <div style={{ color: "#4b5563", fontSize: 10, letterSpacing: 2, textTransform: "uppercase", fontFamily: "'IBM Plex Mono', monospace", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ color: accent, fontSize: 28, fontWeight: 700, fontFamily: "'IBM Plex Mono', monospace", lineHeight: 1 }}>
        {value}
      </div>
      {sub && <div style={{ color: "#6b7280", fontSize: 11, marginTop: 4, fontFamily: "'IBM Plex Mono', monospace" }}>{sub}</div>}
    </div>
  );
}

function FileDropZone({ label, file, onFile, color }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef();

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  }, [onFile]);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current.click()}
      style={{
        flex: 1,
        border: `1px dashed ${dragging ? color : color + "55"}`,
        background: dragging ? color + "0a" : "#0d1117",
        padding: "24px 20px",
        cursor: "pointer",
        transition: "all 0.15s",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
      }}
    >
      <input ref={inputRef} type="file" accept=".csv" style={{ display: "none" }} onChange={e => onFile(e.target.files[0])} />
      <div style={{ fontSize: 22 }}>{file ? "📄" : "⬆"}</div>
      <div style={{ color: color, fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, letterSpacing: 1, textTransform: "uppercase" }}>{label}</div>
      {file
        ? <div style={{ color: "#9ca3af", fontSize: 11, fontFamily: "'IBM Plex Mono', monospace" }}>{file.name}</div>
        : <div style={{ color: "#4b5563", fontSize: 10, fontFamily: "'IBM Plex Mono', monospace" }}>drop CSV or click to browse</div>
      }
    </div>
  );
}

export default function App() {
  const [internalFile, setInternalFile] = useState(null);
  const [brokerFile, setBrokerFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [expandedRow, setExpandedRow] = useState(null);

  const loadSample = async () => {
    try {
      const res = await fetch(`${API_BASE}/sample`);
      const data = await res.json();
      const toFile = (content, name) => new File([content], name, { type: "text/csv" });
      setInternalFile(toFile(data.internal_csv, "internal_trades.csv"));
      setBrokerFile(toFile(data.broker_csv, "broker_confirms.csv"));
      setError(null);
    } catch {
      setError("Could not load sample data. Make sure the backend is running.");
    }
  };

  const runRecon = async () => {
    if (!internalFile || !brokerFile) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setExpandedRow(null);

    const form = new FormData();
    form.append("internal", internalFile);
    form.append("broker", brokerFile);

    try {
      const res = await fetch(`${API_BASE}/reconcile`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Unknown error");
      setResult(data);
      setFilter("ALL");
      setSearch("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const filtered = result?.trades?.filter(t => {
    const matchFilter = filter === "ALL" || t.status === filter || (filter === "BREAK" && t.status === "BREAK");
    const matchSearch = !search || t.trade_id.toLowerCase().includes(search.toLowerCase()) || t.symbol.toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  }) ?? [];

  const s = result?.summary;

  return (
    <div style={{ minHeight: "100vh", background: "#060a0f", color: "#e2e8f0", fontFamily: "'IBM Plex Mono', monospace" }}>
      {/* Google Font */}
      <style>{`@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
      * { box-sizing: border-box; }
      ::-webkit-scrollbar { width: 6px; height: 6px; } ::-webkit-scrollbar-track { background: #0d1117; } ::-webkit-scrollbar-thumb { background: #1f2937; border-radius: 3px; }
      tr:hover td { background: #0f1923 !important; }
      `}</style>

      {/* Header */}
      <div style={{ background: "#0d1117", borderBottom: "1px solid #1f2937", padding: "12px 32px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#22c55e", boxShadow: "0 0 8px #22c55e" }} />
          <span style={{ color: "#22c55e", fontSize: 13, fontWeight: 700, letterSpacing: 3, textTransform: "uppercase" }}>TradeRecon</span>
          <span style={{ color: "#1f2937", fontSize: 13 }}>|</span>
          <span style={{ color: "#4b5563", fontSize: 11, letterSpacing: 1 }}>TRADE RECONCILIATION ENGINE v1.0</span>
        </div>
        <div style={{ color: "#374151", fontSize: 10, letterSpacing: 1 }}>
          {new Date().toUTCString().toUpperCase()}
        </div>
      </div>

      <div style={{ padding: "32px", maxWidth: 1400, margin: "0 auto" }}>

        {/* Upload Section */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <div style={{ color: "#f59e0b", fontSize: 11, letterSpacing: 2, textTransform: "uppercase" }}>01 / UPLOAD FILES</div>
            <div style={{ flex: 1, height: 1, background: "#1f2937" }} />
            <button
              onClick={loadSample}
              style={{ background: "transparent", border: "1px solid #374151", color: "#6b7280", padding: "6px 14px", cursor: "pointer", fontSize: 10, letterSpacing: 1, fontFamily: "'IBM Plex Mono', monospace", textTransform: "uppercase" }}
            >
              Load Sample Data
            </button>
          </div>

          <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
            <FileDropZone label="Internal Blotter" file={internalFile} onFile={setInternalFile} color="#22c55e" />
            <FileDropZone label="Broker Confirms" file={brokerFile} onFile={setBrokerFile} color="#3b82f6" />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              onClick={runRecon}
              disabled={!internalFile || !brokerFile || loading}
              style={{
                background: internalFile && brokerFile && !loading ? "#f59e0b" : "#1f2937",
                color: internalFile && brokerFile && !loading ? "#000" : "#4b5563",
                border: "none",
                padding: "12px 32px",
                cursor: internalFile && brokerFile && !loading ? "pointer" : "not-allowed",
                fontSize: 12,
                fontWeight: 700,
                letterSpacing: 2,
                fontFamily: "'IBM Plex Mono', monospace",
                textTransform: "uppercase",
                transition: "all 0.15s",
              }}
            >
              {loading ? "RECONCILING..." : "RUN RECONCILIATION"}
            </button>
            {error && <span style={{ color: "#ef4444", fontSize: 11 }}>⚠ {error}</span>}
          </div>
        </div>

        {/* Summary Cards */}
        {s && (
          <div style={{ marginBottom: 32 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <div style={{ color: "#f59e0b", fontSize: 11, letterSpacing: 2, textTransform: "uppercase" }}>02 / SUMMARY</div>
              <div style={{ flex: 1, height: 1, background: "#1f2937" }} />
              <span style={{ color: "#374151", fontSize: 10 }}>Generated {result.generated_at}</span>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <StatCard label="Match Rate" value={`${s.match_rate}%`} accent="#22c55e" sub={`${s.matched} clean matches`} />
              <StatCard label="Total Breaks" value={s.total_breaks} accent="#ef4444" sub={`${s.matched_with_breaks} trades affected`} />
              <StatCard label="Internal Trades" value={s.total_internal} accent="#3b82f6" sub="uploaded blotter" />
              <StatCard label="Broker Confirms" value={s.total_broker} accent="#6366f1" sub="uploaded confirms" />
              <StatCard label="Missing / Broker" value={s.missing_in_broker} accent="#ec4899" sub="not in broker file" />
              <StatCard label="Missing / Internal" value={s.missing_in_internal} accent="#06b6d4" sub="not in blotter" />
            </div>

            {/* Break type breakdown */}
            {Object.keys(s.break_types).length > 0 && (
              <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {Object.entries(s.break_types).map(([type, count]) => (
                  <div key={type} style={{
                    background: "#0d1117",
                    border: `1px solid ${BREAK_COLORS[type] || "#374151"}44`,
                    padding: "6px 14px",
                    display: "flex", gap: 10, alignItems: "center"
                  }}>
                    <span style={{ color: BREAK_COLORS[type] || "#9ca3af", fontSize: 10, letterSpacing: 1 }}>{type}</span>
                    <span style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 700 }}>{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Trade Table */}
        {result && (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <div style={{ color: "#f59e0b", fontSize: 11, letterSpacing: 2, textTransform: "uppercase" }}>03 / TRADE DETAIL</div>
              <div style={{ flex: 1, height: 1, background: "#1f2937" }} />
              <div style={{ display: "flex", gap: 6 }}>
                {["ALL", "MATCHED", "BREAK"].map(f => (
                  <button key={f} onClick={() => setFilter(f)} style={{
                    background: filter === f ? "#f59e0b" : "transparent",
                    color: filter === f ? "#000" : "#6b7280",
                    border: `1px solid ${filter === f ? "#f59e0b" : "#374151"}`,
                    padding: "5px 12px",
                    cursor: "pointer",
                    fontSize: 10,
                    letterSpacing: 1,
                    fontFamily: "'IBM Plex Mono', monospace",
                  }}>{f}</button>
                ))}
              </div>
              <input
                placeholder="Search trade ID or symbol..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{
                  background: "#0d1117",
                  border: "1px solid #1f2937",
                  color: "#e2e8f0",
                  padding: "5px 12px",
                  fontSize: 11,
                  fontFamily: "'IBM Plex Mono', monospace",
                  outline: "none",
                  width: 220,
                }}
              />
            </div>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr style={{ background: "#0d1117", borderBottom: "1px solid #1f2937" }}>
                    {["Trade ID", "Symbol", "Side", "Qty", "Internal Px", "Broker Px", "Int. Settle", "Brk. Settle", "Status", "Breaks"].map(h => (
                      <th key={h} style={{ padding: "10px 12px", textAlign: "left", color: "#4b5563", letterSpacing: 1, fontSize: 10, textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((t) => (
                    <>
                      <tr
                        key={t.trade_id}
                        onClick={() => setExpandedRow(expandedRow === t.trade_id ? null : t.trade_id)}
                        style={{ borderBottom: "1px solid #0f1923", cursor: "pointer" }}
                      >
                        <td style={{ padding: "10px 12px", color: "#f59e0b", fontWeight: 600 }}>{t.trade_id}</td>
                        <td style={{ padding: "10px 12px", color: "#e2e8f0" }}>{t.symbol}</td>
                        <td style={{ padding: "10px 12px", color: t.side === "BUY" ? "#22c55e" : "#f87171" }}>{t.side}</td>
                        <td style={{ padding: "10px 12px", color: "#9ca3af" }}>{t.quantity}</td>
                        <td style={{ padding: "10px 12px", color: "#9ca3af" }}>{t.internal_price}</td>
                        <td style={{ padding: "10px 12px", color: t.internal_price !== t.broker_price && t.broker_price !== "—" ? "#f59e0b" : "#9ca3af" }}>{t.broker_price}</td>
                        <td style={{ padding: "10px 12px", color: "#9ca3af", fontSize: 10 }}>{t.internal_settle}</td>
                        <td style={{ padding: "10px 12px", color: t.internal_settle !== t.broker_settle && t.broker_settle !== "—" ? "#a78bfa" : "#9ca3af", fontSize: 10 }}>{t.broker_settle}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <span style={{
                            background: t.status === "MATCHED" ? "#22c55e22" : "#ef444422",
                            color: t.status === "MATCHED" ? "#22c55e" : "#ef4444",
                            border: `1px solid ${t.status === "MATCHED" ? "#22c55e44" : "#ef444444"}`,
                            padding: "2px 8px",
                            borderRadius: 2,
                            fontSize: 10,
                            letterSpacing: 1,
                          }}>
                            {t.status}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px" }}>
                          {t.breaks.length > 0
                            ? t.breaks.map((b, i) => <BreakBadge key={i} label={b} />)
                            : <span style={{ color: "#22c55e", fontSize: 10 }}>✓ CLEAN</span>}
                        </td>
                      </tr>
                      {expandedRow === t.trade_id && (
                        <tr key={t.trade_id + "_exp"}>
                          <td colSpan={10} style={{ background: "#0d1117", padding: "12px 24px", borderBottom: "1px solid #1f2937" }}>
                            <div style={{ display: "flex", gap: 32, fontSize: 11, color: "#6b7280" }}>
                              <div><span style={{ color: "#374151" }}>TRADE ID:</span> <span style={{ color: "#f59e0b" }}>{t.trade_id}</span></div>
                              <div><span style={{ color: "#374151" }}>SYMBOL:</span> <span style={{ color: "#e2e8f0" }}>{t.symbol}</span></div>
                              <div><span style={{ color: "#374151" }}>BREAK COUNT:</span> <span style={{ color: "#ef4444" }}>{t.break_count}</span></div>
                              {t.breaks.map((b, i) => (
                                <div key={i}><span style={{ color: "#374151" }}>BREAK {i + 1}:</span> <span style={{ color: BREAK_COLORS[b.split("(")[0].trim()] || "#9ca3af" }}>{b}</span></div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={10} style={{ padding: 32, textAlign: "center", color: "#374151" }}>No trades match current filter.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 8, color: "#374151", fontSize: 10, textAlign: "right" }}>
              Showing {filtered.length} of {result.trades.length} trades
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

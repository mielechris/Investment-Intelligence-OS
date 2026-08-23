import { useEffect, useState } from "react";

const API = "http://localhost:8000";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type InsiderRecord = {
  insider_activity_id: string;
  record_kind: string;
  form: string;
  ticker?: string;
  reporting_owner?: string;
  reporting_owner_role?: string;
  transaction_date?: string;
  filing_date?: string;
  transaction_code?: string;
  transaction_nature?: string;
  shares?: number | null;
  price_per_share?: number | null;
  dollar_value?: number | null;
  shares_owned_after?: number | null;
  plan_10b5_1?: boolean | null;
  source_url: string;
  source_name?: string;
  admission_status: string;
  secondary_source?: boolean;
  requires_primary_corroboration?: boolean;
};

type InsiderStatus = {
  case_id: string;
  records: InsiderRecord[];
  summary: {
    record_count: number;
    open_market_buys: number;
    open_market_sales: number;
    planned_10b5_1_sales: number;
    beneficial_ownership_filings: number;
    buy_dollar_value: number;
    sale_dollar_value: number;
    cluster_signal_30d: string;
    cluster_is_context_only: boolean;
  };
};

function money(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function InsiderOwnershipPanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [status, setStatus] = useState<InsiderStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Public insider/ownership data is contextual research evidence only; it never authorizes a trade.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => (current === next ? current : next));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const load = async (selectedCaseId: string) => {
    const response = await fetch(`${API}/insider/${selectedCaseId}`);
    if (!response.ok) throw new Error(`Insider status failed: ${response.status}`);
    setStatus((await response.json()) as InsiderStatus);
  };

  useEffect(() => {
    if (!caseId) {
      setStatus(null);
      return;
    }
    void load(caseId).catch((error) => setMessage(error instanceof Error ? error.message : "Insider status unavailable"));
  }, [caseId]);

  const autoCapture = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Checking SEC first, then official Micron IR, then secondary public context if both official sources are unavailable...");
    try {
      const response = await fetch(`${API}/insider/${caseId}/auto-capture`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json() as { status?: string; records_fetched?: number; records_added?: number; error?: string; provider?: string; provider_note?: string };
      if (data.status === "provider_error") {
        setMessage(`Insider providers unavailable: ${data.error ?? "unknown provider error"}. This is recorded as a provider gap, not as “no insider activity.”`);
      } else if (data.status === "secondary_fallback_ok") {
        setMessage(`Secondary public insider fallback used: ${data.records_fetched ?? 0} transaction record(s) parsed, ${data.records_added ?? 0} new ledger record(s) added. ${data.provider_note ?? "These records are context-only and require primary-source corroboration."}`);
      } else if (data.status === "fallback_ok") {
        setMessage(`Official Micron IR fallback used: ${data.records_fetched ?? 0} public filing record(s) parsed, ${data.records_added ?? 0} new ledger record(s) added. ${data.provider_note ?? "Form 4 direction is not inferred without transaction detail."}`);
      } else {
        setMessage(`SEC capture complete: ${data.records_fetched ?? 0} public records parsed, ${data.records_added ?? 0} new ledger records added.`);
      }
      await load(caseId);
    } catch (error) {
      setMessage(error instanceof Error ? `Insider capture error: ${error.message}` : "Insider capture failed");
    } finally {
      setBusy(false);
    }
  };

  if (!caseId) return null;

  const panel = {
    background: "rgba(7, 11, 17, 0.96)",
    border: "1px solid #28313d",
    borderRadius: "14px",
    padding: "22px",
  } as const;
  const small = {
    color: "#758294",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };
  const summary = status?.summary;

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={{ ...panel, borderColor: "#4a5876" }}>
        <div style={small}>INSIDER & OWNERSHIP INTELLIGENCE · PUBLIC FILINGS / CONTEXT</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "18px", alignItems: "start", flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: "7px 0 5px" }}>Separate genuine insider activity from compensation mechanics</h2>
            <div style={{ color: "#8c99a8", fontSize: "13px", maxWidth: "900px", lineHeight: 1.5 }}>
              SEC EDGAR is primary; Micron IR is the official fallback. If both are unavailable locally, a secondary public source may populate context-only transactions that require primary-source corroboration. No insider source can independently authorize a trade.
            </div>
          </div>
          <button onClick={() => void autoCapture()} disabled={busy} style={{ border: "1px solid #5d6e96", background: "#141d31", color: "#dce5ff", borderRadius: "8px", padding: "12px 16px", fontWeight: 900 }}>
            {busy ? "CHECKING PUBLIC SOURCES..." : "AUTO CAPTURE PUBLIC INSIDER FILINGS"}
          </button>
        </div>

        <div style={{ marginTop: "13px", color: "#9ba8b6", fontSize: "12px", lineHeight: 1.5 }}>{message}</div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(120px, 1fr))", gap: "8px", marginTop: "16px" }}>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>Open-market buys</div><div style={{ marginTop: "7px", fontSize: "20px", fontWeight: 900 }}>{summary?.open_market_buys ?? 0}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>Open-market sales</div><div style={{ marginTop: "7px", fontSize: "20px", fontWeight: 900 }}>{summary?.open_market_sales ?? 0}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>10b5-1 sales</div><div style={{ marginTop: "7px", fontSize: "20px", fontWeight: 900 }}>{summary?.planned_10b5_1_sales ?? 0}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>13D / 13G</div><div style={{ marginTop: "7px", fontSize: "20px", fontWeight: 900 }}>{summary?.beneficial_ownership_filings ?? 0}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>Buy value</div><div style={{ marginTop: "7px", fontSize: "15px", fontWeight: 900 }}>{money(summary?.buy_dollar_value)}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>30d cluster</div><div style={{ marginTop: "7px", fontSize: "12px", fontWeight: 900 }}>{(summary?.cluster_signal_30d ?? "NONE").replaceAll("_", " ")}</div></div>
        </div>

        {status && status.records.length > 0 && (
          <div style={{ ...panel, marginTop: "15px", padding: "16px", background: "#080c11" }}>
            <div style={small}>RECENT PUBLIC INSIDER / OWNERSHIP RECORDS</div>
            {status.records.slice(0, 14).map((record) => (
              <div key={record.insider_activity_id} style={{ borderTop: "1px solid #1e2731", padding: "10px 0", marginTop: "8px", fontSize: "12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                  <strong>
                    {record.reporting_owner ? `${record.reporting_owner} · ${record.reporting_owner_role ?? "Reporting owner"}` : record.record_kind.replaceAll("_", " ")}
                  </strong>
                  <span style={{ color: record.transaction_nature === "OPEN_MARKET_PURCHASE" ? "#69cf94" : record.transaction_nature === "OPEN_MARKET_SALE" ? "#e1b26d" : "#8fa0b3", fontWeight: 800 }}>
                    {record.transaction_nature?.replaceAll("_", " ") ?? record.form}
                  </span>
                </div>
                <div style={{ marginTop: "5px", color: "#98a5b3" }}>
                  {record.shares !== null && record.shares !== undefined ? `${record.shares.toLocaleString()} shares` : ""}
                  {record.price_per_share !== null && record.price_per_share !== undefined ? ` @ $${record.price_per_share.toLocaleString()}` : ""}
                  {record.dollar_value !== null && record.dollar_value !== undefined ? ` · ${money(record.dollar_value)}` : ""}
                  {record.plan_10b5_1 === true ? " · 10b5-1" : ""}
                </div>
                <div style={{ marginTop: "4px", color: "#7f8c9c" }}>{record.form} · filed {record.filing_date ?? "—"} · transaction {record.transaction_date ?? "—"}</div>
                {record.secondary_source && <div style={{ marginTop: "4px", color: "#d7b76a" }}>SECONDARY PUBLIC SOURCE · CONTEXT ONLY · PRIMARY CORROBORATION REQUIRED</div>}
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: "12px", color: "#758294", fontSize: "11px", lineHeight: 1.5 }}>
          Insider activity is a contextual signal, not a standalone BUY/SELL rule. Absence of a successful source response is never interpreted as absence of insider activity.
        </div>
      </div>
    </section>
  );
}

export default InsiderOwnershipPanel;

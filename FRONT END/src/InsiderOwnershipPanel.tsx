import { useEffect, useState } from "react";

const API = "http://localhost:8002";
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
  recent_records_90d?: InsiderRecord[];
  historical_records?: InsiderRecord[];
  summary: {
    record_count: number;
    raw_record_count?: number;
    excluded_non_corporate_records?: number;
    open_market_buys: number;
    open_market_sales: number;
    buy_dollar_value: number;
    sale_dollar_value: number;
    recent_open_market_buys_90d?: number | null;
    recent_open_market_sales_90d?: number | null;
    recent_buy_dollar_value_90d?: number | null;
    recent_sale_dollar_value_90d?: number | null;
    planned_10b5_1_sales: number | null;
    beneficial_ownership_filings: number | null;
    cluster_signal_30d: string;
    cluster_is_context_only: boolean;
  };
  coverage?: {
    active_source_tier: string;
    primary_sec_records: number;
    official_company_records: number;
    secondary_public_records: number;
    open_market_direction_covered: boolean;
    plan_10b5_1_covered: boolean;
    beneficial_ownership_covered: boolean;
    secondary_requires_primary_corroboration: boolean;
    recent_window_days?: number;
    latest_record_at?: string | null;
    latest_record_age_days?: number | null;
    recent_activity_covered?: boolean;
    historical_only?: boolean;
  };
};

function money(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "UNKNOWN";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function countOrUnknown(value: number | null | undefined): string {
  return value === null || value === undefined ? "UNKNOWN" : value.toLocaleString();
}

function tierLabel(value?: string): string {
  return (value ?? "NO_SUCCESSFUL_SOURCE").replaceAll("_", " ");
}

function dateLabel(value?: string | null): string {
  if (!value) return "UNKNOWN";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString(undefined, { timeZone: "UTC" });
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
        setMessage(`Secondary public insider fallback used: ${data.records_fetched ?? 0} corporate-insider transaction record(s) parsed, ${data.records_added ?? 0} new ledger record(s) added. ${data.provider_note ?? "These records are context-only and require primary-source corroboration."}`);
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
  const coverage = status?.coverage;
  const currentCovered = coverage?.recent_activity_covered === true;
  const recentRecords = status?.recent_records_90d ?? [];
  const historicalRecords = status?.historical_records ?? [];

  const renderRecord = (record: InsiderRecord) => (
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
  );

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={{ ...panel, borderColor: "#4a5876" }}>
        <div style={small}>INSIDER & OWNERSHIP INTELLIGENCE · CORPORATE INSIDERS ONLY</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "18px", alignItems: "start", flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: "7px 0 5px" }}>Separate current insider behavior from stale historical context</h2>
            <div style={{ color: "#8c99a8", fontSize: "13px", maxWidth: "920px", lineHeight: 1.5 }}>
              SEC EDGAR is primary; Micron IR is the official fallback. Secondary public rows are corporate-insider context only. Congressional/political trades are excluded, and records older than the current 90-day window cannot be used as present-tense insider evidence.
            </div>
          </div>
          <button onClick={() => void autoCapture()} disabled={busy} style={{ border: "1px solid #5d6e96", background: "#141d31", color: "#dce5ff", borderRadius: "8px", padding: "12px 16px", fontWeight: 900 }}>
            {busy ? "CHECKING PUBLIC SOURCES..." : "AUTO CAPTURE PUBLIC INSIDER FILINGS"}
          </button>
        </div>

        <div style={{ marginTop: "13px", color: "#9ba8b6", fontSize: "12px", lineHeight: 1.5 }}>{message}</div>

        {status && (
          <div style={{ marginTop: "10px", color: "#7f8c9c", fontSize: "11px", lineHeight: 1.6 }}>
            SOURCE TIER: <strong style={{ color: "#c6d0dc" }}>{tierLabel(coverage?.active_source_tier)}</strong>
            {summary?.excluded_non_corporate_records ? ` · ${summary.excluded_non_corporate_records} non-corporate/political row(s) excluded` : ""}
            {coverage?.secondary_requires_primary_corroboration ? " · secondary records require primary corroboration" : ""}
            <br />
            LATEST GOVERNED RECORD: <strong style={{ color: currentCovered ? "#a9d7b8" : "#d7b76a" }}>{dateLabel(coverage?.latest_record_at)}</strong>
            {coverage?.latest_record_age_days !== null && coverage?.latest_record_age_days !== undefined ? ` · ${coverage.latest_record_age_days} days old` : ""}
            {currentCovered ? ` · current ${coverage?.recent_window_days ?? 90}-day coverage available` : " · STALE SOURCE — current activity is UNKNOWN"}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(120px, 1fr))", gap: "8px", marginTop: "16px" }}>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>90d buys</div><div style={{ marginTop: "7px", fontSize: "20px", fontWeight: 900 }}>{countOrUnknown(summary?.recent_open_market_buys_90d)}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>90d sales</div><div style={{ marginTop: "7px", fontSize: "20px", fontWeight: 900 }}>{countOrUnknown(summary?.recent_open_market_sales_90d)}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>10b5-1 sales</div><div style={{ marginTop: "7px", fontSize: "15px", fontWeight: 900 }}>{countOrUnknown(summary?.planned_10b5_1_sales)}</div><div style={{ marginTop: "3px", color: "#6f7d8d", fontSize: "10px" }}>{coverage?.plan_10b5_1_covered ? "covered" : "not covered by active source"}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>13D / 13G</div><div style={{ marginTop: "7px", fontSize: "15px", fontWeight: 900 }}>{countOrUnknown(summary?.beneficial_ownership_filings)}</div><div style={{ marginTop: "3px", color: "#6f7d8d", fontSize: "10px" }}>{coverage?.beneficial_ownership_covered ? "covered" : "not covered by active source"}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>90d buy value</div><div style={{ marginTop: "7px", fontSize: "15px", fontWeight: 900 }}>{money(summary?.recent_buy_dollar_value_90d)}</div></div>
          <div style={{ ...panel, padding: "12px", background: "#080d11" }}><div style={small}>30d cluster</div><div style={{ marginTop: "7px", fontSize: "12px", fontWeight: 900 }}>{(summary?.cluster_signal_30d ?? "UNKNOWN").replaceAll("_", " ")}</div></div>
        </div>

        {!currentCovered && status && (
          <div style={{ marginTop: "16px", border: "1px solid #6a5530", background: "#171209", borderRadius: "10px", padding: "12px 14px", color: "#d7b76a", fontSize: "12px", lineHeight: 1.5 }}>
            CURRENT INSIDER SIGNAL WITHHELD: the newest governed record is outside the {coverage?.recent_window_days ?? 90}-day freshness window. Historical buys/sales below are retained for context only and cannot influence present-tense qualification.
          </div>
        )}

        {currentCovered && recentRecords.length > 0 && (
          <div style={{ ...panel, marginTop: "15px", padding: "16px", background: "#080c11" }}>
            <div style={small}>CURRENT CORPORATE INSIDER RECORDS · LAST 90 DAYS</div>
            {recentRecords.slice(0, 14).map(renderRecord)}
          </div>
        )}

        {historicalRecords.length > 0 && (
          <div style={{ ...panel, marginTop: "15px", padding: "16px", background: "#080c11" }}>
            <div style={small}>{currentCovered ? "OLDER CORPORATE INSIDER HISTORY" : "HISTORICAL CORPORATE INSIDER RECORDS · STALE CONTEXT"}</div>
            {historicalRecords.slice(0, 14).map(renderRecord)}
          </div>
        )}

        <div style={{ marginTop: "12px", color: "#758294", fontSize: "11px", lineHeight: 1.5 }}>
          Insider activity is a contextual signal, not a standalone BUY/SELL rule. Unknown or stale coverage is shown explicitly rather than converted to zero. Raw excluded rows remain in the audit ledger for provenance but cannot enter governed research.
        </div>
      </div>
    </section>
  );
}

export default InsiderOwnershipPanel;

import { useCallback, useEffect, useState } from "react";

const API = "http://127.0.0.1:8002";

type OpportunityCandidate = {
  opportunity_candidate_id: string;
  ticker: string;
  label?: string;
  score?: number;
  priority?: string;
  eligible_for_promotion?: boolean;
  catalyst_categories?: string[];
  current_price?: number | null;
  quote_provider?: string | null;
  news_count?: number;
  source_count?: number;
  recent_24h_count?: number;
  promoted_case_id?: string | null;
  created_at?: string;
};

type OpportunityStatus = {
  latest_scan?: {
    opportunity_scan_id?: string;
    scanned_count?: number;
    queued_count?: number;
    created_at?: string;
  } | null;
  queue: OpportunityCandidate[];
  paper_mode: boolean;
  auto_trade_authority: boolean;
  trade_execution_permission: boolean;
  live_execution: boolean;
};

type AutomationStatus = {
  config: {
    enabled: boolean;
    auto_dispatch_enabled: boolean;
    interval_minutes: number;
    news_limit: number;
    max_candidates: number;
    dispatch_limit: number;
    last_scan_at?: string | null;
    last_scan_status?: string | null;
    last_error?: string | null;
    auto_trade_authority: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };
  scheduler_running: boolean;
  paper_mode: boolean;
  auto_trade_authority: boolean;
  trade_execution_permission: boolean;
  live_execution: boolean;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function money(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function scoreTone(score?: number): string {
  if ((score ?? 0) >= 65) return "#59c68c";
  if ((score ?? 0) >= 45) return "#e6bd5c";
  return "#7d8998";
}

export default function OpportunityFloor() {
  const [status, setStatus] = useState<OpportunityStatus | null>(null);
  const [automation, setAutomation] = useState<AutomationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [statusData, automationData] = await Promise.all([
        getJson<OpportunityStatus>("/opportunities/status"),
        getJson<AutomationStatus>("/opportunities/automation"),
      ]);
      setStatus(statusData);
      setAutomation(automationData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Opportunity floor unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const panel = {
    background: "rgba(7, 11, 17, 0.94)",
    border: "1px solid #3f4f63",
    borderRadius: "14px",
    padding: "22px",
    marginBottom: "22px",
  } as const;

  const label = {
    color: "#758294",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  const config = automation?.config;
  const queue = status?.queue ?? [];

  return (
    <section style={panel}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "18px",
          alignItems: "start",
          flexWrap: "wrap",
        }}
      >
        <div>
          <div style={label}>OPPORTUNITY FLOOR</div>
          <h2 style={{ margin: "7px 0 5px", fontSize: "25px" }}>
            Autonomous Research Hunt
          </h2>
          <div style={{ color: "#8c99a8", fontSize: "12px" }}>
            Public-data scanner → ranked candidates → governed research queue
          </div>
        </div>

        <div
          style={{
            border: "1px solid #315a45",
            background: "#09150f",
            borderRadius: "9px",
            padding: "11px 14px",
            minWidth: "245px",
          }}
        >
          <div style={label}>AUTOMATION</div>
          <div
            style={{
              marginTop: "6px",
              color: config?.enabled && automation?.scheduler_running ? "#59c68c" : "#e6bd5c",
              fontWeight: 900,
              letterSpacing: "1px",
            }}
          >
            {config?.enabled ? "SCAN ARMED" : "SCAN PAUSED"}
            {automation?.scheduler_running ? " · SCHEDULER LIVE" : ""}
          </div>
          <div style={{ marginTop: "5px", color: "#8fa095", fontSize: "11px" }}>
            Every {config?.interval_minutes ?? 240}m · Agent auto-dispatch {config?.auto_dispatch_enabled ? "ON" : "OFF"}
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            marginTop: "15px",
            border: "1px solid #6d3340",
            background: "#1a0b0f",
            color: "#ff8b9b",
            borderRadius: "8px",
            padding: "11px 13px",
            fontSize: "12px",
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, minmax(150px, 1fr))",
          gap: "10px",
          marginTop: "17px",
        }}
      >
        <Metric label="Last Scan" value={config?.last_scan_at ? new Date(config.last_scan_at).toLocaleString() : "Waiting for first scan"} />
        <Metric label="Scan Status" value={(config?.last_scan_status || "PENDING").replaceAll("_", " ")} />
        <Metric label="Scanned" value={String(status?.latest_scan?.scanned_count ?? 0)} />
        <Metric label="Research Queue" value={String(queue.length)} />
      </div>

      <div style={{ overflowX: "auto", marginTop: "17px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "900px" }}>
          <thead>
            <tr style={{ color: "#748193", fontSize: "10px", letterSpacing: "1.4px", textAlign: "left" }}>
              <th style={{ padding: "9px" }}>RANK</th>
              <th style={{ padding: "9px" }}>TICKER</th>
              <th style={{ padding: "9px" }}>SCORE</th>
              <th style={{ padding: "9px" }}>PRICE</th>
              <th style={{ padding: "9px" }}>CATALYSTS</th>
              <th style={{ padding: "9px" }}>NEWS</th>
              <th style={{ padding: "9px" }}>STATE</th>
            </tr>
          </thead>
          <tbody>
            {queue.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: "18px 9px", color: "#6f7c8d" }}>
                  No candidate has crossed the research-promotion score yet. The scanner remains fail-closed.
                </td>
              </tr>
            )}
            {queue.slice(0, 8).map((candidate, index) => (
              <tr key={candidate.opportunity_candidate_id} style={{ borderTop: "1px solid #202a35" }}>
                <td style={{ padding: "12px 9px", color: "#748193" }}>#{index + 1}</td>
                <td style={{ padding: "12px 9px" }}>
                  <div style={{ fontWeight: 900 }}>{candidate.ticker}</div>
                  <div style={{ marginTop: "3px", color: "#7f8b99", fontSize: "11px" }}>{candidate.label || ""}</div>
                </td>
                <td style={{ padding: "12px 9px", color: scoreTone(candidate.score), fontWeight: 900 }}>
                  {(candidate.score ?? 0).toFixed(1)} · {candidate.priority || "LOW"}
                </td>
                <td style={{ padding: "12px 9px" }}>
                  {money(candidate.current_price)}
                  <div style={{ color: "#6f7c8d", fontSize: "10px", marginTop: "3px" }}>{candidate.quote_provider || "—"}</div>
                </td>
                <td style={{ padding: "12px 9px", color: "#a9b5c2", fontSize: "11px" }}>
                  {(candidate.catalyst_categories || []).length
                    ? (candidate.catalyst_categories || []).join(" · ")
                    : "None classified"}
                </td>
                <td style={{ padding: "12px 9px" }}>
                  {candidate.news_count ?? 0} items · {candidate.source_count ?? 0} sources
                </td>
                <td style={{ padding: "12px 9px" }}>
                  <span style={{ color: candidate.promoted_case_id ? "#59c68c" : "#e6bd5c", fontWeight: 800 }}>
                    {candidate.promoted_case_id ? "CASE CREATED" : "RESEARCH QUEUED"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div
        style={{
          marginTop: "15px",
          borderTop: "1px solid #202a35",
          paddingTop: "12px",
          color: "#687687",
          fontSize: "11px",
          lineHeight: 1.5,
        }}
      >
        Research-only surface. Candidate scores are prioritization scores, not buy/sell signals. Automatic agent dispatch is OFF by default, and this floor has no sizing, authorization, paper-order, broker, or live-execution control.
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid #293440", borderRadius: "9px", padding: "12px", background: "#080c11" }}>
      <div style={{ color: "#758294", fontSize: "9px", letterSpacing: "1.5px", textTransform: "uppercase" }}>{label}</div>
      <div style={{ marginTop: "6px", fontWeight: 800, fontSize: "13px" }}>{value}</div>
    </div>
  );
}

import { useEffect, useState } from "react";

const API = "http://localhost:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type InstitutionalRecord = {
  institutional_signal_id: string;
  lane: string;
  lane_label: string;
  ticker: string;
  summary?: string;
  directional_context?: string;
  details?: Record<string, unknown>;
  data_as_of?: string | null;
  age_days?: number | null;
  freshness_days?: number;
  fresh?: boolean;
  source_name?: string;
  source_tier?: string;
  admission_status?: string;
  primary_corroboration_required?: boolean;
};

type LaneStatus = {
  label: string;
  status: "CURRENT" | "STALE" | "LAGGED" | "NO_DATA" | string;
  record?: InstitutionalRecord | null;
};

type InstitutionalStatus = {
  case_id: string;
  lanes: Record<string, LaneStatus>;
  latest_snapshot?: {
    captured_lanes?: string[];
    failed_lanes?: Record<string, string>;
    created_at?: string;
  } | null;
};

type CaptureResult = {
  captured_lanes?: string[];
  failed_lanes?: Record<string, string>;
  records_added?: number;
};

function fmtNumber(value: unknown, digits = 2): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtMoney(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 2 }).format(value);
}

function pct(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2).replace(/\.00$/, "")}%`;
}

function dateLabel(value?: string | null): string {
  if (!value) return "UNKNOWN";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "numeric", day: "numeric", year: "numeric" }).format(parsed);
}

function tone(status?: string): string {
  if (status === "CURRENT") return "#67cf95";
  if (status === "STALE" || status === "LAGGED") return "#d8b466";
  return "#7f8b99";
}

function directionLabel(value?: string): string {
  return (value ?? "UNKNOWN").replaceAll("_", " ");
}

function InstitutionalIntelligencePanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [status, setStatus] = useState<InstitutionalStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Institutional expectations are corroborating context only; no lane can independently authorize a trade or resolve a qualification gap.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => current === next ? current : next);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const load = async (selectedCaseId: string) => {
    const response = await fetch(`${API}/institutional/${selectedCaseId}`);
    if (!response.ok) throw new Error(`Institutional status failed: ${response.status}`);
    setStatus(await response.json() as InstitutionalStatus);
  };

  useEffect(() => {
    if (!caseId) {
      setStatus(null);
      return;
    }
    void load(caseId).catch((error) => setMessage(error instanceof Error ? error.message : "Institutional layer unavailable"));
  }, [caseId]);

  const capture = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Capturing ownership, analyst context, short interest, options positioning, and catalysts with freshness and source-semantic checks...");
    try {
      const response = await fetch(`${API}/institutional/${caseId}/auto-capture`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json() as CaptureResult;
      const captured = result.captured_lanes?.length ?? 0;
      const failed = Object.keys(result.failed_lanes ?? {}).length;
      setMessage(`Institutional capture complete: ${captured} lane(s) captured, ${failed} unavailable. All captured records require primary corroboration and remain non-executable context.`);
      await load(caseId);
    } catch (error) {
      setMessage(error instanceof Error ? `Institutional capture error: ${error.message}` : "Institutional capture failed");
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

  const lanes = status?.lanes ?? {};
  const orderedKeys = ["institutional_ownership", "analyst_revisions", "short_interest", "options_positioning", "catalyst_calendar"];

  const detail = (key: string, record?: InstitutionalRecord | null) => {
    const d = record?.details ?? {};
    const fallbackScope = typeof d.fallback_scope === "string" ? d.fallback_scope.toLowerCase() : "";
    if (!record) return <div style={{ color: "#687586", marginTop: "10px" }}>No governed capture yet.</div>;

    if (key === "institutional_ownership") {
      if (d.reporting_date_unknown === true || "buyers_12m" in d || "sellers_12m" in d) {
        return <div style={{ marginTop: "10px", color: "#a5b0bc", lineHeight: 1.5 }}>
          Buyers 12m: <strong>{fmtNumber(d.buyers_12m, 0)}</strong> · sellers: <strong>{fmtNumber(d.sellers_12m, 0)}</strong><br />
          Inflows/outflows: <strong>{fmtMoney(d.inflows_12m)} / {fmtMoney(d.outflows_12m)}</strong><br />
          13F report date: <strong style={{ color: "#d8b466" }}>UNVERIFIED · LAGGED CONTEXT</strong>
        </div>;
      }
      return <div style={{ marginTop: "10px", color: "#a5b0bc", lineHeight: 1.5 }}>Increasing holders: <strong>{fmtNumber(d.increasing_holders, 0)}</strong> · decreasing: <strong>{fmtNumber(d.decreasing_holders, 0)}</strong><br />Reporting lag: <strong>{record.age_days ?? "UNKNOWN"} days</strong></div>;
    }

    if (key === "analyst_revisions") {
      if (d.analyst_feed_kind === "RATINGS_AND_TARGET_ACTIONS" || fallbackScope.includes("ratings and target changes")) {
        return <div style={{ marginTop: "10px", color: "#a5b0bc", lineHeight: 1.5 }}>
          Rating/target actions +: <strong>{fmtNumber(d.positive_recent_actions, 0)}</strong> · −: <strong>{fmtNumber(d.negative_recent_actions, 0)}</strong><br />
          Consensus: <strong>{typeof d.consensus_rating === "string" ? d.consensus_rating : "—"}</strong> · target: <strong>{typeof d.consensus_price_target === "number" ? fmtMoney(d.consensus_price_target) : "—"}</strong><br />
          EPS revision series: <strong style={{ color: "#d8b466" }}>NOT PROVIDED BY FALLBACK</strong>
        </div>;
      }
      return <div style={{ marginTop: "10px", color: "#a5b0bc", lineHeight: 1.5 }}>Revised up: <strong>{fmtNumber(d.revised_up, 0)}</strong> · revised down: <strong>{fmtNumber(d.revised_down, 0)}</strong><br />Direction: <strong>{directionLabel(record.directional_context)}</strong></div>;
    }

    if (key === "short_interest") {
      return <div style={{ marginTop: "10px", color: "#a5b0bc", lineHeight: 1.5 }}>Shares short: <strong>{fmtNumber(d.shares_short, 0)}</strong> · ratio: <strong>{fmtNumber(d.short_ratio)}</strong><br />Short % float: <strong>{pct(d.short_percent_float)}</strong> · change: <strong>{pct(d.change_vs_prior_month)}</strong></div>;
    }

    if (key === "options_positioning") {
      return <div style={{ marginTop: "10px", color: "#a5b0bc", lineHeight: 1.5 }}>Put/call OI: <strong>{fmtNumber(d.put_call_open_interest_ratio)}</strong> · volume: <strong>{fmtNumber(d.put_call_volume_ratio)}</strong><br />Nearest expiry: <strong>{dateLabel(typeof d.expiration === "string" ? d.expiration : null)}</strong><br />Median IV calls/puts: <strong>{pct(d.median_call_iv)} / {pct(d.median_put_iv)}</strong></div>;
    }

    if (key === "catalyst_calendar") {
      return <div style={{ marginTop: "10px", color: "#a5b0bc", lineHeight: 1.5 }}>Next earnings: <strong>{dateLabel(typeof d.next_earnings === "string" ? d.next_earnings : null)}</strong>{d.estimated_not_confirmed === true ? <strong style={{ color: "#d8b466" }}> · ESTIMATED</strong> : null}<br />EPS consensus: <strong>{fmtNumber(d.earnings_average)}</strong> · revenue consensus: <strong>{fmtNumber(d.revenue_average, 0)}</strong></div>;
    }
    return null;
  };

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={{ ...panel, borderColor: "#59634b" }}>
        <div style={small}>INSTITUTIONAL EXPECTATIONS · OWNERSHIP / REVISIONS / CROWDING / CATALYSTS</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "18px", alignItems: "start", flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: "7px 0 5px" }}>See what sophisticated market participants already expect</h2>
            <div style={{ color: "#8c99a8", fontSize: "13px", maxWidth: "930px", lineHeight: 1.5 }}>
              13F ownership is lagged; analyst estimates can herd; short interest is periodic; options may be hedges; catalyst dates can change. These lanes inform the Committee but cannot independently resolve a research requirement, clear Risk, or authorize a trade.
            </div>
          </div>
          <button onClick={() => void capture()} disabled={busy} style={{ border: "1px solid #63714d", background: "#19200f", color: "#dbe7c3", borderRadius: "8px", padding: "12px 16px", fontWeight: 900 }}>
            {busy ? "CAPTURING INSTITUTIONAL LAYER..." : "AUTO CAPTURE INSTITUTIONAL LAYER"}
          </button>
        </div>

        <div style={{ marginTop: "13px", color: "#9ba8b6", fontSize: "12px", lineHeight: 1.5 }}>{message}</div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(160px, 1fr))", gap: "10px", marginTop: "18px" }}>
          {orderedKeys.map((key) => {
            const lane = lanes[key];
            const record = lane?.record;
            const d = record?.details ?? {};
            const fallbackAnalyst = key === "analyst_revisions" && (d.analyst_feed_kind === "RATINGS_AND_TARGET_ACTIONS" || (typeof d.fallback_scope === "string" && d.fallback_scope.toLowerCase().includes("ratings and target changes")));
            const label = fallbackAnalyst ? "Analyst Ratings / Target Actions" : (lane?.label ?? key.replaceAll("_", " "));
            return (
              <div key={key} style={{ ...panel, padding: "15px", background: "#080d11" }}>
                <div style={small}>{label}</div>
                <div style={{ marginTop: "8px", fontSize: "12px", color: tone(lane?.status), fontWeight: 900 }}>{lane?.status ?? "NO DATA"}</div>
                <div style={{ marginTop: "8px", fontSize: "13px", fontWeight: 800 }}>{directionLabel(record?.directional_context)}</div>
                <div style={{ marginTop: "6px", color: "#7e8a98", fontSize: "11px" }}>As of {dateLabel(record?.data_as_of)}{record?.age_days !== null && record?.age_days !== undefined ? ` · ${record.age_days}d old` : ""}</div>
                {detail(key, record)}
              </div>
            );
          })}
        </div>

        {status?.latest_snapshot && (
          <div style={{ ...panel, padding: "14px", marginTop: "14px", background: "#080c11" }}>
            <div style={small}>LATEST CAPTURE AUDIT</div>
            <div style={{ marginTop: "8px", color: "#a2adba", fontSize: "12px", lineHeight: 1.5 }}>
              Captured: {(status.latest_snapshot.captured_lanes ?? []).map((item) => item.replaceAll("_", " ")).join(" · ") || "none"}
              {Object.keys(status.latest_snapshot.failed_lanes ?? {}).length > 0 ? <><br />Unavailable: {Object.keys(status.latest_snapshot.failed_lanes ?? {}).map((item) => item.replaceAll("_", " ")).join(" · ")}</> : null}
            </div>
          </div>
        )}

        <div style={{ marginTop: "12px", color: "#758294", fontSize: "11px", lineHeight: 1.5 }}>
          SOURCE TIER: SECONDARY PUBLIC MARKET DATA · PRIMARY CORROBORATION REQUIRED · GAP RESOLUTION ELIGIBLE: NO · PAPER / SHADOW MODE ONLY
        </div>
      </div>
    </section>
  );
}

export default InstitutionalIntelligencePanel;

import { useEffect, useState } from "react";

const API = "http://localhost:8000";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type FactRow = {
  key: string;
  label: string;
  covered: boolean;
  supporting_items: number;
};

type Resolution = {
  resolved?: boolean;
  blockers?: string[];
  independent_sources?: number;
  average_quality?: number;
  fact_coverage?: {
    coverage_pct?: number;
  };
};

type LaneStatus = {
  lane: string;
  label: string;
  requirement?: string | null;
  status: string;
  coverage_pct: number;
  covered_facts: number;
  total_facts: number;
  facts: FactRow[];
  current_high_quality_records: number;
  source_count: number;
  note?: string | null;
  latest_resolution?: Resolution | null;
};

type PrimaryStatus = {
  case_id: string;
  lanes: Record<string, LaneStatus>;
};

type CaptureResult = {
  records_seen_or_added?: number;
  failures?: string[];
  status?: PrimaryStatus;
};

function PrimaryEvidencePanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [status, setStatus] = useState<PrimaryStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Primary evidence is allowed to resolve gaps only after the fact contract, quality firewall, and source-diversity rules all pass.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => current === next ? current : next);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const load = async (selectedCaseId: string) => {
    const response = await fetch(`${API}/primary-evidence/${selectedCaseId}`);
    if (!response.ok) throw new Error(`Primary evidence status failed: ${response.status}`);
    setStatus(await response.json() as PrimaryStatus);
  };

  useEffect(() => {
    if (!caseId) {
      setStatus(null);
      return;
    }
    void load(caseId).catch((error) => setMessage(error instanceof Error ? error.message : "Primary evidence layer unavailable"));
  }, [caseId]);

  const capture = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Collecting filing, company-IR, peer supply, hyperscaler, policy, and hard-market evidence...");
    try {
      const response = await fetch(`${API}/primary-evidence/${caseId}/auto-capture`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json() as CaptureResult;
      const failures = result.failures?.length ?? 0;
      setMessage(`Primary capture complete: ${result.records_seen_or_added ?? 0} verified record(s) seen or added; ${failures} provider issue(s). Independent memory-pricing data remains open unless a qualified source is available.`);
      if (result.status) setStatus(result.status);
      else await load(caseId);
    } catch (error) {
      setMessage(error instanceof Error ? `Primary capture error: ${error.message}` : "Primary capture failed");
    } finally {
      setBusy(false);
    }
  };

  if (!caseId) return null;

  const ordered = ["memory_pricing", "supply_inventory", "hyperscaler_demand", "micron_financials", "valuation_market", "policy"];
  const panel = {
    background: "rgba(7, 11, 17, 0.97)",
    border: "1px solid #31424d",
    borderRadius: "14px",
    padding: "22px",
  } as const;
  const small = {
    color: "#778698",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={{ ...panel, borderColor: "#3c6370" }}>
        <div style={small}>PRIMARY EVIDENCE ACQUISITION · REQUIREMENT CONTRACTS</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "18px", alignItems: "start", flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: "7px 0 5px" }}>Make the Factory prove each missing fact</h2>
            <div style={{ color: "#8f9dab", fontSize: "13px", maxWidth: "930px", lineHeight: 1.5 }}>
              Each Committee requirement is decomposed into facts. A gap cannot turn green merely because two articles mention the topic; fact coverage, quality, and independent-source rules must all pass.
            </div>
          </div>
          <button onClick={() => void capture()} disabled={busy} style={{ border: "1px solid #397789", background: "#0b2630", color: "#d9f4f7", borderRadius: "8px", padding: "12px 16px", fontWeight: 900 }}>
            {busy ? "CAPTURING PRIMARY EVIDENCE..." : "AUTO CAPTURE PRIMARY EVIDENCE"}
          </button>
        </div>

        <div style={{ marginTop: "13px", color: "#9ba8b6", fontSize: "12px", lineHeight: 1.5 }}>{message}</div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(300px, 1fr))", gap: "12px", marginTop: "18px" }}>
          {ordered.map((key) => {
            const lane = status?.lanes?.[key];
            const pct = lane?.coverage_pct ?? 0;
            const resolution = lane?.latest_resolution;
            const resolved = Boolean(resolution?.resolved);
            return (
              <div key={key} style={{ ...panel, padding: "16px", background: "#080d12" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                  <div>
                    <div style={small}>{lane?.label ?? key.replaceAll("_", " ")}</div>
                    <div style={{ marginTop: "7px", fontWeight: 900, color: resolved ? "#67cf95" : pct ? "#d7b665" : "#8995a3" }}>
                      {resolved ? "GAP RESOLVED" : lane?.status ?? "OPEN"}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "24px", fontWeight: 900 }}>{pct}%</div>
                    <div style={{ color: "#778698", fontSize: "11px" }}>{lane?.covered_facts ?? 0}/{lane?.total_facts ?? 0} facts</div>
                  </div>
                </div>

                <div style={{ height: "7px", background: "#141d25", borderRadius: "999px", overflow: "hidden", marginTop: "12px" }}>
                  <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: "100%", background: resolved ? "#5aa77b" : "#7b6732" }} />
                </div>

                <div style={{ marginTop: "12px", display: "grid", gap: "6px" }}>
                  {(lane?.facts ?? []).map((fact) => (
                    <div key={fact.key} style={{ display: "flex", justifyContent: "space-between", gap: "8px", fontSize: "12px", color: fact.covered ? "#b8d9c6" : "#8c98a5" }}>
                      <span>{fact.covered ? "✓" : "○"} {fact.label}</span>
                      <span>{fact.supporting_items ? `${fact.supporting_items} item${fact.supporting_items === 1 ? "" : "s"}` : "OPEN"}</span>
                    </div>
                  ))}
                </div>

                <div style={{ marginTop: "12px", color: "#7f8c9b", fontSize: "11px", lineHeight: 1.5 }}>
                  High-quality current records: <strong>{lane?.current_high_quality_records ?? 0}</strong> · Sources: <strong>{lane?.source_count ?? 0}</strong>
                  {resolution ? <><br />Resolution blockers: <strong>{(resolution.blockers ?? []).join(" · ") || "none"}</strong></> : null}
                  {lane?.note ? <><br /><span style={{ color: "#c9a95e" }}>{lane.note}</span></> : null}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ marginTop: "13px", color: "#778698", fontSize: "11px", lineHeight: 1.5 }}>
          RESOLUTION RULE: FACT CONTRACT + QUALITY ≥ 65% + AT LEAST TWO HIGH-QUALITY ITEMS + AT LEAST TWO INDEPENDENT SOURCES + PRIMARY/OFFICIAL SUPPORT · PAPER / SHADOW MODE ONLY
        </div>
      </div>
    </section>
  );
}

export default PrimaryEvidencePanel;

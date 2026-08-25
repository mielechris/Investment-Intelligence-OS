import { useEffect, useState } from "react";

const API = "http://localhost:8000";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type GapPlan = {
  case_id: string;
  topic: string;
  requirements: string[];
  targeted_desks: string[];
  source_requests: Array<{ source: string; gap?: string }>;
};

type ResolutionRow = {
  requirement: string;
  resolved: boolean;
  supporting_items: number;
  high_quality_items: number;
  independent_sources: number;
  official_or_market_items: number;
  average_quality: number;
  blockers: string[];
  top_support: Array<{ source?: string; claim?: string; quality_score?: number; url?: string }>;
};

type RequirementLineageRow = {
  prior_requirement: string;
  lane?: string | null;
  prior_resolved: boolean;
  effective_resolved: boolean;
  status: string;
  replacement_requirement?: string | null;
};

type RequirementLineage = {
  prior_requirement_count: number;
  prior_resolved_count: number;
  accepted_resolved_count: number;
  reopened_count: number;
  current_open_count: number;
  current_requirements: string[];
  rows: RequirementLineageRow[];
};

type GapRun = {
  case_id: string;
  evidence_summary: { evidence_count?: number; average_quality_score?: number };
  quality_firewall?: { raw_count: number; admitted_count: number; rejected_count: number };
  resolution_matrix?: ResolutionRow[];
  requirement_lineage?: RequirementLineage;
  committee: {
    disposition?: string;
    confidence?: number;
    required_evidence?: string[];
    agents?: Record<string, { disposition?: string; confidence?: number; missing_evidence?: string[]; falsifier?: string }>;
  };
  risk: { decision?: string; triggered_rules?: string[] };
  execution: { execution?: string };
  qualification: {
    stage: string;
    qualified_buy_candidate: boolean;
    paper_buy_enabled: boolean;
    unmet_requirements: string[];
    thresholds: Record<string, number>;
    observed: Record<string, unknown>;
  };
};

function pct(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function labelize(value: string): string {
  return value.replaceAll("_", " ");
}

function EvidenceGapHunterPanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [plan, setPlan] = useState<GapPlan | null>(null);
  const [result, setResult] = useState<GapRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Researches exactly what the latest Committee says is still missing.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => (current === next ? current : next));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!caseId) {
      setPlan(null);
      return;
    }
    const load = async () => {
      try {
        const response = await fetch(`${API}/gap-hunter/${caseId}/plan`);
        if (!response.ok) throw new Error(`Gap plan failed: ${response.status}`);
        setPlan((await response.json()) as GapPlan);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Gap plan unavailable");
      }
    };
    void load();
  }, [caseId]);

  const run = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Hunting open evidence, applying the quality firewall, then rerunning targeted desks and the full Committee...");
    try {
      const response = await fetch(`${API}/gap-hunter/${caseId}/run`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as GapRun;
      setResult(data);
      const firewall = data.quality_firewall;
      const lineage = data.requirement_lineage;
      const resolved = data.resolution_matrix?.filter((item) => item.resolved).length ?? 0;
      const total = data.resolution_matrix?.length ?? 0;
      const lineageText = lineage
        ? `${lineage.accepted_resolved_count} prior gap(s) remain closed; ${lineage.reopened_count} reopened/tightened; ${lineage.current_open_count} current requirement(s).`
        : `${resolved}/${total} prior gaps resolved.`;
      setMessage(
        `Gap hunt complete: ${firewall ? `${firewall.admitted_count}/${firewall.raw_count} items admitted` : `${data.evidence_summary.evidence_count ?? 0} items`} at ${pct(data.evidence_summary.average_quality_score)} quality. ${lineageText} Stage: ${labelize(data.qualification.stage)}.`
      );
      const planResponse = await fetch(`${API}/gap-hunter/${caseId}/plan`);
      if (planResponse.ok) setPlan((await planResponse.json()) as GapPlan);
    } catch (error) {
      setMessage(error instanceof Error ? `Gap hunter error: ${error.message}` : "Gap hunter failed");
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

  const skeptic = result?.committee.agents?.skeptic;
  const lineage = result?.requirement_lineage;
  const priorClosed = lineage?.accepted_resolved_count ?? 0;
  const priorTotal = lineage?.prior_requirement_count ?? (result?.resolution_matrix?.length ?? 0);
  const currentOpen = lineage?.current_open_count ?? plan?.requirements.length ?? 0;

  const lineageFor = (requirement: string) => lineage?.rows.find((row) => row.prior_requirement === requirement);

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={{ ...panel, borderColor: "#6e5931" }}>
        <div style={small}>EVIDENCE GAP HUNTER · GOVERNED RESEARCH</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: "18px", flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: "7px 0 5px" }}>Hunt what the Committee is still missing</h2>
            <div style={{ color: "#8d99a8", fontSize: "13px", maxWidth: "800px" }}>{plan?.topic ?? "Loading current case..."}</div>
          </div>
          <button
            onClick={() => void run()}
            disabled={busy || !plan}
            style={{
              border: "1px solid #a78345",
              background: busy ? "#29251f" : "#332613",
              color: "#f2d39a",
              borderRadius: "8px",
              padding: "12px 16px",
              fontWeight: 900,
              cursor: busy ? "default" : "pointer",
            }}
          >
            {busy ? "HUNTING EVIDENCE..." : "HUNT GAPS + REUNDERWRITE"}
          </button>
        </div>

        <div style={{ marginTop: "14px", color: "#9aa6b5", fontSize: "12px" }}>{message}</div>

        {plan && (
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "14px", marginTop: "18px" }}>
            <div style={{ ...panel, padding: "16px", background: "#090d12" }}>
              <div style={small}>CURRENT OPEN EVIDENCE REQUIREMENTS</div>
              {plan.requirements.map((gap, index) => (
                <div key={`${gap}-${index}`} style={{ marginTop: "9px", borderTop: index ? "1px solid #1e2731" : "none", paddingTop: index ? "9px" : 0, fontSize: "13px", lineHeight: 1.45 }}>
                  {index + 1}. {gap}
                </div>
              ))}
            </div>
            <div style={{ ...panel, padding: "16px", background: "#090d12" }}>
              <div style={small}>TARGETED DESKS</div>
              <div style={{ marginTop: "10px", fontSize: "13px", lineHeight: 1.7 }}>{plan.targeted_desks.map(labelize).join(" · ")}</div>
              <div style={{ ...small, marginTop: "15px" }}>RESEARCH LANES</div>
              <div style={{ marginTop: "8px", fontSize: "12px", color: "#9da9b7", lineHeight: 1.6 }}>
                {plan.source_requests.map((item) => item.source).join(" · ")}
              </div>
            </div>
          </div>
        )}

        {result && (
          <>
            <div style={{ ...panel, padding: "16px", marginTop: "14px", borderColor: result.qualification.qualified_buy_candidate ? "#3e7a58" : "#394554", background: "#080c11" }}>
              <div style={small}>QUALIFICATION GATE</div>
              <div style={{ marginTop: "8px", fontSize: "22px", fontWeight: 900, color: result.qualification.qualified_buy_candidate ? "#69d99a" : "#d7b76a" }}>
                {labelize(result.qualification.stage)}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(100px, 1fr))", gap: "9px", marginTop: "13px", fontSize: "12px" }}>
                <div><span style={small}>Committee</span><div>{result.committee.disposition} · {pct(result.committee.confidence)}</div></div>
                <div><span style={small}>Evidence</span><div>{pct(result.evidence_summary.average_quality_score)} · {result.evidence_summary.evidence_count ?? 0}</div></div>
                <div><span style={small}>Firewall</span><div>{result.quality_firewall ? `${result.quality_firewall.admitted_count}/${result.quality_firewall.raw_count} admitted` : "—"}</div></div>
                <div><span style={small}>Prior Closed</span><div>{priorClosed}/{priorTotal}</div></div>
                <div><span style={small}>Current Open</span><div>{currentOpen}</div></div>
                <div><span style={small}>Risk</span><div>{result.risk.decision ?? "—"}</div></div>
                <div><span style={small}>Paper Buy</span><div>{result.qualification.paper_buy_enabled ? "ENABLED" : "LOCKED"}</div></div>
              </div>
              {lineage && lineage.reopened_count > 0 && (
                <div style={{ marginTop: "11px", color: "#d0a45d", fontSize: "11px", lineHeight: 1.5 }}>
                  Requirement lineage: {lineage.reopened_count} prior green requirement(s) were tightened/reopened by the new Committee and are not counted as currently closed.
                </div>
              )}
              {result.qualification.unmet_requirements.length > 0 && (
                <div style={{ marginTop: "13px", color: "#c9a768", fontSize: "12px", lineHeight: 1.6 }}>
                  Still blocking qualification: {result.qualification.unmet_requirements.map(labelize).join(" · ")}
                </div>
              )}
              {skeptic && (
                <div style={{ marginTop: "14px", borderTop: "1px solid #242d37", paddingTop: "12px", fontSize: "12px", lineHeight: 1.5 }}>
                  <span style={small}>SKEPTIC / RED TEAM</span>
                  <div style={{ marginTop: "5px" }}>{skeptic.disposition ?? "—"} · {pct(skeptic.confidence)}</div>
                  {skeptic.missing_evidence && skeptic.missing_evidence.length > 0 && <div style={{ marginTop: "5px", color: "#d1ad6b" }}>Still wants: {skeptic.missing_evidence.join(" · ")}</div>}
                  {skeptic.falsifier && <div style={{ marginTop: "5px", color: "#8e9baa" }}>Falsifier: {skeptic.falsifier}</div>}
                </div>
              )}
            </div>

            {result.resolution_matrix && result.resolution_matrix.length > 0 && (
              <div style={{ ...panel, marginTop: "14px", padding: "16px", background: "#090d12" }}>
                <div style={small}>PRIOR REQUIREMENT RESOLUTION MATRIX</div>
                <div style={{ marginTop: "7px", color: "#8996a6", fontSize: "12px" }}>
                  This matrix adjudicates the requirements that existed before this re-underwrite. The new Committee may tighten a previously green requirement; those rows are shown as REOPENED rather than current closures.
                </div>
                {result.resolution_matrix.map((row, index) => {
                  const rowLineage = lineageFor(row.requirement);
                  const reopened = rowLineage?.status === "SUPERSEDED_REOPENED";
                  const displayStatus = reopened ? "REOPENED" : row.resolved ? "PRIOR CLOSED" : "OPEN";
                  const displayColor = reopened ? "#d09c54" : row.resolved ? "#69d99a" : "#d7b76a";
                  return (
                    <details key={`${row.requirement}-${index}`} style={{ borderTop: index ? "1px solid #1f2832" : "none", padding: "12px 0" }}>
                      <summary style={{ cursor: "pointer", display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center", listStyle: "none" }}>
                        <span style={{ fontSize: "12px", lineHeight: 1.45, maxWidth: "75%" }}>{index + 1}. {row.requirement}</span>
                        <strong style={{ color: displayColor, fontSize: "11px" }}>{displayStatus}</strong>
                      </summary>
                      {reopened && rowLineage?.replacement_requirement && (
                        <div style={{ marginTop: "8px", color: "#d0a45d", fontSize: "11px", lineHeight: 1.45 }}>
                          Replacement requirement: {rowLineage.replacement_requirement}
                        </div>
                      )}
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(100px, 1fr))", gap: "8px", marginTop: "10px", fontSize: "11px" }}>
                        <div><span style={small}>Quality</span><div>{pct(row.average_quality)}</div></div>
                        <div><span style={small}>Support</span><div>{row.supporting_items}</div></div>
                        <div><span style={small}>High Quality</span><div>{row.high_quality_items}</div></div>
                        <div><span style={small}>Sources</span><div>{row.independent_sources}</div></div>
                        <div><span style={small}>Primary/Market</span><div>{row.official_or_market_items}</div></div>
                      </div>
                      {row.blockers.length > 0 && <div style={{ marginTop: "9px", color: "#c9a768", fontSize: "11px" }}>Blockers: {row.blockers.map(labelize).join(" · ")}</div>}
                      {row.top_support.length > 0 && (
                        <div style={{ marginTop: "9px" }}>
                          {row.top_support.map((item, supportIndex) => (
                            <div key={supportIndex} style={{ marginTop: "6px", color: "#8f9cab", fontSize: "11px", lineHeight: 1.4 }}>
                              {item.source || "Source"} · {pct(item.quality_score)} · {item.claim || "—"}
                            </div>
                          ))}
                        </div>
                      )}
                    </details>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

export default EvidenceGapHunterPanel;

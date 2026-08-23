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

type GapRun = {
  case_id: string;
  evidence_summary: { evidence_count?: number; average_quality_score?: number };
  committee: { disposition?: string; confidence?: number; required_evidence?: string[] };
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
    setMessage("Hunting open evidence, sending targeted desks first, then rerunning the full Committee...");
    try {
      const response = await fetch(`${API}/gap-hunter/${caseId}/run`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as GapRun;
      setResult(data);
      setMessage(
        `Gap hunt complete: ${data.evidence_summary.evidence_count ?? 0} items at ${pct(data.evidence_summary.average_quality_score)} quality. Stage: ${labelize(data.qualification.stage)}. Risk: ${data.risk.decision ?? "—"}.`
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
              <div style={small}>OPEN EVIDENCE REQUIREMENTS</div>
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
          <div style={{ ...panel, padding: "16px", marginTop: "14px", borderColor: result.qualification.qualified_buy_candidate ? "#3e7a58" : "#394554", background: "#080c11" }}>
            <div style={small}>QUALIFICATION GATE</div>
            <div style={{ marginTop: "8px", fontSize: "22px", fontWeight: 900, color: result.qualification.qualified_buy_candidate ? "#69d99a" : "#d7b76a" }}>
              {labelize(result.qualification.stage)}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(130px, 1fr))", gap: "9px", marginTop: "13px", fontSize: "12px" }}>
              <div><span style={small}>Committee</span><div>{result.committee.disposition} · {pct(result.committee.confidence)}</div></div>
              <div><span style={small}>Evidence</span><div>{pct(result.evidence_summary.average_quality_score)} · {result.evidence_summary.evidence_count ?? 0}</div></div>
              <div><span style={small}>Risk</span><div>{result.risk.decision ?? "—"}</div></div>
              <div><span style={small}>Paper Buy</span><div>{result.qualification.paper_buy_enabled ? "ENABLED" : "LOCKED"}</div></div>
            </div>
            {result.qualification.unmet_requirements.length > 0 && (
              <div style={{ marginTop: "13px", color: "#c9a768", fontSize: "12px", lineHeight: 1.6 }}>
                Still blocking qualification: {result.qualification.unmet_requirements.map(labelize).join(" · ")}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export default EvidenceGapHunterPanel;

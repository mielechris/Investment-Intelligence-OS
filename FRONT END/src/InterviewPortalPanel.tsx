import { useMemo, useState } from "react";

const API = "http://127.0.0.1:8002";

type Interview = {
  interview_id: string;
  subject_name: string;
  professional_role?: string;
  organization_context?: string;
  expertise_context?: string;
  objective: string;
  status: string;
  compliance_status: string;
};

type Insight = {
  insight_index: number;
  claim: string;
  category: string;
  confidence: number;
  source_excerpt: string;
  applicability: string;
  restriction_risk: "LOW" | "MEDIUM" | "HIGH";
  restriction_reason?: string;
};

type InsightPacket = {
  interview_insight_packet_id: string;
  interview_id: string;
  subject_name: string;
  summary: string;
  expertise_areas: string[];
  compliance_flags: string[];
  candidate_agent_roles: string[];
  insights: Insight[];
};

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function InterviewPortalPanel() {
  const [subjectName, setSubjectName] = useState("");
  const [role, setRole] = useState("");
  const [organization, setOrganization] = useState("");
  const [expertise, setExpertise] = useState("");
  const [objective, setObjective] = useState("Capture reusable professional judgment for IIOS research");
  const [transcript, setTranscript] = useState("");
  const [interview, setInterview] = useState<Interview | null>(null);
  const [packet, setPacket] = useState<InsightPacket | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [attestNoMnpi, setAttestNoMnpi] = useState(false);
  const [attestRights, setAttestRights] = useState(false);
  const [approvalNotes, setApprovalNotes] = useState("");
  const [message, setMessage] = useState("Start a professional interview record, paste or type the transcript, then extract governed judgment.");
  const [busy, setBusy] = useState(false);
  const [publishedCount, setPublishedCount] = useState(0);

  const selectableCount = useMemo(
    () => packet?.insights.filter((item) => item.restriction_risk === "LOW").length ?? 0,
    [packet]
  );

  const create = async () => {
    setBusy(true);
    try {
      const response = await fetch(`${API}/interview-portal/interviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject_name: subjectName,
          professional_role: role,
          organization_context: organization,
          expertise_context: expertise,
          objective,
          confidentiality_scope: "Public/non-confidential professional judgment only; no MNPI or employer/client confidential information",
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as Interview;
      setInterview(data);
      setPacket(null);
      setSelected(new Set());
      setPublishedCount(0);
      setMessage(`Interview ${data.interview_id.slice(-8)} created. Add the transcript and save it.`);
    } catch (error) {
      setMessage(error instanceof Error ? `Interview error: ${error.message}` : "Interview creation failed");
    } finally {
      setBusy(false);
    }
  };

  const saveTranscript = async () => {
    if (!interview) return;
    setBusy(true);
    try {
      const response = await fetch(`${API}/interview-portal/interviews/${interview.interview_id}/transcript`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript, append: false }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as Interview;
      setInterview(data);
      setMessage("Transcript saved to the persistent ledger. Ready to extract judgment.");
    } catch (error) {
      setMessage(error instanceof Error ? `Transcript error: ${error.message}` : "Transcript save failed");
    } finally {
      setBusy(false);
    }
  };

  const extract = async () => {
    if (!interview) return;
    setBusy(true);
    setMessage("Extracting transcript-supported judgment and screening for potentially restricted information...");
    try {
      const response = await fetch(`${API}/interview-portal/interviews/${interview.interview_id}/extract`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as InsightPacket;
      setPacket(data);
      setSelected(new Set());
      setMessage(`Extraction complete: ${data.insights.length} insights. Human review is required before anything enters the Judgment Bank.`);
    } catch (error) {
      setMessage(error instanceof Error ? `Extraction error: ${error.message}` : "Extraction failed");
    } finally {
      setBusy(false);
    }
  };

  const toggle = (index: number, enabled: boolean) => {
    setSelected((current) => {
      const next = new Set(current);
      if (enabled) next.add(index);
      else next.delete(index);
      return next;
    });
  };

  const approve = async () => {
    if (!interview) return;
    setBusy(true);
    try {
      const response = await fetch(`${API}/interview-portal/interviews/${interview.interview_id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved_insight_indexes: Array.from(selected),
          attest_no_mnpi: attestNoMnpi,
          attest_right_to_use: attestRights,
          approval_notes: approvalNotes,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json() as { judgment_bank_entries_added: number; restricted_insights: Insight[] };
      setPublishedCount(data.judgment_bank_entries_added);
      setMessage(`${data.judgment_bank_entries_added} approved low-risk insights added to the professional Judgment Bank. ${data.restricted_insights.length} selected insights were blocked by the restriction gate.`);
    } catch (error) {
      setMessage(error instanceof Error ? `Approval error: ${error.message}` : "Approval failed");
    } finally {
      setBusy(false);
    }
  };

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
  const input = {
    width: "100%",
    boxSizing: "border-box" as const,
    background: "#0d131b",
    border: "1px solid #303b49",
    color: "#f4f4f4",
    borderRadius: "7px",
    padding: "11px 12px",
    fontSize: "13px",
  };

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={{ ...panel, borderColor: "#315d67" }}>
        <div style={small}>PROFESSIONAL INTERVIEW PORTAL · JUDGMENT CAPTURE</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "20px", alignItems: "start", flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: "7px 0 5px" }}>Capture expert judgment without turning the person into a black box</h2>
            <div style={{ color: "#8c99a8", fontSize: "13px", maxWidth: "850px", lineHeight: 1.5 }}>
              Transcript-supported insights keep their provenance. Nothing is published to research memory until you approve it, and medium/high restriction-risk items are blocked from the Judgment Bank.
            </div>
          </div>
          <div style={{ color: "#71c6d4", fontSize: "11px", letterSpacing: "1px" }}>HUMAN APPROVAL REQUIRED · NO AUTO TRADE EVIDENCE</div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(220px, 1fr))", gap: "10px", marginTop: "18px" }}>
          <input style={input} value={subjectName} onChange={(event) => setSubjectName(event.target.value)} placeholder="Professional name" />
          <input style={input} value={role} onChange={(event) => setRole(event.target.value)} placeholder="Role / title" />
          <input style={input} value={organization} onChange={(event) => setOrganization(event.target.value)} placeholder="Organization context (optional)" />
          <input style={input} value={expertise} onChange={(event) => setExpertise(event.target.value)} placeholder="Expertise context" />
        </div>
        <input style={{ ...input, marginTop: "10px" }} value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="Interview objective" />

        <div style={{ display: "flex", gap: "9px", flexWrap: "wrap", marginTop: "12px" }}>
          <button onClick={() => void create()} disabled={busy || subjectName.trim().length < 2 || objective.trim().length < 3} style={{ border: "1px solid #4c8290", background: "#12323a", color: "#d6f4f8", borderRadius: "7px", padding: "11px 15px", fontWeight: 800 }}>
            CREATE INTERVIEW RECORD
          </button>
          {interview && <div style={{ alignSelf: "center", color: "#8997a6", fontSize: "12px" }}>ID {interview.interview_id.slice(-8)} · {interview.status} · {interview.compliance_status}</div>}
        </div>

        {interview && (
          <div style={{ marginTop: "17px" }}>
            <div style={small}>TRANSCRIPT / NOTES</div>
            <textarea
              style={{ ...input, minHeight: "190px", marginTop: "8px", resize: "vertical" }}
              value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
              placeholder="Paste or type the professional interview transcript here. Do not include confidential employer/client information or MNPI."
            />
            <div style={{ display: "flex", gap: "9px", flexWrap: "wrap", marginTop: "10px" }}>
              <button onClick={() => void saveTranscript()} disabled={busy || transcript.trim().length < 5} style={{ border: "1px solid #3f5664", background: "#111a22", color: "#d5dee6", borderRadius: "7px", padding: "10px 14px", fontWeight: 800 }}>SAVE TRANSCRIPT</button>
              <button onClick={() => void extract()} disabled={busy || transcript.trim().length < 5} style={{ border: "1px solid #63528e", background: "#211936", color: "#e5dcff", borderRadius: "7px", padding: "10px 14px", fontWeight: 800 }}>{busy ? "WORKING..." : "EXTRACT JUDGMENT"}</button>
            </div>
          </div>
        )}

        <div style={{ marginTop: "13px", color: "#9ba8b6", fontSize: "12px", lineHeight: 1.5 }}>{message}</div>

        {packet && (
          <div style={{ ...panel, marginTop: "18px", padding: "16px", background: "#080c11" }}>
            <div style={small}>EXTRACTED JUDGMENT · HUMAN REVIEW</div>
            <div style={{ marginTop: "8px", fontSize: "14px", lineHeight: 1.55 }}>{packet.summary}</div>
            {packet.expertise_areas.length > 0 && <div style={{ marginTop: "9px", color: "#8fa0b1", fontSize: "12px" }}>Expertise: {packet.expertise_areas.join(" · ")}</div>}
            {packet.candidate_agent_roles.length > 0 && <div style={{ marginTop: "7px", color: "#a89bd0", fontSize: "12px" }}>Possible reusable roles: {packet.candidate_agent_roles.join(" · ")}</div>}
            {packet.compliance_flags.length > 0 && <div style={{ marginTop: "10px", color: "#e2ad6c", fontSize: "12px", lineHeight: 1.5 }}>Screening flags: {packet.compliance_flags.join(" · ")}</div>}

            <div style={{ marginTop: "14px" }}>
              {packet.insights.map((insight) => {
                const blocked = insight.restriction_risk !== "LOW";
                const tone = insight.restriction_risk === "LOW" ? "#64c990" : insight.restriction_risk === "MEDIUM" ? "#d7b76a" : "#ff7185";
                return (
                  <div key={insight.insight_index} style={{ borderTop: "1px solid #1e2731", padding: "12px 0", display: "grid", gridTemplateColumns: "28px 1fr", gap: "10px" }}>
                    <input type="checkbox" checked={selected.has(insight.insight_index)} disabled={blocked} onChange={(event) => toggle(insight.insight_index, event.target.checked)} />
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                        <strong>{insight.claim}</strong>
                        <span style={{ color: tone, fontSize: "11px", fontWeight: 800 }}>{insight.restriction_risk} RISK · {pct(insight.confidence)}</span>
                      </div>
                      <div style={{ marginTop: "5px", color: "#9ca8b5", fontSize: "12px" }}>{insight.category} · {insight.applicability || "general applicability"}</div>
                      <div style={{ marginTop: "6px", color: "#7f8c9c", fontSize: "11px", lineHeight: 1.45 }}>Excerpt: “{insight.source_excerpt || "No excerpt extracted"}”</div>
                      {insight.restriction_reason && <div style={{ marginTop: "5px", color: tone, fontSize: "11px" }}>{insight.restriction_reason}</div>}
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ ...panel, padding: "14px", marginTop: "12px", background: "#0a0f15" }}>
              <div style={small}>PUBLISH TO PROFESSIONAL JUDGMENT BANK</div>
              <label style={{ display: "block", marginTop: "10px", fontSize: "12px" }}>
                <input type="checkbox" checked={attestNoMnpi} onChange={(event) => setAttestNoMnpi(event.target.checked)} /> I attest the selected insights contain no MNPI or confidential employer/client information.
              </label>
              <label style={{ display: "block", marginTop: "8px", fontSize: "12px" }}>
                <input type="checkbox" checked={attestRights} onChange={(event) => setAttestRights(event.target.checked)} /> I attest I have the right to use these selected insights for IIOS research.
              </label>
              <input style={{ ...input, marginTop: "10px" }} value={approvalNotes} onChange={(event) => setApprovalNotes(event.target.value)} placeholder="Approval notes (optional)" />
              <button onClick={() => void approve()} disabled={busy || selected.size === 0 || !attestNoMnpi || !attestRights} style={{ marginTop: "10px", border: "1px solid #47775b", background: "#10261a", color: "#d4f6df", borderRadius: "7px", padding: "11px 15px", fontWeight: 900 }}>
                APPROVE SELECTED TO JUDGMENT BANK ({selected.size}/{selectableCount})
              </button>
              {publishedCount > 0 && <div style={{ marginTop: "9px", color: "#63cc91", fontSize: "12px" }}>{publishedCount} professional judgment entries published.</div>}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default InterviewPortalPanel;

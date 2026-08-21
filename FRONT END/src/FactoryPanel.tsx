import { useEffect, useState } from "react";

type InterviewSession = {
  id: string;
  subject_name: string;
  subject_context?: string | null;
  objective: string;
  transcript: string;
  status: string;
  created_at: string;
};

type InterviewInsight = {
  claim: string;
  category: string;
  confidence: number;
  source_excerpt: string;
};

type InsightPacket = {
  interview_id: string;
  subject_name: string;
  summary: string;
  expertise_areas: string[];
  insights: InterviewInsight[];
  candidate_agent_roles: string[];
  provenance_note: string;
};

type FactoryAgent = {
  id: string;
  name: string;
  role: string;
  mission: string;
  instructions: string;
  data_feeds: string[];
  evidence_requirements: string[];
  permissions: string[];
  status: "proposed" | "approved" | "disabled";
  model: string;
  source_interview_id?: string | null;
  source_subject_name?: string | null;
  provenance: string[];
};

const API_BASE = "http://localhost:8000";

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP fallback message.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

const panel = {
  border: "1px solid #273448",
  background: "linear-gradient(145deg, #0a0f17, #080b10)",
  borderRadius: "14px",
  padding: "22px",
};

const field = {
  width: "100%",
  boxSizing: "border-box" as const,
  background: "#0b1119",
  border: "1px solid #2b3a50",
  borderRadius: "8px",
  padding: "12px 14px",
  color: "#edf5ff",
  fontSize: "14px",
};

const label = {
  display: "block",
  color: "#7f91a9",
  fontSize: "10px",
  letterSpacing: "2px",
  marginBottom: "7px",
};

const button = {
  border: "1px solid #36536d",
  background: "linear-gradient(145deg, #11283b, #0b1824)",
  color: "#a8d8ff",
  borderRadius: "8px",
  padding: "11px 14px",
  fontWeight: 800,
  letterSpacing: "1px",
  cursor: "pointer",
};

function FactoryPanel() {
  const [subjectName, setSubjectName] = useState("");
  const [subjectContext, setSubjectContext] = useState("");
  const [objective, setObjective] = useState(
    "Capture reusable investment judgment, signals, decision rules, and risk checks."
  );
  const [transcript, setTranscript] = useState("");
  const [interview, setInterview] = useState<InterviewSession | null>(null);
  const [insights, setInsights] = useState<InsightPacket | null>(null);
  const [proposals, setProposals] = useState<FactoryAgent[]>([]);
  const [registry, setRegistry] = useState<FactoryAgent[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRegistry = async () => {
    try {
      const agents = await api<FactoryAgent[]>("/factory/agents");
      setRegistry(agents);
    } catch {
      // Registry is supplemental to the main interview workflow.
    }
  };

  useEffect(() => {
    void loadRegistry();
  }, []);

  const runStep = async (name: string, work: () => Promise<void>) => {
    setBusy(name);
    setError(null);
    setNotice(null);
    try {
      await work();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Factory request failed");
    } finally {
      setBusy(null);
    }
  };

  const createInterview = () =>
    runStep("create", async () => {
      const created = await api<InterviewSession>("/factory/interviews", {
        method: "POST",
        body: JSON.stringify({
          subject_name: subjectName,
          subject_context: subjectContext || null,
          objective,
        }),
      });
      setInterview(created);
      setInsights(null);
      setProposals([]);
      setNotice(`Interview room opened for ${created.subject_name}.`);
    });

  const saveTranscript = () =>
    runStep("transcript", async () => {
      if (!interview) return;
      const saved = await api<InterviewSession>(
        `/factory/interviews/${interview.id}/transcript`,
        {
          method: "PUT",
          body: JSON.stringify({ transcript, append: false }),
        }
      );
      setInterview(saved);
      setNotice("Transcript saved. Ready for extraction.");
    });

  const extractInsights = () =>
    runStep("extract", async () => {
      if (!interview) return;
      if (transcript !== interview.transcript) {
        const saved = await api<InterviewSession>(
          `/factory/interviews/${interview.id}/transcript`,
          {
            method: "PUT",
            body: JSON.stringify({ transcript, append: false }),
          }
        );
        setInterview(saved);
      }
      const packet = await api<InsightPacket>(
        `/factory/interviews/${interview.id}/extract`,
        { method: "POST" }
      );
      setInsights(packet);
      setProposals([]);
      setNotice("Insight packet extracted with interview provenance attached.");
    });

  const proposeAgents = () =>
    runStep("propose", async () => {
      if (!interview) return;
      const agents = await api<FactoryAgent[]>(
        `/factory/interviews/${interview.id}/agents/propose`,
        {
          method: "POST",
          body: JSON.stringify({ max_agents: 3 }),
        }
      );
      setProposals(agents);
      await loadRegistry();
      setNotice(`${agents.length} agent proposal${agents.length === 1 ? "" : "s"} created. Human approval is still required.`);
    });

  const setAgentStatus = (agentId: string, action: "approve" | "disable") =>
    runStep(`${action}-${agentId}`, async () => {
      const updated = await api<FactoryAgent>(
        `/factory/agents/${agentId}/${action}`,
        { method: "POST" }
      );
      setProposals((current) =>
        current.map((agent) => (agent.id === updated.id ? updated : agent))
      );
      await loadRegistry();
      setNotice(
        action === "approve"
          ? `${updated.name} deployed to the approved agent registry.`
          : `${updated.name} disabled.`
      );
    });

  const resetRoom = () => {
    setSubjectName("");
    setSubjectContext("");
    setObjective(
      "Capture reusable investment judgment, signals, decision rules, and risk checks."
    );
    setTranscript("");
    setInterview(null);
    setInsights(null);
    setProposals([]);
    setNotice(null);
    setError(null);
  };

  const approved = registry.filter((agent) => agent.status === "approved");

  return (
    <section
      style={{
        marginBottom: "28px",
        border: "1px solid #4a3477",
        background:
          "radial-gradient(circle at top left, rgba(83,42,135,.25), transparent 42%), #080b11",
        borderRadius: "16px",
        padding: "24px",
        boxShadow: "0 18px 50px rgba(0,0,0,.28)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "20px",
          alignItems: "flex-start",
          flexWrap: "wrap",
          marginBottom: "22px",
        }}
      >
        <div>
          <div
            style={{
              color: "#b88cff",
              letterSpacing: "4px",
              fontSize: "11px",
              marginBottom: "8px",
            }}
          >
            AGENT FACTORY // V1.2
          </div>
          <h2 style={{ margin: 0, fontSize: "28px" }}>Interview Room</h2>
          <p style={{ color: "#8d9aae", maxWidth: "720px", lineHeight: 1.55 }}>
            Turn a real conversation into traceable investment insights and reusable specialist
            agents. Proposals stay locked until you explicitly deploy them.
          </p>
        </div>
        <div
          style={{
            border: "1px solid #5a3f87",
            background: "#170f25",
            color: "#c6a8ff",
            borderRadius: "8px",
            padding: "10px 14px",
            fontSize: "11px",
            letterSpacing: "2px",
          }}
        >
          HUMAN APPROVAL REQUIRED
        </div>
      </div>

      {(notice || error) && (
        <div
          style={{
            border: `1px solid ${error ? "#7b3042" : "#315f54"}`,
            background: error ? "#1c0b10" : "#0b1916",
            color: error ? "#ff8998" : "#79d6bd",
            borderRadius: "8px",
            padding: "12px 14px",
            marginBottom: "18px",
          }}
        >
          {error ?? notice}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(310px, 1fr))",
          gap: "18px",
        }}
      >
        <div style={panel}>
          <div style={{ color: "#7cbfff", fontSize: "11px", letterSpacing: "3px" }}>
            01 // OPEN INTERVIEW
          </div>
          <h3>Source & Objective</h3>

          <label style={{ marginBottom: "14px", display: "block" }}>
            <span style={label}>SUBJECT NAME</span>
            <input
              value={subjectName}
              onChange={(event) => setSubjectName(event.target.value)}
              placeholder="Jesse"
              style={field}
              disabled={Boolean(interview)}
            />
          </label>

          <label style={{ marginBottom: "14px", display: "block" }}>
            <span style={label}>CONTEXT</span>
            <input
              value={subjectContext}
              onChange={(event) => setSubjectContext(event.target.value)}
              placeholder="Operator, investor, sector expert..."
              style={field}
              disabled={Boolean(interview)}
            />
          </label>

          <label style={{ display: "block" }}>
            <span style={label}>INTERVIEW OBJECTIVE</span>
            <textarea
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              rows={4}
              style={{ ...field, resize: "vertical" }}
              disabled={Boolean(interview)}
            />
          </label>

          <div style={{ display: "flex", gap: "10px", marginTop: "16px", flexWrap: "wrap" }}>
            {!interview ? (
              <button
                style={button}
                onClick={createInterview}
                disabled={!subjectName.trim() || !objective.trim() || busy !== null}
              >
                {busy === "create" ? "OPENING..." : "OPEN INTERVIEW ROOM"}
              </button>
            ) : (
              <button style={button} onClick={resetRoom} disabled={busy !== null}>
                START NEW INTERVIEW
              </button>
            )}
          </div>

          {interview && (
            <div style={{ marginTop: "16px", color: "#8291a6", fontSize: "12px" }}>
              Session <strong style={{ color: "#b7c7dc" }}>{interview.id.slice(0, 8)}</strong> · status{" "}
              <strong style={{ color: "#78cdb7" }}>{interview.status.toUpperCase()}</strong>
            </div>
          )}
        </div>

        <div style={panel}>
          <div style={{ color: "#7cbfff", fontSize: "11px", letterSpacing: "3px" }}>
            02 // CAPTURE
          </div>
          <h3>Interview Transcript</h3>
          <textarea
            value={transcript}
            onChange={(event) => setTranscript(event.target.value)}
            placeholder="Paste or capture the interview transcript here..."
            rows={14}
            style={{ ...field, resize: "vertical", lineHeight: 1.5 }}
            disabled={!interview}
          />
          <div style={{ display: "flex", gap: "10px", marginTop: "14px", flexWrap: "wrap" }}>
            <button
              style={button}
              onClick={saveTranscript}
              disabled={!interview || !transcript.trim() || busy !== null}
            >
              {busy === "transcript" ? "SAVING..." : "SAVE TRANSCRIPT"}
            </button>
            <button
              style={{ ...button, border: "1px solid #604d2f", color: "#f0c97c", background: "#1b150b" }}
              onClick={extractInsights}
              disabled={!interview || !transcript.trim() || busy !== null}
            >
              {busy === "extract" ? "EXTRACTING..." : "EXTRACT INTELLIGENCE"}
            </button>
          </div>
        </div>
      </div>

      {insights && (
        <div style={{ ...panel, marginTop: "18px", border: "1px solid #31564f" }}>
          <div style={{ color: "#6ed0b2", fontSize: "11px", letterSpacing: "3px" }}>
            03 // INSIGHT PACKET
          </div>
          <h3 style={{ marginBottom: "8px" }}>{insights.subject_name} Interview Intelligence</h3>
          <p style={{ color: "#a8b6c7", lineHeight: 1.6 }}>{insights.summary}</p>

          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "18px" }}>
            {insights.expertise_areas.map((area) => (
              <span
                key={area}
                style={{
                  border: "1px solid #31564f",
                  background: "#0d1a18",
                  color: "#7fd8bd",
                  padding: "6px 9px",
                  borderRadius: "999px",
                  fontSize: "11px",
                }}
              >
                {area}
              </span>
            ))}
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: "12px",
            }}
          >
            {insights.insights.map((item, index) => (
              <div
                key={`${item.category}-${index}`}
                style={{
                  background: "#0b1115",
                  border: "1px solid #23363a",
                  borderRadius: "9px",
                  padding: "14px",
                }}
              >
                <div style={{ color: "#6ed0b2", fontSize: "10px", letterSpacing: "2px" }}>
                  {item.category.toUpperCase()} // {Math.round(item.confidence * 100)}%
                </div>
                <p style={{ color: "#e0e8ee", lineHeight: 1.45 }}>{item.claim}</p>
                <div style={{ color: "#73818e", fontSize: "12px", fontStyle: "italic" }}>
                  “{item.source_excerpt}”
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: "16px", color: "#758394", fontSize: "12px" }}>
            Provenance: {insights.provenance_note}
          </div>

          <button
            style={{ ...button, marginTop: "16px", border: "1px solid #573e85", color: "#c7a9ff", background: "#170f26" }}
            onClick={proposeAgents}
            disabled={busy !== null}
          >
            {busy === "propose" ? "DESIGNING AGENTS..." : "GENERATE AGENT PROPOSALS"}
          </button>
        </div>
      )}

      {proposals.length > 0 && (
        <div style={{ marginTop: "18px" }}>
          <div style={{ color: "#bd91ff", fontSize: "11px", letterSpacing: "3px", marginBottom: "10px" }}>
            04 // HUMAN DEPLOYMENT GATE
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
              gap: "14px",
            }}
          >
            {proposals.map((agent) => (
              <div
                key={agent.id}
                style={{
                  ...panel,
                  border:
                    agent.status === "approved"
                      ? "1px solid #33765f"
                      : agent.status === "disabled"
                      ? "1px solid #5a3038"
                      : "1px solid #503b72",
                }}
              >
                <div
                  style={{
                    color:
                      agent.status === "approved"
                        ? "#6fd1aa"
                        : agent.status === "disabled"
                        ? "#cc7381"
                        : "#c49bff",
                    fontSize: "10px",
                    letterSpacing: "2px",
                  }}
                >
                  {agent.status.toUpperCase()}
                </div>
                <h3 style={{ marginBottom: "5px" }}>{agent.name}</h3>
                <div style={{ color: "#8392a6", fontSize: "12px", marginBottom: "12px" }}>
                  {agent.role}
                </div>
                <p style={{ color: "#b6c2cf", lineHeight: 1.5 }}>{agent.mission}</p>

                <div style={{ marginTop: "12px" }}>
                  <span style={label}>EVIDENCE REQUIREMENTS</span>
                  <ul style={{ color: "#8f9eae", paddingLeft: "18px", lineHeight: 1.5 }}>
                    {agent.evidence_requirements.slice(0, 4).map((requirement) => (
                      <li key={requirement}>{requirement}</li>
                    ))}
                  </ul>
                </div>

                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  {agent.status !== "approved" && (
                    <button
                      style={{ ...button, border: "1px solid #33765f", color: "#80dfbd", background: "#0b1b16" }}
                      onClick={() => setAgentStatus(agent.id, "approve")}
                      disabled={busy !== null}
                    >
                      {busy === `approve-${agent.id}` ? "DEPLOYING..." : "APPROVE & DEPLOY"}
                    </button>
                  )}
                  {agent.status !== "disabled" && (
                    <button
                      style={{ ...button, border: "1px solid #5f333c", color: "#d58491", background: "#1a0d11" }}
                      onClick={() => setAgentStatus(agent.id, "disable")}
                      disabled={busy !== null}
                    >
                      DISABLE
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ ...panel, marginTop: "18px", border: "1px solid #2f435c" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "15px", alignItems: "center", flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "#79bfff", fontSize: "11px", letterSpacing: "3px" }}>
              FACTORY FLOOR REGISTRY
            </div>
            <h3 style={{ marginBottom: "4px" }}>Approved Dynamic Agents</h3>
            <div style={{ color: "#7f8d9e", fontSize: "12px" }}>
              {approved.length} approved · {registry.length} total definitions
            </div>
          </div>
          <button style={button} onClick={() => void loadRegistry()} disabled={busy !== null}>
            REFRESH REGISTRY
          </button>
        </div>

        {approved.length === 0 ? (
          <div
            style={{
              marginTop: "16px",
              border: "1px dashed #314052",
              borderRadius: "9px",
              padding: "18px",
              color: "#708094",
            }}
          >
            No dynamic agents deployed yet. The factory floor is suspiciously quiet.
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
              gap: "12px",
              marginTop: "16px",
            }}
          >
            {approved.map((agent) => (
              <div
                key={agent.id}
                style={{
                  border: "1px solid #2b6855",
                  background: "linear-gradient(145deg, #0b1915, #09110f)",
                  borderRadius: "10px",
                  padding: "15px",
                }}
              >
                <div style={{ color: "#63c6a3", fontSize: "10px", letterSpacing: "2px" }}>
                  DEPLOYED
                </div>
                <strong style={{ display: "block", marginTop: "7px" }}>{agent.name}</strong>
                <span style={{ color: "#798a9c", fontSize: "12px" }}>{agent.role}</span>
                {agent.source_subject_name && (
                  <div style={{ color: "#607183", fontSize: "11px", marginTop: "9px" }}>
                    Provenance: interview with {agent.source_subject_name}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default FactoryPanel;

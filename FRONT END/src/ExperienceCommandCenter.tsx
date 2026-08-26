import { useEffect, useMemo, useState } from "react";
import { EXPERIENCE_PHASES, FACTORY_ZONES } from "./experienceBlueprint";

const API = "http://127.0.0.1:8002";

type SystemStatus = {
  version?: string;
  paper_mode?: boolean;
  automatic_monitoring?: boolean;
  provider_hardening?: boolean;
  judgment_bank?: boolean;
  professional_interview_portal?: boolean;
  kimi_research_intelligence?: boolean;
  grok_research_intelligence?: boolean;
};

type Agent = {
  key: string;
  name: string;
  room?: string;
  status?: string;
};

type FactoryStatus = {
  generated_at?: string;
  activity?: {
    recent_event_count?: number;
    agent_completions?: number;
    committee_completions?: number;
    risk_completions?: number;
    latest_event?: {
      event_type?: string;
      case_id?: string;
      created_at?: string;
      room?: string;
    } | null;
  };
  rooms?: Array<{
    key: string;
    label: string;
    count: number;
    activity_count?: number;
  }>;
  cases?: Array<{
    case_id: string;
    stage?: string;
    active_room?: string | null;
    live_execution?: boolean;
  }>;
  portfolio?: {
    nav?: number | null;
    cash?: number | null;
    positions?: number | null;
    return_pct?: number | null;
    drawdown_pct?: number | null;
  };
  validation?: {
    cases?: number | null;
    case_target?: number;
    structural_ready?: boolean;
    empirical_ready?: boolean;
    freeze_blockers?: string[];
  };
  safety?: {
    violations?: number | null;
    all_invariants?: boolean;
    live_execution?: boolean;
  };
};

type Telemetry = {
  system: SystemStatus | null;
  factory: FactoryStatus | null;
  agents: Agent[];
  online: boolean;
  error: string | null;
  loadedAt: string | null;
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function boolLabel(value: boolean | undefined, trueLabel: string, falseLabel = "OFF") {
  if (value === undefined) return "UNKNOWN";
  return value ? trueLabel : falseLabel;
}

function toneFor(value: "good" | "warn" | "bad" | "muted") {
  if (value === "good") return "#63e6a5";
  if (value === "warn") return "#e8c96b";
  if (value === "bad") return "#ff6d7c";
  return "#78889a";
}

function metricCard(label: string, value: string | number, tone: "good" | "warn" | "bad" | "muted" = "muted") {
  return (
    <div
      key={label}
      style={{
        border: "1px solid rgba(108, 139, 170, .24)",
        background: "rgba(7, 12, 18, .82)",
        borderRadius: "11px",
        padding: "12px 13px",
        minWidth: 0,
      }}
    >
      <div style={{ color: "#6e8197", fontSize: "9px", letterSpacing: "1.5px", fontWeight: 800 }}>
        {label}
      </div>
      <div style={{ marginTop: "6px", color: toneFor(tone), fontSize: "17px", fontWeight: 900, overflow: "hidden", textOverflow: "ellipsis" }}>
        {value}
      </div>
    </div>
  );
}

function normalize(value: string | undefined | null) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function roomTelemetry(zoneLabel: string, rooms: FactoryStatus["rooms"]) {
  const zone = normalize(zoneLabel);
  const words = zone.split(" ").filter((word) => word.length >= 4);
  if (!rooms?.length || !words.length) return null;
  return rooms.find((room) => {
    const candidate = normalize(`${room.key} ${room.label}`);
    return words.some((word) => candidate.includes(word));
  }) ?? null;
}

export default function ExperienceCommandCenter() {
  const [telemetry, setTelemetry] = useState<Telemetry>({
    system: null,
    factory: null,
    agents: [],
    online: false,
    error: null,
    loadedAt: null,
  });

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const [system, factory, agentPayload] = await Promise.all([
          fetchJson<SystemStatus>("/system/status"),
          fetchJson<FactoryStatus>("/factory-room/status"),
          fetchJson<{ agents: Agent[] }>("/agents"),
        ]);
        if (!active) return;
        setTelemetry({
          system,
          factory,
          agents: agentPayload.agents || [],
          online: true,
          error: null,
          loadedAt: new Date().toISOString(),
        });
      } catch (error) {
        if (!active) return;
        setTelemetry((current) => ({
          ...current,
          online: false,
          error: error instanceof Error ? error.message : "Telemetry request failed",
          loadedAt: new Date().toISOString(),
        }));
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const liveExecution = telemetry.factory?.safety?.live_execution;
  const safetyGood = telemetry.factory?.safety?.all_invariants === true && liveExecution === false;
  const activeCases = telemetry.factory?.cases?.length ?? 0;
  const recentEvents = telemetry.factory?.activity?.recent_event_count ?? 0;
  const agentCompletions = telemetry.factory?.activity?.agent_completions ?? 0;
  const blockers = telemetry.factory?.validation?.freeze_blockers ?? [];

  const roomCount = useMemo(
    () => (telemetry.factory?.rooms || []).reduce((sum, room) => sum + Number(room.count || 0), 0),
    [telemetry.factory?.rooms]
  );

  const panel = {
    background: "linear-gradient(180deg, rgba(9,14,22,.97), rgba(4,7,11,.97))",
    border: "1px solid rgba(92, 132, 170, .28)",
    borderRadius: "17px",
    boxShadow: "0 22px 70px rgba(0,0,0,.34)",
  } as const;

  return (
    <section style={{ ...panel, padding: "22px", marginBottom: "22px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "20px", flexWrap: "wrap" }}>
        <div>
          <div style={{ color: "#66839d", fontSize: "10px", letterSpacing: "3px", fontWeight: 900 }}>
            EXPERIENCE TRACK · X0 / X1
          </div>
          <h2 style={{ margin: "7px 0 5px", fontSize: "28px" }}>FACTORY BLUEPRINT + COMMAND CENTER</h2>
          <div style={{ color: "#77899c", maxWidth: "780px", lineHeight: 1.5, fontSize: "12px" }}>
            The map below is the canonical IIOS floor plan. Runtime indicators come only from live backend state; unavailable telemetry stays unknown rather than being invented.
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <div style={{ color: telemetry.online ? "#63e6a5" : "#ff6d7c", fontWeight: 900, fontSize: "11px", letterSpacing: "2px" }}>
            {telemetry.online ? "COMMAND CENTER ONLINE" : "COMMAND CENTER OFFLINE"}
          </div>
          <div style={{ color: "#75879b", marginTop: "5px", fontSize: "11px" }}>
            API {API} · v{telemetry.system?.version ?? "UNKNOWN"}
          </div>
          {telemetry.error && (
            <div style={{ color: "#ff8a96", marginTop: "5px", fontSize: "10px", maxWidth: "390px" }}>{telemetry.error}</div>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(8, minmax(110px, 1fr))", gap: "8px", marginTop: "18px", overflowX: "auto" }}>
        {metricCard("SYSTEM", telemetry.online ? "ONLINE" : "OFFLINE", telemetry.online ? "good" : "bad")}
        {metricCard("MODE", boolLabel(telemetry.system?.paper_mode, "PAPER / SHADOW"), telemetry.system?.paper_mode ? "good" : "warn")}
        {metricCard("LIVE CAPITAL", liveExecution === false ? "LOCKED" : liveExecution === true ? "ENABLED" : "UNKNOWN", liveExecution === false ? "good" : liveExecution === true ? "bad" : "muted")}
        {metricCard("SAFETY", safetyGood ? "INVARIANTS HOLD" : telemetry.factory?.safety?.all_invariants === false ? "VIOLATION" : "UNKNOWN", safetyGood ? "good" : telemetry.factory?.safety?.all_invariants === false ? "bad" : "muted")}
        {metricCard("AGENTS", telemetry.agents.length || "UNKNOWN", telemetry.agents.length ? "good" : "muted")}
        {metricCard("ACTIVE CASES", activeCases, activeCases > 0 ? "good" : "muted")}
        {metricCard("EVENTS · 5M", recentEvents, recentEvents > 0 ? "good" : "muted")}
        {metricCard("DESKS COMPLETE · 5M", agentCompletions, agentCompletions > 0 ? "good" : "muted")}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2.4fr) minmax(260px, .8fr)", gap: "14px", marginTop: "16px" }}>
        <div
          style={{
            border: "1px solid rgba(112, 151, 190, .2)",
            borderRadius: "14px",
            padding: "14px",
            background: "radial-gradient(circle at 50% 20%, rgba(34,64,91,.24), rgba(5,9,14,.9) 55%)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", marginBottom: "11px" }}>
            <div style={{ color: "#6d8298", fontSize: "9px", letterSpacing: "2px", fontWeight: 900 }}>X0 · CANONICAL FACTORY MAP</div>
            <div style={{ color: "#596b7f", fontSize: "10px" }}>{roomCount} runtime room occupants / items reported</div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(150px, 1fr))", gap: "9px" }}>
            {FACTORY_ZONES.map((zone) => {
              const runtimeRoom = roomTelemetry(zone.label, telemetry.factory?.rooms);
              const runtimeCount = runtimeRoom?.count;
              const runtimeActivity = runtimeRoom?.activity_count;
              const hasRuntime = runtimeRoom !== null;
              return (
                <article
                  key={zone.key}
                  style={{
                    minHeight: "122px",
                    padding: "13px",
                    borderRadius: "11px",
                    border: hasRuntime ? "1px solid rgba(99,230,165,.32)" : "1px solid #273746",
                    background: hasRuntime ? "rgba(10,35,29,.52)" : "rgba(10,17,25,.76)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
                    <span style={{ color: "#6b8299", fontSize: "8px", letterSpacing: "1.2px", fontWeight: 800 }}>{zone.phase} · {zone.category}</span>
                    <span style={{ color: hasRuntime ? "#63e6a5" : "#66788b", fontSize: "8px", fontWeight: 900 }}>
                      {hasRuntime ? `LIVE ${runtimeCount ?? 0}` : "CONTRACTED"}
                    </span>
                  </div>
                  <div style={{ marginTop: "8px", fontWeight: 900, fontSize: "13px" }}>{zone.label}</div>
                  <div style={{ color: "#8392a3", marginTop: "7px", fontSize: "10px", lineHeight: 1.45 }}>{zone.purpose}</div>
                  {hasRuntime && runtimeActivity !== undefined && (
                    <div style={{ color: "#63e6a5", marginTop: "8px", fontSize: "9px" }}>Recent activity: {runtimeActivity}</div>
                  )}
                </article>
              );
            })}
          </div>
        </div>

        <aside style={{ border: "1px solid #273746", borderRadius: "14px", padding: "14px", background: "rgba(7,12,18,.78)" }}>
          <div style={{ color: "#6d8298", fontSize: "9px", letterSpacing: "2px", fontWeight: 900 }}>EXPERIENCE BUILD LINE</div>
          <div style={{ marginTop: "11px", display: "grid", gap: "7px" }}>
            {EXPERIENCE_PHASES.map((phase) => (
              <div key={phase.key} style={{ borderLeft: phase.key === "X0" || phase.key === "X1" ? "2px solid #63e6a5" : "2px solid #334353", padding: "7px 9px" }}>
                <div style={{ color: phase.key === "X0" || phase.key === "X1" ? "#dfffee" : "#a0adbb", fontSize: "11px", fontWeight: 900 }}>
                  {phase.key} · {phase.name}
                </div>
                <div style={{ color: "#718397", fontSize: "9px", lineHeight: 1.4, marginTop: "3px" }}>{phase.goal}</div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: "14px", paddingTop: "12px", borderTop: "1px solid #263442" }}>
            <div style={{ color: "#6d8298", fontSize: "9px", letterSpacing: "1.5px", fontWeight: 900 }}>VALIDATION</div>
            <div style={{ color: "#9aabba", marginTop: "7px", fontSize: "10px", lineHeight: 1.55 }}>
              Structural ready: {String(telemetry.factory?.validation?.structural_ready ?? "UNKNOWN")}<br />
              Empirical ready: {String(telemetry.factory?.validation?.empirical_ready ?? "UNKNOWN")}<br />
              Freeze blockers: {blockers.length}
            </div>
          </div>

          <div style={{ marginTop: "13px", color: "#5f7286", fontSize: "9px", lineHeight: 1.5 }}>
            Last telemetry: {telemetry.loadedAt ? new Date(telemetry.loadedAt).toLocaleTimeString() : "NEVER"}
          </div>
        </aside>
      </div>
    </section>
  );
}

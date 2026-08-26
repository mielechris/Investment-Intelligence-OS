import { useEffect, useMemo, useState } from "react";
import { AGENT_VISUAL_CONTRACTS } from "./agentVisualContracts";
import type { RawLedgerEvent } from "./factoryLedgerAdapter";

const API = "http://127.0.0.1:8002";
const POLL_MS = 5000;

type AgentRuntime = {
  key: string;
  name: string;
  room?: string;
  status?: string;
};

type FactoryStatus = {
  activity?: {
    recent_events?: RawLedgerEvent[];
  };
};

type Telemetry = {
  agents: AgentRuntime[];
  recentEvents: RawLedgerEvent[];
  online: boolean;
  error: string | null;
  loadedAt: string | null;
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function normalize(value: string | null | undefined) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function eventMatchesAgent(event: RawLedgerEvent, key: string) {
  const raw = normalize(`${event.event_type || ""} ${JSON.stringify(event.payload || {})}`);
  const aliases: Record<string, string[]> = {
    policy: ["policy"],
    macro: ["macro", "rates"],
    fundamentals: ["fundamental"],
    market_structure: ["market structure", "positioning", "tape"],
    commodities: ["commodit", "supply chain", "physical markets"],
    geo_weather: ["geo weather", "geopolit", "weather"],
    skeptic: ["skeptic", "red team"],
    portfolio: ["portfolio"],
  };
  return (aliases[key] || [key]).some((alias) => raw.includes(alias));
}

function isAgentEvent(event: RawLedgerEvent) {
  const type = String(event.event_type || "").toUpperCase();
  return type.includes("AGENT") || type.includes("SPECIALIST") || type.includes("DESK");
}

function runtimeTone(active: boolean, online: boolean) {
  if (!online) return { border: "rgba(255,109,124,.48)", glow: "rgba(255,109,124,.10)", text: "#ff9ba6", label: "OFFLINE" };
  if (active) return { border: "rgba(99,230,165,.58)", glow: "rgba(99,230,165,.13)", text: "#8bf0bd", label: "ACTIVE" };
  return { border: "rgba(100,129,157,.30)", glow: "transparent", text: "#73879a", label: "IDLE" };
}

export default function SpecialistDeskFloor() {
  const [telemetry, setTelemetry] = useState<Telemetry>({
    agents: [],
    recentEvents: [],
    online: false,
    error: null,
    loadedAt: null,
  });

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const [agentPayload, factory] = await Promise.all([
          fetchJson<{ agents: AgentRuntime[] }>("/agents"),
          fetchJson<FactoryStatus>("/factory-room/status"),
        ]);
        if (!active) return;
        setTelemetry({
          agents: agentPayload.agents || [],
          recentEvents: factory.activity?.recent_events || [],
          online: true,
          error: null,
          loadedAt: new Date().toISOString(),
        });
      } catch (error) {
        if (!active) return;
        setTelemetry((current) => ({
          ...current,
          online: false,
          error: error instanceof Error ? error.message : "Desk telemetry request failed",
          loadedAt: new Date().toISOString(),
        }));
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const recentAgentEvents = useMemo(
    () => telemetry.recentEvents.filter(isAgentEvent),
    [telemetry.recentEvents]
  );

  const activeKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const contract of AGENT_VISUAL_CONTRACTS) {
      if (recentAgentEvents.some((event) => eventMatchesAgent(event, contract.key))) keys.add(contract.key);
    }
    return keys;
  }, [recentAgentEvents]);

  const maxMessage = useMemo(() => {
    if (!telemetry.online) return "No telemetry, no theater. MAX is off the floor.";
    const activeContract = AGENT_VISUAL_CONTRACTS.find((contract) => activeKeys.has(contract.key));
    if (activeContract) return activeContract.maxReaction;
    if (recentAgentEvents.length > 0) return "The desks are moving. I just don't have a clean owner on that event yet.";
    return "Quiet floor. Nobody gets to fake being busy.";
  }, [activeKeys, recentAgentEvents.length, telemetry.online]);

  return (
    <section style={{ marginBottom: "22px", borderRadius: "18px", border: "1px solid rgba(82,112,143,.28)", background: "linear-gradient(180deg, rgba(8,11,16,.98), rgba(3,5,9,.99))", overflow: "hidden", boxShadow: "0 28px 90px rgba(0,0,0,.38)" }}>
      <div style={{ padding: "20px 20px 15px", borderBottom: "1px solid rgba(82,112,143,.20)", background: "radial-gradient(circle at 50% -20%, rgba(52,88,119,.22), transparent 58%)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "18px", flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "#788da2", fontSize: "9px", fontWeight: 900, letterSpacing: "2.5px" }}>X3 · EIGHT SPECIALIST DESKS</div>
            <h2 style={{ margin: "7px 0 5px", fontSize: "27px", letterSpacing: ".3px" }}>THE INTELLIGENCE BULLPEN</h2>
            <div style={{ color: "#7c8b9a", fontSize: "11px", lineHeight: 1.55, maxWidth: "760px" }}>
              Each station is bound to one backend agent. A desk lights only when current agent telemetry or a recent ledger event supports it. Idle means idle; offline means offline.
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ color: telemetry.online ? "#73e9b0" : "#ff7b89", fontWeight: 900, fontSize: "10px", letterSpacing: "1.8px" }}>
              {telemetry.online ? "DESK TELEMETRY LIVE" : "DESK TELEMETRY OFFLINE"}
            </div>
            <div style={{ color: "#66798c", marginTop: "5px", fontSize: "9px" }}>
              {telemetry.agents.length || 0} agents · poll {POLL_MS / 1000}s
            </div>
            {telemetry.error && <div style={{ color: "#ff919c", marginTop: "5px", fontSize: "9px", maxWidth: "380px" }}>{telemetry.error}</div>}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(190px, 1fr))", gap: "10px", padding: "14px 14px 12px" }}>
        {AGENT_VISUAL_CONTRACTS.map((contract) => {
          const runtime = telemetry.agents.find((agent) => agent.key === contract.key);
          const eventActive = activeKeys.has(contract.key);
          const reportedActive = normalize(runtime?.status) !== "" && !["idle", "ready", "unknown"].includes(normalize(runtime?.status));
          const isActive = telemetry.online && (eventActive || reportedActive);
          const tone = runtimeTone(isActive, telemetry.online);

          return (
            <article key={contract.key} style={{ minHeight: "245px", borderRadius: "13px", padding: "13px", border: `1px solid ${tone.border}`, background: "linear-gradient(160deg, rgba(14,20,28,.96), rgba(6,9,13,.98))", boxShadow: `0 0 30px ${tone.glow}`, position: "relative", overflow: "hidden" }}>
              <div style={{ position: "absolute", inset: 0, pointerEvents: "none", background: isActive ? "radial-gradient(circle at 50% 20%, rgba(61,188,139,.12), transparent 52%)" : "none" }} />
              <div style={{ position: "relative", zIndex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
                  <div style={{ color: "#6f8295", fontSize: "8px", letterSpacing: "1.4px", fontWeight: 900 }}>{contract.backendRoom.toUpperCase()}</div>
                  <div style={{ color: tone.text, fontSize: "8px", letterSpacing: "1.2px", fontWeight: 900 }}>{tone.label}</div>
                </div>
                <div style={{ marginTop: "9px", fontSize: "15px", fontWeight: 950 }}>{contract.floorTitle}</div>
                <div style={{ color: "#9eabb8", marginTop: "5px", fontSize: "10px", fontWeight: 800 }}>{runtime?.name || contract.backendName}</div>
                <div style={{ color: "#758697", marginTop: "8px", fontSize: "9px", lineHeight: 1.45 }}>{contract.characterArchetype}</div>

                <div style={{ marginTop: "12px", padding: "9px", borderRadius: "9px", border: "1px solid rgba(85,112,139,.18)", background: "rgba(4,8,12,.58)" }}>
                  <div style={{ color: "#61788d", fontSize: "8px", letterSpacing: "1px", fontWeight: 900 }}>DESK PROPS</div>
                  <div style={{ color: "#8998a7", marginTop: "5px", fontSize: "8px", lineHeight: 1.55 }}>{contract.visualProps.join(" · ")}</div>
                </div>

                <div style={{ marginTop: "10px", color: isActive ? "#9fecc8" : "#64778a", fontSize: "8px", lineHeight: 1.45 }}>
                  {isActive ? contract.activeBehavior : "Station remains visually cold until real telemetry supports activity."}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <div style={{ margin: "0 14px 14px", borderRadius: "13px", border: "1px solid rgba(130,102,64,.28)", background: "linear-gradient(90deg, rgba(24,19,12,.90), rgba(9,9,10,.96))", padding: "12px 14px", display: "grid", gridTemplateColumns: "70px minmax(0,1fr) auto", gap: "12px", alignItems: "center" }}>
        <div style={{ width: "58px", height: "58px", borderRadius: "50%", border: "1px solid rgba(202,162,91,.38)", display: "grid", placeItems: "center", fontWeight: 950, fontSize: "18px", color: "#d9b775", background: "radial-gradient(circle, rgba(143,104,43,.18), rgba(6,7,9,.96) 68%)" }}>MAX</div>
        <div>
          <div style={{ color: "#8f7852", fontSize: "8px", letterSpacing: "1.5px", fontWeight: 900 }}>FLOOR BOSS · STATE-BOUND REACTION</div>
          <div style={{ color: "#c8b898", marginTop: "5px", fontSize: "11px", lineHeight: 1.45 }}>{maxMessage}</div>
        </div>
        <div style={{ color: telemetry.online ? "#7f9d8e" : "#a36d72", fontSize: "8px", fontWeight: 900, letterSpacing: "1px" }}>
          {telemetry.online ? "WATCHING FLOOR" : "OFF FLOOR"}
        </div>
      </div>
    </section>
  );
}

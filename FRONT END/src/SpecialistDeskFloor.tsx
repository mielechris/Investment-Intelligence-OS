import { useEffect, useMemo, useState } from "react";
import { AGENT_VISUAL_CONTRACTS } from "./agentVisualContracts";
import type { RawLedgerEvent } from "./factoryLedgerAdapter";

const API = "http://127.0.0.1:8002";
const POLL_MS = 5000;

const BRASS_BRIGHT = "#e4ad55";
const BRASS_DARK = "#6f481d";
const GREEN = "#67df75";
const RED = "#f05454";
const PURPLE = "#b16cff";

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
  safety?: {
    all_invariants?: boolean;
    live_execution?: boolean;
  };
  portfolio?: {
    nav?: number | null;
    cash?: number | null;
    positions?: number | null;
    return_pct?: number | null;
    drawdown_pct?: number | null;
  };
};

type SystemStatus = {
  paper_mode?: boolean;
  automatic_monitoring?: boolean;
  version?: string;
};

type Telemetry = {
  agents: AgentRuntime[];
  recentEvents: RawLedgerEvent[];
  factory: FactoryStatus | null;
  system: SystemStatus | null;
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
    macro: ["macro", "rates", "fed"],
    fundamentals: ["fundamental", "valuation", "earnings"],
    market_structure: ["market structure", "positioning", "tape", "flow"],
    commodities: ["commodit", "supply chain", "physical markets", "inventory"],
    geo_weather: ["geo weather", "geopolit", "weather", "sanction"],
    skeptic: ["skeptic", "red team", "falsifier", "gap"],
    portfolio: ["portfolio", "position sizing", "capital"],
  };
  return (aliases[key] || [key]).some((alias) => raw.includes(alias));
}

function isAgentEvent(event: RawLedgerEvent) {
  const type = String(event.event_type || "").toUpperCase();
  return type.includes("AGENT") || type.includes("SPECIALIST") || type.includes("DESK");
}

function runtimeState(active: boolean, online: boolean) {
  if (!online) return { label: "OFFLINE", text: RED, border: "rgba(240,84,84,.56)", glow: "rgba(240,84,84,.12)" };
  if (active) return { label: "ACTIVE", text: GREEN, border: "rgba(103,223,117,.58)", glow: "rgba(103,223,117,.14)" };
  return { label: "IDLE", text: "#8a795c", border: "rgba(197,138,53,.26)", glow: "transparent" };
}

function shortStatus(value: boolean | undefined, yes: string, no: string) {
  if (value === undefined) return "UNKNOWN";
  return value ? yes : no;
}

function ornamentedPanel(extra: React.CSSProperties = {}): React.CSSProperties {
  return {
    border: `1px solid ${BRASS_DARK}`,
    background: "linear-gradient(180deg, rgba(11,9,6,.98), rgba(4,4,3,.99))",
    boxShadow: "inset 0 0 0 1px rgba(229,173,85,.07), 0 18px 55px rgba(0,0,0,.34)",
    ...extra,
  };
}

function metricTone(value: number | null | undefined, badWhenNegative = false) {
  if (value === null || value === undefined) return "#8a795c";
  if (badWhenNegative && value < 0) return RED;
  return GREEN;
}

function fakePortraitSilhouette(seed: number, active: boolean) {
  const tilt = seed % 2 === 0 ? -4 : 4;
  return (
    <div style={{ height: 116, position: "relative", overflow: "hidden", borderBottom: `1px solid ${BRASS_DARK}`, background: "radial-gradient(circle at 50% 34%, rgba(128,89,42,.24), rgba(8,7,5,.96) 60%)" }}>
      <div style={{ position: "absolute", left: "50%", top: 18, width: 44, height: 44, transform: `translateX(-50%) rotate(${tilt}deg)`, borderRadius: "50% 50% 44% 44%", background: active ? "linear-gradient(180deg,#ad7d4f,#3e2c20)" : "linear-gradient(180deg,#60452e,#1f1913)", boxShadow: active ? "0 0 18px rgba(229,173,85,.2)" : "none" }} />
      <div style={{ position: "absolute", left: "50%", bottom: -22, width: 102, height: 94, transform: "translateX(-50%)", borderRadius: "46% 46% 8% 8%", background: active ? "linear-gradient(180deg,#463524,#0b0a08 72%)" : "linear-gradient(180deg,#2b241c,#090806 72%)", border: "1px solid rgba(197,138,53,.14)" }} />
      <div style={{ position: "absolute", inset: 0, background: "repeating-linear-gradient(90deg, transparent 0 22px, rgba(229,173,85,.025) 23px 24px)" }} />
      <div style={{ position: "absolute", left: 9, right: 9, bottom: 7, display: "flex", gap: 3 }}>
        {[0, 1, 2, 3, 4, 5].map((i) => <span key={i} style={{ height: 2 + ((seed + i) % 4) * 2, flex: 1, background: active && i % 2 === 0 ? GREEN : BRASS_DARK, opacity: .7 }} />)}
      </div>
    </div>
  );
}

export default function SpecialistDeskFloor() {
  const [telemetry, setTelemetry] = useState<Telemetry>({
    agents: [],
    recentEvents: [],
    factory: null,
    system: null,
    online: false,
    error: null,
    loadedAt: null,
  });

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const [agentPayload, factory, system] = await Promise.all([
          fetchJson<{ agents: AgentRuntime[] }>("/agents"),
          fetchJson<FactoryStatus>("/factory-room/status"),
          fetchJson<SystemStatus>("/system/status"),
        ]);
        if (!mounted) return;
        setTelemetry({
          agents: agentPayload.agents || [],
          recentEvents: factory.activity?.recent_events || [],
          factory,
          system,
          online: true,
          error: null,
          loadedAt: new Date().toISOString(),
        });
      } catch (error) {
        if (!mounted) return;
        setTelemetry((current) => ({
          ...current,
          online: false,
          error: error instanceof Error ? error.message : "X3 telemetry request failed",
          loadedAt: new Date().toISOString(),
        }));
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  const recentAgentEvents = useMemo(() => telemetry.recentEvents.filter(isAgentEvent), [telemetry.recentEvents]);

  const activeKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const contract of AGENT_VISUAL_CONTRACTS) {
      if (recentAgentEvents.some((event) => eventMatchesAgent(event, contract.key))) keys.add(contract.key);
    }
    return keys;
  }, [recentAgentEvents]);

  const activeCount = activeKeys.size;
  const latestEvent = telemetry.recentEvents[0];
  const safetyHold = telemetry.factory?.safety?.all_invariants === true && telemetry.factory?.safety?.live_execution === false;

  const maxMessage = useMemo(() => {
    if (!telemetry.online) return "No telemetry, no theater. MAX is off the floor.";
    const activeContract = AGENT_VISUAL_CONTRACTS.find((contract) => activeKeys.has(contract.key));
    if (activeContract) return activeContract.maxReaction;
    if (recentAgentEvents.length > 0) return "The floor moved. Ownership is unclear, so nobody gets credit yet.";
    return "Quiet floor. Nobody gets to fake being busy.";
  }, [activeKeys, recentAgentEvents.length, telemetry.online]);

  const paperReturn = telemetry.factory?.portfolio?.return_pct;
  const drawdown = telemetry.factory?.portfolio?.drawdown_pct;

  return (
    <section style={{ marginBottom: 24, color: "#d8c8a7", fontFamily: "Georgia, 'Times New Roman', serif" }}>
      <div style={{ ...ornamentedPanel({ borderRadius: 4, overflow: "hidden" }), background: "linear-gradient(180deg,#090704,#030302 70%)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px,.82fr) minmax(520px,1.9fr) minmax(270px,.78fr)", gap: 8, padding: 8 }}>
          <aside style={ornamentedPanel({ padding: 12, minHeight: 184 })}>
            <div style={{ color: BRASS_BRIGHT, fontSize: 11, letterSpacing: 1.8 }}>MARKET INTELLIGENCE FEED</div>
            <div style={{ color: telemetry.online ? GREEN : RED, fontSize: 8, marginTop: 3, letterSpacing: 1.2 }}>{telemetry.online ? "LIVE 24/7" : "OFFLINE"}</div>
            <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
              {[
                ["SYSTEM", telemetry.online ? "NORMAL" : "OFFLINE", telemetry.online ? GREEN : RED],
                ["AGENTS ACTIVE", String(activeCount), activeCount ? GREEN : "#927d5c"],
                ["PAPER MODE", shortStatus(telemetry.system?.paper_mode, "ENGAGED", "OFF"), telemetry.system?.paper_mode ? GREEN : RED],
                ["LIVE CAPITAL", telemetry.factory?.safety?.live_execution === false ? "DISABLED" : telemetry.factory?.safety?.live_execution === true ? "ENABLED" : "UNKNOWN", telemetry.factory?.safety?.live_execution === false ? GREEN : telemetry.factory?.safety?.live_execution === true ? RED : "#927d5c"],
                ["SAFETY", telemetry.factory?.safety?.all_invariants === true ? "ALL GREEN" : telemetry.factory?.safety?.all_invariants === false ? "VIOLATION" : "UNKNOWN", telemetry.factory?.safety?.all_invariants === true ? GREEN : telemetry.factory?.safety?.all_invariants === false ? RED : "#927d5c"],
              ].map(([label, value, tone]) => (
                <div key={String(label)} style={{ display: "flex", justifyContent: "space-between", gap: 10, borderTop: "1px solid rgba(197,138,53,.18)", paddingTop: 5, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 9 }}>
                  <span style={{ color: "#a18b64" }}>{label}</span><span style={{ color: String(tone), fontWeight: 800 }}>{value}</span>
                </div>
              ))}
            </div>
          </aside>

          <header style={ornamentedPanel({ padding: "11px 18px 12px", textAlign: "center", minHeight: 184, display: "grid", alignContent: "space-between" })}>
            <div>
              <div style={{ color: BRASS_BRIGHT, fontSize: 37, letterSpacing: 7, textShadow: "0 0 18px rgba(229,173,85,.24)" }}>IIOS</div>
              <div style={{ color: "#d6a65e", fontSize: 19, letterSpacing: 4 }}>INTELLIGENCE FACTORY</div>
              <div style={{ marginTop: 5, color: "#9d7440", fontSize: 9, letterSpacing: 2.6 }}>BUILT ON EVIDENCE. RUN ON DISCIPLINE.</div>
              <div style={{ marginTop: 6, color: RED, fontSize: 10, fontStyle: "italic", transform: "rotate(-1deg)" }}>QUESTIONABLY SUPERVISED.</div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", borderTop: `1px solid ${BRASS_DARK}`, marginTop: 10 }}>
              {[
                ["PAPER RETURN", paperReturn == null ? "UNKNOWN" : `${paperReturn.toFixed(2)}%`, metricTone(paperReturn, true)],
                ["DRAWDOWN", drawdown == null ? "UNKNOWN" : `${drawdown.toFixed(2)}%`, metricTone(drawdown, true)],
                ["POSITIONS", telemetry.factory?.portfolio?.positions ?? "UNKNOWN", GREEN],
                ["EVENTS", telemetry.recentEvents.length, telemetry.recentEvents.length ? GREEN : "#927d5c"],
                ["VERSION", telemetry.system?.version ?? "UNKNOWN", BRASS_BRIGHT],
              ].map(([label, value, tone]) => (
                <div key={String(label)} style={{ padding: "8px 7px 2px", borderRight: `1px solid ${BRASS_DARK}` }}>
                  <div style={{ fontSize: 7, color: "#85683f", letterSpacing: .8 }}>{label}</div>
                  <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", marginTop: 4, color: String(tone), fontSize: 13, fontWeight: 900 }}>{String(value)}</div>
                </div>
              ))}
            </div>
          </header>

          <aside style={ornamentedPanel({ minHeight: 184, padding: 12, display: "grid", gridTemplateColumns: "88px 1fr", gap: 10, alignItems: "center" })}>
            <div style={{ height: 120, position: "relative", border: `1px solid ${BRASS_DARK}`, background: "radial-gradient(circle at 50% 25%,rgba(169,118,62,.32),#080604 63%)" }}>
              <div style={{ position: "absolute", left: "50%", top: 18, transform: "translateX(-50%)", width: 48, height: 50, borderRadius: "50%", background: "linear-gradient(#a27a58,#37271e)" }} />
              <div style={{ position: "absolute", left: "50%", bottom: -7, transform: "translateX(-50%)", width: 82, height: 74, borderRadius: "44% 44% 0 0", background: "linear-gradient(#403026,#080705)" }} />
            </div>
            <div>
              <div style={{ color: BRASS_BRIGHT, fontSize: 18, letterSpacing: 2 }}>THE BOSS</div>
              <div style={{ color: "#9f7740", fontSize: 8, letterSpacing: 1.2, marginTop: 3 }}>CHIEF INVESTMENT OFFICER</div>
              <div style={{ color: "#c3a16e", marginTop: 12, fontSize: 11, lineHeight: 1.8 }}>“I DON'T PREDICT.<br />I PREPARE.<br />THEN I PROFIT.”</div>
              <div style={{ marginTop: 8, fontSize: 7, color: "#745b38" }}>No runtime claims attached to the portrait.</div>
            </div>
          </aside>
        </div>

        <div style={{ margin: "0 8px 8px", border: `1px solid ${BRASS_DARK}`, background: "#050403", padding: "8px 10px", textAlign: "center", color: BRASS_BRIGHT, fontSize: 11, letterSpacing: 2.2 }}>
          THE EIGHT AGENTS — EVERYONE HAS A ROLE. EGO IS NOT ONE.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(8, minmax(142px, 1fr))", gap: 5, padding: "0 8px 8px" }}>
          {AGENT_VISUAL_CONTRACTS.map((contract, index) => {
            const runtime = telemetry.agents.find((agent) => agent.key === contract.key);
            const eventActive = activeKeys.has(contract.key);
            const reportedActive = normalize(runtime?.status) !== "" && !["idle", "ready", "unknown"].includes(normalize(runtime?.status));
            const active = telemetry.online && (eventActive || reportedActive);
            const state = runtimeState(active, telemetry.online);
            const isSkeptic = contract.key === "skeptic";

            return (
              <article key={contract.key} style={{ ...ornamentedPanel(), minWidth: 0, overflow: "hidden", borderColor: isSkeptic ? "#73231f" : BRASS_DARK, boxShadow: `0 0 24px ${state.glow}` }}>
                <div style={{ padding: "7px 8px 6px", minHeight: 51 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 4, alignItems: "flex-start" }}>
                    <div style={{ color: isSkeptic ? RED : BRASS_BRIGHT, fontSize: 9, lineHeight: 1.2, fontWeight: 800 }}>{index + 1}. {contract.floorTitle}</div>
                    <span style={{ color: state.text, fontFamily: "ui-monospace,monospace", fontSize: 7 }}>{state.label}</span>
                  </div>
                  <div style={{ color: "#a79577", fontSize: 7, marginTop: 3, lineHeight: 1.25 }}>{contract.characterArchetype}</div>
                </div>
                {fakePortraitSilhouette(index + 3, active)}
                <div style={{ padding: 7, minHeight: 82 }}>
                  <div style={{ fontFamily: "ui-monospace,monospace", color: "#8a7555", fontSize: 7 }}>{runtime?.name || contract.backendName}</div>
                  <div style={{ marginTop: 6, color: active ? "#cdb989" : "#665a48", fontSize: 7, lineHeight: 1.35 }}>{active ? contract.activeBehavior : "Station cold until governed telemetry supports activity."}</div>
                  <div style={{ marginTop: 7, borderTop: "1px solid rgba(197,138,53,.14)", paddingTop: 5, color: isSkeptic ? "#b84d43" : "#806437", fontSize: 7 }}>MAX: {contract.maxReaction}</div>
                </div>
              </article>
            );
          })}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1.15fr 1.1fr 1.1fr .85fr", gap: 6, padding: "0 8px 8px" }}>
          <div style={ornamentedPanel({ padding: 10 })}>
            <div style={{ color: BRASS_BRIGHT, fontSize: 10 }}>BULLSHIT DETECTOR</div>
            <div style={{ marginTop: 12, height: 8, border: `1px solid ${BRASS_DARK}`, background: "linear-gradient(90deg,#2f6d31,#a88c28,#8d2c25)" }} />
            <div style={{ marginTop: 7, fontFamily: "ui-monospace,monospace", color: "#d6b56e", fontSize: 17 }}>{activeCount ? `${Math.min(99, 62 + activeCount * 4)}%` : "UNKNOWN"}</div>
            <div style={{ color: "#776447", fontSize: 7 }}>Entertainment meter only. Not investment telemetry.</div>
          </div>

          <div style={ornamentedPanel({ padding: 10 })}>
            <div style={{ color: BRASS_BRIGHT, fontSize: 10 }}>PREDICTION RECEIPTS</div>
            <div style={{ color: "#9a845f", fontSize: 7, marginTop: 7, lineHeight: 1.5 }}>You said it. The ledger timestamps it. Outcome review comes later.</div>
            <div style={{ marginTop: 8, color: telemetry.recentEvents.length ? GREEN : "#716046", fontFamily: "ui-monospace,monospace", fontSize: 9 }}>{telemetry.recentEvents.length} RECENT LEDGER EVENTS</div>
          </div>

          <div style={ornamentedPanel({ padding: 10 })}>
            <div style={{ color: BRASS_BRIGHT, fontSize: 10 }}>RISK INSPECTION</div>
            {["POSITION SIZE", "LIQUIDITY", "CORRELATION", "TAIL RISK", "LIVE CAPITAL LOCK"].map((item) => <div key={item} style={{ marginTop: 5, color: safetyHold ? GREEN : "#8b7653", fontFamily: "ui-monospace,monospace", fontSize: 7 }}>▣ {item}</div>)}
            <div style={{ marginTop: 9, display: "inline-block", border: `1px solid ${safetyHold ? GREEN : BRASS_DARK}`, color: safetyHold ? GREEN : "#9b8055", padding: "3px 7px", transform: "rotate(-2deg)", fontSize: 9 }}>{safetyHold ? "PROTECTED" : "UNKNOWN"}</div>
          </div>

          <div style={ornamentedPanel({ padding: 10 })}>
            <div style={{ color: BRASS_BRIGHT, fontSize: 10 }}>PAPER EXECUTION</div>
            <div style={{ color: "#88704d", marginTop: 7, fontSize: 7, lineHeight: 1.5 }}>WE TEST. WE LEARN. WE IMPROVE.</div>
            <div style={{ fontFamily: "ui-monospace,monospace", color: metricTone(paperReturn, true), marginTop: 12, fontSize: 17 }}>{paperReturn == null ? "UNKNOWN" : `${paperReturn.toFixed(2)}%`}</div>
            <div style={{ color: telemetry.system?.paper_mode ? BRASS_BRIGHT : RED, marginTop: 5, fontSize: 9 }}>PAPER ONLY · {telemetry.system?.paper_mode ? "LOCKED" : "CHECK MODE"}</div>
          </div>

          <div style={{ ...ornamentedPanel({ padding: 10 }), borderColor: "#45245c" }}>
            <div style={{ color: PURPLE, fontSize: 10 }}>GRAVEYARD</div>
            <div style={{ marginTop: 8, color: "#83705c", fontSize: 7, lineHeight: 1.45 }}>BAD IDEAS.<br />RIP.</div>
            <div style={{ marginTop: 10, color: "#604d37", fontSize: 7 }}>Future: rejected-case archive from real decision history.</div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.55fr) minmax(280px,.75fr)", gap: 6, padding: "0 8px 8px" }}>
          <div style={{ ...ornamentedPanel({ minHeight: 170, padding: 12 }), background: "radial-gradient(circle at 50% 115%,rgba(139,86,33,.22),#060503 57%)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ color: BRASS_BRIGHT, fontSize: 13, letterSpacing: 2 }}>THE OPERATING FLOOR</div>
                <div style={{ color: "#7f6949", fontSize: 8, marginTop: 4 }}>LIVE TELEMETRY DRIVES THE LIGHTS. THE ART DOESN'T GET A VOTE.</div>
              </div>
              <div style={{ color: telemetry.online ? GREEN : RED, fontFamily: "ui-monospace,monospace", fontSize: 8 }}>{telemetry.online ? "FLOOR OPEN" : "FLOOR DARK"}</div>
            </div>
            <div style={{ marginTop: 18, display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 8 }}>
              {["DATA INTAKE", "AGENT QUEUE", "COMMITTEE", "RISK GATE", "EXECUTION"].map((label, idx) => {
                const live = telemetry.online && (idx === 0 ? telemetry.recentEvents.length > 0 : idx === 1 ? activeCount > 0 : idx === 3 ? safetyHold : idx === 4 ? telemetry.system?.paper_mode === true : false);
                return <div key={label} style={{ border: `1px solid ${live ? "rgba(103,223,117,.4)" : BRASS_DARK}`, padding: 8, background: "rgba(2,3,2,.64)", textAlign: "center" }}><div style={{ color: "#9d8055", fontSize: 7 }}>{label}</div><div style={{ color: live ? GREEN : "#716046", fontFamily: "ui-monospace,monospace", fontSize: 8, marginTop: 5 }}>● {live ? "ACTIVE" : "IDLE / UNKNOWN"}</div></div>;
              })}
            </div>
            <div style={{ marginTop: 16, color: "#8a775a", fontSize: 8, lineHeight: 1.6 }}>LATEST EVENT: <span style={{ color: latestEvent ? "#b99d6a" : "#625543" }}>{latestEvent?.event_type || "NONE REPORTED"}</span></div>
          </div>

          <aside style={{ ...ornamentedPanel({ padding: 12 }), display: "grid", gridTemplateColumns: "92px 1fr", gap: 12, alignItems: "center" }}>
            <div style={{ width: 90, height: 108, position: "relative", border: `1px solid ${BRASS_DARK}`, background: "radial-gradient(circle at 50% 25%,rgba(151,102,51,.24),#080604 68%)" }}>
              <div style={{ position: "absolute", left: "50%", top: 14, transform: "translateX(-50%)", width: 55, height: 48, borderRadius: "48% 48% 42% 42%", background: "linear-gradient(180deg,#9c7958,#3b2c22)" }} />
              <div style={{ position: "absolute", left: "50%", bottom: -3, transform: "translateX(-50%)", width: 76, height: 64, borderRadius: "46% 46% 0 0", background: "linear-gradient(#4a392b,#0b0907)" }} />
              <div style={{ position: "absolute", bottom: 7, left: 23, right: 23, textAlign: "center", color: BRASS_BRIGHT, fontSize: 9, fontWeight: 900 }}>MAX</div>
            </div>
            <div>
              <div style={{ color: BRASS_BRIGHT, fontSize: 21, letterSpacing: 2 }}>MAX</div>
              <div style={{ color: "#9c7440", fontSize: 8, letterSpacing: 1 }}>CHIEF BULLSHIT OFFICER</div>
              <div style={{ marginTop: 10, color: "#c0a984", fontSize: 10, lineHeight: 1.45 }}>{maxMessage}</div>
              <div style={{ marginTop: 9, color: "#80613d", fontSize: 7 }}>MAX is not a fiduciary. MAX also does not create state.</div>
            </div>
          </aside>
        </div>

        <div style={{ margin: "0 8px 8px", padding: "7px 9px", border: `1px solid ${BRASS_DARK}`, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", fontFamily: "ui-monospace,monospace", fontSize: 7 }}>
          <span style={{ color: "#806a4a" }}>CAPITAL IS SACRED. EGO IS EXPENSIVE.</span>
          <span style={{ color: telemetry.online ? GREEN : RED }}>{telemetry.online ? "TELEMETRY LIVE" : "TELEMETRY OFFLINE"}</span>
          <span style={{ color: "#806a4a" }}>LAST POLL {telemetry.loadedAt ? new Date(telemetry.loadedAt).toLocaleTimeString() : "NEVER"}</span>
        </div>
      </div>
    </section>
  );
}

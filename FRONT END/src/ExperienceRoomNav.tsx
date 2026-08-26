import { useEffect, useMemo, useState } from "react";
import "./previewApiBridge";
import "./experienceShell.css";

type RoomKey = "factory" | "research" | "cases" | "capital" | "judgment";

type Room = {
  key: RoomKey;
  label: string;
  eyebrow: string;
  description: string;
};

const ROOMS: readonly Room[] = [
  { key: "factory", label: "Factory", eyebrow: "OPERATING HOME", description: "Command center, living floor, eight specialist desks, event lineage, and MAX." },
  { key: "research", label: "Research", eyebrow: "INTELLIGENCE INPUTS", description: "Opportunity discovery, evidence acquisition, institutional context, and governed research." },
  { key: "cases", label: "Cases", eyebrow: "UNDERWRITING", description: "Launch, surveillance, active thesis, re-underwrite history, and live case operations." },
  { key: "capital", label: "Capital", eyebrow: "CONTROL & RISK", description: "Risk inspection, paper execution, portfolio controls, sizing, and thesis integrity." },
  { key: "judgment", label: "Judgment", eyebrow: "HUMAN INTELLIGENCE", description: "Judgment Bank, calibration, interviews, and professional judgment capture." },
] as const;

const FACTORY_MARKERS = [
  "FACTORY BLUEPRINT + COMMAND CENTER",
  "X2 · LIVING FACTORY FLOOR",
  "BACKEND AUDIT → CANONICAL FACTORY EVENTS",
  "THE EIGHT AGENTS",
  "CHIEF BULLSHIT OFFICER",
];

const RESEARCH_MARKERS = [
  "OPPORTUNITY FLOOR",
  "AUTONOMOUS RESEARCH HUNT",
  "EVIDENCE GAP HUNTER",
  "HARD DATA ACQUISITION",
  "PRIMARY EVIDENCE ACQUISITION",
  "INSIDER & OWNERSHIP INTELLIGENCE",
  "INSTITUTIONAL EXPECTATIONS",
  "ANALYST CONSENSUS",
  "SHORT INTEREST",
  "OPTIONS POSITIONING",
  "JESSE INTELLIGENCE FLOOR",
  "INSTITUTIONAL SECTOR SENTIMENT",
  "MONETARY POLICY PROBABILITY",
  "PRODUCTION INPUT HEALTH",
  "DAILY DISLOCATION SCANNER",
];

const CASE_MARKERS = [
  "CASE LAUNCH BAY",
  "SURVEILLANCE FLOOR",
  "ACTIVE CASE",
  "LAST FACTORY PASS",
  "LIVE OPERATIONS FLOOR",
  "THE FACTORY ROOM",
  "RE-UNDERWRITE HISTORY",
  "SIGNAL LADDER",
];

const CAPITAL_MARKERS = [
  "CAPITAL CONTROL ROOM",
  "GOVERNED CAPITAL CHAIN",
  "PORTFOLIO CONTROL",
  "PAPER PORTFOLIO",
  "POSITION QUALIFICATION",
  "POSITION SIZING",
  "EXECUTION LOCK",
  "PAPER EXECUTION",
  "THESIS INTEGRITY",
];

const JUDGMENT_MARKERS = [
  "JUDGMENT BANK",
  "AGENT CALIBRATION BOARD",
  "PROFESSIONAL INTERVIEW PORTAL",
  "JUDGMENT CAPTURE",
  "CREATE INTERVIEW RECORD",
];

function normalizedText(node: Element): string {
  return String(node.textContent || "").replace(/\s+/g, " ").toUpperCase();
}

function hasMarker(text: string, markers: readonly string[]) {
  return markers.some((marker) => text.includes(marker));
}

function classify(node: HTMLElement): RoomKey | "always" | null {
  if (node.dataset.iiosShell === "experience-room-nav") return "always";
  if (node.tagName === "HEADER") return "always";

  const text = normalizedText(node);

  if (hasMarker(text, JUDGMENT_MARKERS)) return "judgment";
  if (hasMarker(text, CAPITAL_MARKERS)) return "capital";
  if (hasMarker(text, CASE_MARKERS)) return "cases";
  if (hasMarker(text, RESEARCH_MARKERS)) return "research";
  if (hasMarker(text, FACTORY_MARKERS)) return "factory";

  return null;
}

function stampRoomState(activeRoom: RoomKey) {
  const main = document.querySelector("main");
  if (!main) return;

  for (const child of Array.from(main.children) as HTMLElement[]) {
    const room = classify(child);
    child.dataset.iiosRoom = room ?? "legacy";

    if (room === "always") {
      child.dataset.iiosRoomVisible = "true";
    } else if (room === null) {
      child.dataset.iiosRoomVisible = activeRoom === "cases" ? "true" : "false";
    } else {
      child.dataset.iiosRoomVisible = room === activeRoom ? "true" : "false";
    }
  }
}

export default function ExperienceRoomNav() {
  const [activeRoom, setActiveRoom] = useState<RoomKey>("factory");
  const room = useMemo(() => ROOMS.find((item) => item.key === activeRoom) ?? ROOMS[0], [activeRoom]);

  useEffect(() => {
    stampRoomState(activeRoom);
    const timer = window.setInterval(() => stampRoomState(activeRoom), 750);
    return () => window.clearInterval(timer);
  }, [activeRoom]);

  const changeRoom = (key: RoomKey) => {
    setActiveRoom(key);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  };

  return (
    <section
      data-iios-shell="experience-room-nav"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 60,
        margin: "-8px 0 22px",
        padding: "12px 14px 14px",
        border: "1px solid rgba(164, 119, 48, .34)",
        borderRadius: "14px",
        background: "rgba(6, 8, 11, .94)",
        backdropFilter: "blur(18px)",
        boxShadow: "0 16px 50px rgba(0,0,0,.34)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "20px", flexWrap: "wrap" }}>
        <div style={{ minWidth: "260px" }}>
          <div style={{ color: "#aa8247", fontSize: "9px", fontWeight: 900, letterSpacing: "2.2px" }}>{room.eyebrow}</div>
          <div style={{ marginTop: "4px", color: "#d9dde2", fontSize: "12px" }}>{room.description}</div>
        </div>
        <nav style={{ display: "flex", gap: "7px", flexWrap: "wrap", justifyContent: "flex-end" }}>
          {ROOMS.map((item) => {
            const active = item.key === activeRoom;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => changeRoom(item.key)}
                style={{
                  appearance: "none",
                  border: active ? "1px solid #b28749" : "1px solid #2b323b",
                  borderRadius: "8px",
                  background: active ? "linear-gradient(180deg, rgba(119,78,28,.42), rgba(33,24,14,.82))" : "#0b0f14",
                  color: active ? "#f0d19a" : "#8e9aa7",
                  padding: "9px 14px",
                  fontSize: "10px",
                  fontWeight: 900,
                  letterSpacing: "1.25px",
                  textTransform: "uppercase",
                  cursor: "pointer",
                }}
              >
                {item.label}
              </button>
            );
          })}
        </nav>
      </div>
    </section>
  );
}

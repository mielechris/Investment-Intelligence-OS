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
  {
    key: "factory",
    label: "Factory",
    eyebrow: "OPERATING HOME",
    description: "Command center, living floor, eight specialist desks, event lineage, and MAX.",
  },
  {
    key: "research",
    label: "Research",
    eyebrow: "INTELLIGENCE INPUTS",
    description: "Opportunity discovery, production inputs, institutional context, and governed research.",
  },
  {
    key: "cases",
    label: "Cases",
    eyebrow: "UNDERWRITING",
    description: "Launch, surveillance, active thesis, re-underwrite, and live case operations.",
  },
  {
    key: "capital",
    label: "Capital",
    eyebrow: "CONTROL & RISK",
    description: "Risk inspection, paper execution, portfolio controls, and thesis integrity.",
  },
  {
    key: "judgment",
    label: "Judgment",
    eyebrow: "HUMAN INTELLIGENCE",
    description: "Judgment Bank, calibration, interviews, and professional judgment capture.",
  },
] as const;

const ALWAYS_VISIBLE = ["experience-room-nav"];

function normalizedText(node: Element): string {
  return String(node.textContent || "").replace(/\s+/g, " ").toUpperCase();
}

function classify(node: HTMLElement): RoomKey | "always" | null {
  if (ALWAYS_VISIBLE.some((value) => node.dataset.iiosShell === value)) return "always";
  if (node.tagName === "HEADER") return "always";

  const text = normalizedText(node);

  if (
    text.includes("FACTORY BLUEPRINT + COMMAND CENTER") ||
    text.includes("X2 · LIVING FACTORY FLOOR") ||
    text.includes("THE EIGHT AGENTS") ||
    text.includes("BACKEND AUDIT → CANONICAL FACTORY EVENTS") ||
    text.includes("THE OPERATING FLOOR") ||
    text.includes("CHIEF BULLSHIT OFFICER")
  ) return "factory";

  if (
    text.includes("OPPORTUNITY FLOOR") ||
    text.includes("AUTONOMOUS RESEARCH HUNT") ||
    text.includes("JESSE INTELLIGENCE FLOOR") ||
    text.includes("INSTITUTIONAL SECTOR SENTIMENT") ||
    text.includes("PRODUCTION INPUT HEALTH") ||
    text.includes("DAILY DISLOCATION SCANNER")
  ) return "research";

  if (
    text.includes("CASE LAUNCH BAY") ||
    text.includes("SURVEILLANCE FLOOR") ||
    text.includes("ACTIVE CASE") ||
    text.includes("LAST FACTORY PASS") ||
    text.includes("LIVE OPERATIONS FLOOR") ||
    text.includes("THE FACTORY ROOM")
  ) return "cases";

  if (
    text.includes("CAPITAL CONTROL ROOM") ||
    text.includes("GOVERNED CAPITAL CHAIN") ||
    text.includes("PAPER PORTFOLIO") ||
    text.includes("POSITION QUALIFICATION") ||
    text.includes("EXECUTION LOCK")
  ) return "capital";

  if (
    text.includes("JUDGMENT BANK") ||
    text.includes("AGENT CALIBRATION BOARD") ||
    text.includes("PROFESSIONAL INTERVIEW PORTAL") ||
    text.includes("JUDGMENT CAPTURE")
  ) return "judgment";

  return null;
}

function applyRoom(activeRoom: RoomKey) {
  const main = document.querySelector("main");
  if (!main) return;

  const children = Array.from(main.children) as HTMLElement[];
  for (const child of children) {
    const room = classify(child);
    if (room === "always") {
      child.style.removeProperty("display");
      continue;
    }

    if (room === null) {
      child.style.display = activeRoom === "cases" ? "" : "none";
      continue;
    }

    child.style.display = room === activeRoom ? "" : "none";
  }

  window.scrollTo({ top: 0, behavior: "smooth" });
}

export default function ExperienceRoomNav() {
  const [activeRoom, setActiveRoom] = useState<RoomKey>("factory");
  const room = useMemo(() => ROOMS.find((item) => item.key === activeRoom) ?? ROOMS[0], [activeRoom]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => applyRoom(activeRoom));
    return () => window.cancelAnimationFrame(frame);
  }, [activeRoom]);

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
                onClick={() => setActiveRoom(item.key)}
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

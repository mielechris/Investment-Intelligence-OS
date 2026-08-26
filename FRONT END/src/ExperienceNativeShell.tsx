import { useState } from "react";
import "./previewApiBridge";
import "./experienceShell.css";

import LegacyApp from "./App";
import OpportunityFloor from "./OpportunityFloor";
import PaperCapitalControlPanel from "./PaperCapitalControlPanel";
import DecisionHistoryPanel from "./DecisionHistoryPanel";
import EvidenceGapHunterPanel from "./EvidenceGapHunterPanel";
import HardDataPanel from "./HardDataPanel";
import InsiderOwnershipPanel from "./InsiderOwnershipPanel";
import InstitutionalIntelligencePanel from "./InstitutionalIntelligencePanel";
import CaseAwarePrimaryEvidencePanel from "./CaseAwarePrimaryEvidencePanel";
import ConsensusVerificationPanel from "./ConsensusVerificationPanel";
import ShortInterestVerificationPanel from "./ShortInterestVerificationPanel";
import OptionsPositioningVerificationPanel from "./OptionsPositioningVerificationPanel";
import PortfolioContextPanel from "./PortfolioContextPanel";
import InterviewPortalPanel from "./InterviewPortalPanel";
import JesseIntelligencePanel from "./JesseIntelligencePanel";
import ExperienceCommandCenter from "./ExperienceCommandCenter";
import LivingFactoryFloor from "./LivingFactoryFloor";
import SpecialistDeskFloor from "./SpecialistDeskFloor";
import FactoryEventRail from "./FactoryEventRail";
import FactoryRoom from "./FactoryRoom";

type RoomKey = "factory" | "research" | "cases" | "capital" | "judgment";

const ACTIVE_CASE_KEY = "iios.activeCaseId";

const ROOMS: Array<{ key: RoomKey; label: string; eyebrow: string; description: string }> = [
  { key: "factory", label: "Factory", eyebrow: "OPERATING HOME", description: "Live intelligence floor, eight specialist desks, case movement, and MAX." },
  { key: "research", label: "Research", eyebrow: "INTELLIGENCE INPUTS", description: "Discovery, hard data, institutional context, market structure, and external research." },
  { key: "cases", label: "Cases", eyebrow: "UNDERWRITING", description: "Case launch, surveillance, thesis history, evidence gaps, and re-underwrite workflow." },
  { key: "capital", label: "Capital", eyebrow: "CONTROL & RISK", description: "Portfolio overlap, deterministic risk, paper execution, and capital controls." },
  { key: "judgment", label: "Judgment", eyebrow: "HUMAN INTELLIGENCE", description: "Professional interviews, Judgment Bank capture, calibration, and governed human insight." },
];

const ROOM_COMMANDS: Record<RoomKey, Array<[string, string]>> = {
  factory: [["PRIMARY SURFACE", "OPERATIONS"], ["AUTHORITY", "OBSERVE / ROUTE"], ["EXECUTION", "PAPER ONLY"]],
  research: [["PRIMARY SURFACE", "EVIDENCE"], ["AUTHORITY", "RESEARCH ONLY"], ["OUTPUT", "GOVERNED INPUTS"]],
  cases: [["PRIMARY SURFACE", "UNDERWRITING"], ["AUTHORITY", "QUALIFY / REJECT"], ["OUTPUT", "CASE STATE"]],
  capital: [["PRIMARY SURFACE", "RISK & CAPITAL"], ["AUTHORITY", "SIZE / BLOCK"], ["EXECUTION", "PAPER ONLY"]],
  judgment: [["PRIMARY SURFACE", "HUMAN JUDGMENT"], ["AUTHORITY", "CAPTURE / CALIBRATE"], ["OUTPUT", "JUDGMENT BANK"]],
};

function RoomHeader({ room }: { room: (typeof ROOMS)[number] }) {
  return (
    <>
      <div className="native-room-header">
        <div>
          <div className="native-room-eyebrow">{room.eyebrow}</div>
          <h2>{room.label}</h2>
          <p>{room.description}</p>
        </div>
        <div className="native-room-mode">PAPER / SHADOW · LIVE CAPITAL LOCKED</div>
      </div>
      <div className="native-room-command-strip">
        {ROOM_COMMANDS[room.key].map(([label, value]) => (
          <div key={label} className="native-room-command-cell">
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </>
  );
}

function FactoryRoomView() {
  return (
    <>
      <SpecialistDeskFloor />
      <FactoryEventRail />
      <details className="native-drawer">
        <summary>Live Factory Map</summary>
        <div className="native-drawer-body"><LivingFactoryFloor /></div>
      </details>
      <details className="native-drawer">
        <summary>Operations Conveyor</summary>
        <div className="native-drawer-body"><FactoryRoom /></div>
      </details>
      <details className="native-drawer">
        <summary>System Architecture</summary>
        <div className="native-drawer-body"><ExperienceCommandCenter /></div>
      </details>
    </>
  );
}

function ResearchRoomView() {
  return (
    <>
      <OpportunityFloor />
      <JesseIntelligencePanel />
      <HardDataPanel />
      <InsiderOwnershipPanel />
      <InstitutionalIntelligencePanel />
      <ConsensusVerificationPanel />
      <ShortInterestVerificationPanel />
      <OptionsPositioningVerificationPanel />
    </>
  );
}

function CasesRoomView() {
  return (
    <>
      <div className="native-migration-note">
        <strong>UNDERWRITING WORKSPACE</strong>
        <span>Legacy case launch/surveillance is retained here while its inline sections are extracted into native room components.</span>
      </div>
      <LegacyApp />
      <DecisionHistoryPanel />
      <EvidenceGapHunterPanel />
      <CaseAwarePrimaryEvidencePanel />
    </>
  );
}

function CapitalRoomView() {
  const caseId = window.localStorage.getItem(ACTIVE_CASE_KEY);
  return (
    <>
      <PaperCapitalControlPanel caseId={caseId} />
      <PortfolioContextPanel />
    </>
  );
}

function JudgmentRoomView() {
  return (
    <>
      <InterviewPortalPanel />
      <div className="native-migration-note">
        <strong>JUDGMENT BANK EXPERIENCE</strong>
        <span>Scorecards, calibration history, interview library, and governed judgment navigation are the next native extraction.</span>
      </div>
    </>
  );
}

export default function ExperienceNativeShell() {
  const [activeRoom, setActiveRoom] = useState<RoomKey>("factory");
  const room = ROOMS.find((item) => item.key === activeRoom) ?? ROOMS[0];

  return (
    <main className="native-experience-shell">
      <header className="native-masthead">
        <div>
          <div className="native-kicker">INVESTMENT INTELLIGENCE OS</div>
          <h1>THE INTELLIGENCE FACTORY</h1>
          <p>Evidence → 8 desks → Committee → Risk → Monitor → Judgment Bank</p>
        </div>
        <div className="native-masthead-status">
          <span>SYSTEM EXPERIENCE</span>
          <strong>X0–X3 PREVIEW</strong>
          <em>PAPER / SHADOW</em>
        </div>
      </header>

      <nav className="native-room-nav" aria-label="IIOS rooms">
        {ROOMS.map((item) => (
          <button
            type="button"
            key={item.key}
            className={item.key === activeRoom ? "active" : ""}
            onClick={() => {
              setActiveRoom(item.key);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <section className={`native-room native-room--${activeRoom}`}>
        <RoomHeader room={room} />
        {activeRoom === "factory" && <FactoryRoomView />}
        {activeRoom === "research" && <ResearchRoomView />}
        {activeRoom === "cases" && <CasesRoomView />}
        {activeRoom === "capital" && <CapitalRoomView />}
        {activeRoom === "judgment" && <JudgmentRoomView />}
      </section>
    </main>
  );
}

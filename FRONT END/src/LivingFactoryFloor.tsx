import { useEffect, useMemo, useState } from "react";
import { FACTORY_FLOOR_GEOMETRY, FACTORY_ROUTES, getFactoryZoneCenter } from "./factoryGeometry";
import type { FactoryZoneKey } from "./factoryGeometry";
import { visualStateFor } from "./factoryVisualLanguage";

const API = "http://127.0.0.1:8002";
const POLL_MS = 5000;

type RuntimeRoom = {
  key: string;
  label: string;
  count: number;
  activity_count?: number;
};

type RuntimeCase = {
  case_id: string;
  stage?: string;
  active_room?: string | null;
  live_execution?: boolean;
};

type FactorySnapshot = {
  generated_at?: string;
  rooms?: RuntimeRoom[];
  cases?: RuntimeCase[];
};

type FloorTelemetry = {
  snapshot: FactorySnapshot | null;
  online: boolean;
  error: string | null;
  loadedAt: string | null;
};

const ROOM_ALIASES: Record<string, FactoryZoneKey> = {
  "evidence-warehouse": "evidence-warehouse",
  "evidence warehouse": "evidence-warehouse",
  "evidence acquisition": "evidence-warehouse",
  evidence: "evidence-warehouse",
  "agent-desks": "agent-desks",
  "agent desks": "agent-desks",
  "specialist desks": "agent-desks",
  "8 specialist desks": "agent-desks",
  "eight specialist desks": "agent-desks",
  "eight desks": "agent-desks",
  agents: "agent-desks",
  "research-annex": "research-annex",
  "research annex": "research-annex",
  research: "research-annex",
  "committee-room": "committee-room",
  "committee room": "committee-room",
  committee: "committee-room",
  "investment committee": "committee-room",
  "skeptic-room": "skeptic-room",
  "skeptic room": "skeptic-room",
  "red room": "skeptic-room",
  skeptic: "skeptic-room",
  "risk-inspection": "risk-inspection",
  "risk inspection": "risk-inspection",
  risk: "risk-inspection",
  "paper-execution": "paper-execution",
  "paper execution": "paper-execution",
  "paper execution bay": "paper-execution",
  paper: "paper-execution",
  capital: "paper-execution",
  qualified: "paper-execution",
  "position sizing": "paper-execution",
  authorization: "paper-execution",
  "portfolio-office": "portfolio-office",
  "portfolio office": "portfolio-office",
  "paper portfolio": "portfolio-office",
  portfolio: "portfolio-office",
  "thesis-integrity": "thesis-integrity",
  "thesis integrity": "thesis-integrity",
  thesis: "thesis-integrity",
  "judgment-bank": "judgment-bank",
  "judgment bank": "judgment-bank",
  "control-room": "control-room",
  "control room": "control-room",
  control: "control-room",
};

const ROOM_LABELS: Record<FactoryZoneKey, string> = {
  "intelligence-floor": "INTELLIGENCE FLOOR",
  "evidence-warehouse": "EVIDENCE WAREHOUSE",
  "agent-desks": "EIGHT SPECIALIST DESKS",
  "research-annex": "RESEARCH ANNEX · GROK / KIMI",
  "committee-room": "INVESTMENT COMMITTEE",
  "skeptic-room": "SKEPTIC / RED ROOM",
  "risk-inspection": "RISK INSPECTION",
  "paper-execution": "PAPER EXECUTION BAY",
  "portfolio-office": "PORTFOLIO OFFICE",
  "thesis-integrity": "THESIS INTEGRITY",
  "judgment-bank": "JUDGMENT BANK",
  "control-room": "CONTROL ROOM",
};

function normalizeRoom(value: string | null | undefined): FactoryZoneKey | null {
  const normalized = String(value || "").toLowerCase().replace(/[_/]+/g, " ").replace(/\s+/g, " ").trim();
  return ROOM_ALIASES[normalized] ?? null;
}

async function fetchSnapshot(): Promise<FactorySnapshot> {
  const response = await fetch(`${API}/factory-room/status`);
  if (!response.ok) throw new Error(`/factory-room/status HTTP ${response.status}`);
  return response.json() as Promise<FactorySnapshot>;
}

function roomRuntime(zoneKey: FactoryZoneKey, rooms: RuntimeRoom[] | undefined) {
  return rooms?.find((room) => normalizeRoom(room.key) === zoneKey || normalizeRoom(room.label) === zoneKey) ?? null;
}

export default function LivingFactoryFloor() {
  const [telemetry, setTelemetry] = useState<FloorTelemetry>({
    snapshot: null,
    online: false,
    error: null,
    loadedAt: null,
  });

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const snapshot = await fetchSnapshot();
        if (!active) return;
        setTelemetry({ snapshot, online: true, error: null, loadedAt: new Date().toISOString() });
      } catch (error) {
        if (!active) return;
        setTelemetry((current) => ({
          ...current,
          online: false,
          error: error instanceof Error ? error.message : "Factory snapshot request failed",
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

  const placements = useMemo(
    () => (telemetry.snapshot?.cases || []).map((item, index) => {
      const auditZone = normalizeRoom(item.active_room);
      const stageZone = normalizeRoom(item.stage);
      return {
        item,
        index,
        zoneKey: auditZone ?? stageZone,
        placementSource: auditZone ? "AUDIT" as const : stageZone ? "STAGE" as const : "UNPLACED" as const,
      };
    }),
    [telemetry.snapshot?.cases]
  );

  const placedCases = useMemo(
    () => placements.filter((entry) => entry.zoneKey !== null),
    [placements]
  );

  const unplacedCases = useMemo(
    () => placements.filter((entry) => entry.zoneKey === null),
    [placements]
  );

  const caseOffsets = useMemo(() => {
    const offsets = new Map<string, number>();
    const counts = new Map<FactoryZoneKey, number>();
    for (const entry of placedCases) {
      if (!entry.zoneKey) continue;
      const next = counts.get(entry.zoneKey) ?? 0;
      offsets.set(entry.item.case_id, next);
      counts.set(entry.zoneKey, next + 1);
    }
    return offsets;
  }, [placedCases]);

  return (
    <section
      style={{
        marginBottom: "22px",
        padding: "20px",
        border: "1px solid rgba(103, 143, 182, .28)",
        borderRadius: "17px",
        background: "linear-gradient(180deg, rgba(7,11,17,.98), rgba(3,6,10,.98))",
        boxShadow: "0 26px 80px rgba(0,0,0,.36)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: "18px", alignItems: "flex-start", flexWrap: "wrap" }}>
        <div>
          <div style={{ color: "#6e88a1", fontSize: "9px", letterSpacing: "2.4px", fontWeight: 900 }}>X2 · LIVING FACTORY FLOOR</div>
          <h2 style={{ margin: "6px 0", fontSize: "25px" }}>REAL STATE. REAL ROOMS. NO FAKE MOTION.</h2>
          <div style={{ color: "#7e8d9d", fontSize: "11px", lineHeight: 1.5, maxWidth: "760px" }}>
            Recent audit events drive animated placement. When a case has no recent event, its backend-declared stage provides a static location only; stage placement never implies live movement.
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ color: telemetry.online ? "#63e6a5" : "#ff6d7c", fontSize: "10px", letterSpacing: "1.8px", fontWeight: 900 }}>
            {telemetry.online ? "SNAPSHOT LIVE" : "SNAPSHOT OFFLINE / STALE"}
          </div>
          <div style={{ color: "#65778a", marginTop: "5px", fontSize: "9px" }}>
            Poll {POLL_MS / 1000}s · {telemetry.loadedAt ? new Date(telemetry.loadedAt).toLocaleTimeString() : "never loaded"}
          </div>
          {telemetry.error && <div style={{ color: "#ff8a96", marginTop: "5px", maxWidth: "380px", fontSize: "9px" }}>{telemetry.error}</div>}
        </div>
      </div>

      <div
        style={{
          position: "relative",
          width: "100%",
          aspectRatio: "16 / 9",
          minHeight: "560px",
          marginTop: "16px",
          overflow: "hidden",
          borderRadius: "14px",
          border: "1px solid rgba(91, 126, 159, .24)",
          background: "radial-gradient(circle at 48% 35%, rgba(28,55,78,.27), rgba(4,7,11,.96) 58%)",
        }}
      >
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
          {FACTORY_ROUTES.map((route) => {
            const from = getFactoryZoneCenter(route.from);
            const to = getFactoryZoneCenter(route.to);
            return (
              <line
                key={route.key}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                vectorEffect="non-scaling-stroke"
                stroke={route.kind === "PRIMARY" ? "rgba(93,230,173,.32)" : route.kind === "CHALLENGE" ? "rgba(255,108,125,.27)" : "rgba(104,142,178,.20)"}
                strokeWidth={route.kind === "PRIMARY" ? 1.8 : 1.2}
                strokeDasharray={route.kind === "PRIMARY" ? undefined : "5 5"}
              />
            );
          })}
        </svg>

        {(Object.keys(FACTORY_FLOOR_GEOMETRY) as FactoryZoneKey[]).filter((zoneKey) => zoneKey !== "intelligence-floor").map((zoneKey) => {
          const rect = FACTORY_FLOOR_GEOMETRY[zoneKey];
          const runtime = roomRuntime(zoneKey, telemetry.snapshot?.rooms);
          const active = telemetry.online && ((runtime?.activity_count ?? 0) > 0 || placedCases.some((entry) => entry.zoneKey === zoneKey));
          return (
            <div
              key={zoneKey}
              style={{
                position: "absolute",
                left: `${rect.x}%`,
                top: `${rect.y}%`,
                width: `${rect.width}%`,
                height: `${rect.height}%`,
                boxSizing: "border-box",
                padding: "9px",
                borderRadius: "9px",
                border: active ? "1px solid rgba(99,230,165,.50)" : "1px solid rgba(74,101,128,.34)",
                background: active ? "rgba(8,34,28,.69)" : "rgba(8,14,20,.76)",
                boxShadow: active ? "0 0 24px rgba(83,224,166,.12)" : "none",
                transition: "border-color .3s ease, background .3s ease, box-shadow .3s ease",
              }}
            >
              <div style={{ color: active ? "#cffff0" : "#8191a1", fontSize: "8px", fontWeight: 900, letterSpacing: ".8px" }}>{ROOM_LABELS[zoneKey]}</div>
              <div style={{ color: "#566a7d", fontSize: "8px", marginTop: "5px" }}>
                {runtime ? `${runtime.count ?? 0} reported · ${runtime.activity_count ?? 0} recent` : "NO ROOM TELEMETRY"}
              </div>
            </div>
          );
        })}

        {placedCases.map((entry) => {
          if (!entry.zoneKey) return null;
          const center = getFactoryZoneCenter(entry.zoneKey);
          const offset = caseOffsets.get(entry.item.case_id) ?? 0;
          const visual = visualStateFor(telemetry.online ? "ACTIVE" : "OFFLINE");
          const auditPlacement = entry.placementSource === "AUDIT";
          return (
            <div
              key={entry.item.case_id}
              title={`${entry.item.case_id} · ${entry.item.stage ?? "stage unknown"} · ${auditPlacement ? `recent audit room ${entry.item.active_room}` : "static backend stage placement"}`}
              style={{
                position: "absolute",
                left: `${center.x + Math.min(offset, 3) * 1.25}%`,
                top: `${center.y + Math.floor(offset / 4) * 3.1}%`,
                transform: "translate(-50%, -50%)",
                maxWidth: "150px",
                padding: "5px 7px",
                borderRadius: "999px",
                border: auditPlacement && visual.signal === "NEON_ACTIVE" ? "1px solid rgba(99,230,165,.82)" : "1px solid rgba(119,145,170,.55)",
                background: "rgba(4,8,12,.94)",
                color: auditPlacement ? "#dffff0" : "#a7b4c1",
                fontSize: "7px",
                fontWeight: 900,
                letterSpacing: ".5px",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                zIndex: 4,
                opacity: auditPlacement ? 1 : .78,
                transition: auditPlacement ? "left .55s ease, top .55s ease" : "none",
                boxShadow: auditPlacement ? "0 0 16px rgba(99,230,165,.22)" : "none",
              }}
            >
              {entry.item.case_id}
            </div>
          );
        })}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(260px, .36fr)", gap: "12px", marginTop: "12px" }}>
        <div style={{ color: "#65798d", fontSize: "9px", lineHeight: 1.55 }}>
          SOURCE CONTRACT: `active_room` is authoritative for recent motion; `stage` is authoritative only for static fallback placement. No price, sentiment, timing, or inferred workflow state is used.
        </div>
        <div style={{ borderLeft: "2px solid #34495b", paddingLeft: "10px" }}>
          <div style={{ color: "#6c8298", fontSize: "8px", letterSpacing: "1.2px", fontWeight: 900 }}>UNPLACED CASES</div>
          <div style={{ color: unplacedCases.length ? "#e8c96b" : "#67798b", fontSize: "10px", marginTop: "4px", fontWeight: 800 }}>
            {unplacedCases.length ? `${unplacedCases.length} · UNKNOWN / UNMAPPED STAGE` : "0"}
          </div>
        </div>
      </div>
    </section>
  );
}

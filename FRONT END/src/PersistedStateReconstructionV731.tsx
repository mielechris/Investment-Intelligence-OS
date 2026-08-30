import { useEffect, useMemo, useState } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { LIVING_CAST, type LivingCastKey } from "./livingCast";
import { mobReactionLine } from "./mobVoice";
import "./PersistedStateReconstructionV731.css";

type JsonObject = Record<string, unknown>;
type View = "floor" | "control";
type RoomKey = "commission" | "risk" | "paper" | "monitoring" | "learning";
type ReconstructionKind = "committee" | "risk" | "paper" | "monitoring" | "outcome";

type ValidationLayer = {
  availability?: string;
  payload?: JsonObject | null;
};

type LivingOverview = {
  validation?: {
    layers?: {
      factory_telemetry?: ValidationLayer;
      outcome_learning?: ValidationLayer;
    };
  };
  safety?: {
    backend_write_permission?: boolean;
    trade_execution_permission?: boolean;
    live_execution?: boolean;
  };
};

type Promotion = {
  case_id?: string | null;
  ticker?: string | null;
  created_at?: string | null;
  agents?: { agent_keys?: string[] | null } | null;
  committee?: { disposition?: string | null; confidence?: number | null } | null;
  risk?: { decision?: string | null } | null;
  paper_execution?: { execution?: string | null; notional?: number | null } | null;
  monitoring?: { status?: string | null; state?: string | null; thesis_state?: string | null } | null;
  monitoring_state?: string | null;
  thesis_state?: string | null;
};

type Scene = {
  id: string;
  kind: ReconstructionKind;
  room: RoomKey;
  ticker: string;
  caseId: string;
  persistedValue: string;
  secondaryValue?: string;
  sourceLabel: string;
  cast: LivingCastKey[];
  eventType: string;
};

const ROOM_LABEL: Record<RoomKey, string> = {
  commission: "The Commission",
  risk: "Risk Inspection",
  paper: "Paper Bay",
  monitoring: "Monitoring Office",
  learning: "The Confessional",
};

const ROOM_CAST: Record<RoomKey, LivingCastKey[]> = {
  commission: ["max", "fundamentals", "skeptic", "portfolio"],
  risk: ["max", "portfolio", "skeptic", "fundamentals"],
  paper: ["max", "portfolio", "market_structure"],
  monitoring: ["max", "market_structure", "portfolio", "skeptic"],
  learning: ["max", "fundamentals", "skeptic", "portfolio"],
};

function record(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function rows(value: unknown): JsonObject[] {
  return Array.isArray(value)
    ? value.filter((item): item is JsonObject => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function text(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

function meaningful(value: unknown): string {
  const out = text(value, "").trim();
  if (!out) return "";
  const normalized = out.toUpperCase().replaceAll("_", " ");
  if (["NONE", "UNKNOWN", "UNREPORTED", "WAITING", "PENDING", "N/A", "NULL"].includes(normalized)) return "";
  return normalized;
}

function pct(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  const number = Math.abs(value) <= 1 ? value * 100 : value;
  return `${number.toFixed(0)}%`;
}

function isCastKey(value: string): value is LivingCastKey {
  return Object.prototype.hasOwnProperty.call(LIVING_CAST, value);
}

function persistedCast(promotion: Promotion): LivingCastKey[] {
  const raw = promotion.agents?.agent_keys;
  if (!Array.isArray(raw)) return [];
  return raw.map(String).filter((key): key is LivingCastKey => isCastKey(key) && key !== "max");
}

function sceneCast(room: RoomKey, promotion?: Promotion): LivingCastKey[] {
  const observed = promotion ? persistedCast(promotion) : [];
  return Array.from(new Set<LivingCastKey>([...ROOM_CAST[room], ...observed])).slice(0, 5);
}

function promotionScenes(promotions: Promotion[]): Scene[] {
  const scenes: Scene[] = [];
  for (const promotion of promotions) {
    const ticker = text(promotion.ticker, "NO TICKER").toUpperCase();
    const caseId = text(promotion.case_id, "NO CASE");
    const committee = meaningful(promotion.committee?.disposition);
    const confidence = pct(promotion.committee?.confidence);
    if (committee) {
      scenes.push({
        id: `committee:${caseId}:${committee}`,
        kind: "committee",
        room: "commission",
        ticker,
        caseId,
        persistedValue: committee,
        secondaryValue: confidence || undefined,
        sourceLabel: "PERSISTED COMMITTEE DISPOSITION",
        cast: sceneCast("commission", promotion),
        eventType: "COMMITTEE_DECISION_STATE_RECONSTRUCTION",
      });
    }

    const risk = meaningful(promotion.risk?.decision);
    if (risk) {
      scenes.push({
        id: `risk:${caseId}:${risk}`,
        kind: "risk",
        room: "risk",
        ticker,
        caseId,
        persistedValue: risk,
        sourceLabel: "PERSISTED RISK DECISION",
        cast: sceneCast("risk", promotion),
        eventType: "RISK_DECISION_STATE_RECONSTRUCTION",
      });
    }

    const paper = meaningful(promotion.paper_execution?.execution);
    if (paper) {
      scenes.push({
        id: `paper:${caseId}:${paper}`,
        kind: "paper",
        room: "paper",
        ticker,
        caseId,
        persistedValue: paper,
        secondaryValue: typeof promotion.paper_execution?.notional === "number" ? `$${promotion.paper_execution.notional.toLocaleString()}` : undefined,
        sourceLabel: "PERSISTED PAPER EXECUTION STATE",
        cast: sceneCast("paper", promotion),
        eventType: "PAPER_EXECUTION_STATE_RECONSTRUCTION",
      });
    }

    const monitor = meaningful(
      promotion.monitoring?.status ??
      promotion.monitoring?.state ??
      promotion.monitoring?.thesis_state ??
      promotion.monitoring_state ??
      promotion.thesis_state,
    );
    if (monitor) {
      scenes.push({
        id: `monitor:${caseId}:${monitor}`,
        kind: "monitoring",
        room: "monitoring",
        ticker,
        caseId,
        persistedValue: monitor,
        sourceLabel: "PERSISTED MONITORING / THESIS STATE",
        cast: sceneCast("monitoring", promotion),
        eventType: "MONITORING_STATE_RECONSTRUCTION",
      });
    }
  }
  return scenes;
}

function outcomeScenes(outcomePayload: JsonObject): Scene[] {
  const scenes: Scene[] = [];
  for (const raw of rows(outcomePayload.recent_outcomes).slice(0, 12)) {
    const ticker = text(raw.ticker, "NO TICKER").toUpperCase();
    const caseId = text(raw.case_id, text(raw.source_case_id, "NO CASE"));
    const label = meaningful(raw.decision_quality_label ?? raw.market_outcome_label ?? raw.status);
    if (!label) continue;
    const return5d = typeof raw.return_5d_pct === "number" ? `${raw.return_5d_pct.toFixed(1)}% 5D` : undefined;
    scenes.push({
      id: `outcome:${caseId}:${ticker}:${label}`,
      kind: "outcome",
      room: "learning",
      ticker,
      caseId,
      persistedValue: label,
      secondaryValue: return5d,
      sourceLabel: "PERSISTED 9J OUTCOME LABEL",
      cast: ROOM_CAST.learning,
      eventType: "OUTCOME_LEARNING_STATE_RECONSTRUCTION",
    });
  }
  return scenes;
}

function directorLine(key: LivingCastKey, scene: Scene): string {
  const context = {
    eventType: scene.eventType,
    ticker: scene.ticker,
    disposition: scene.kind === "committee" ? scene.persistedValue : undefined,
    confidence: scene.kind === "committee" ? scene.secondaryValue : undefined,
    riskDecision: scene.kind === "risk" ? scene.persistedValue : undefined,
    paperState: scene.kind === "paper" ? scene.persistedValue : undefined,
  };
  if (key === "max") {
    if (scene.kind === "committee") return `${scene.ticker} already has a persisted Commission disposition: ${scene.persistedValue}. We are reconstructing the room from the receipt, not inventing a meeting.`;
    if (scene.kind === "risk") return `${scene.ticker} already has a persisted Risk decision: ${scene.persistedValue}. Nobody calls this live; we're reopening the file, capisce?`;
    if (scene.kind === "paper") return `${scene.ticker} has persisted paper state ${scene.persistedValue}. Fake money, real receipt, zero new authority.`;
    if (scene.kind === "monitoring") return `${scene.ticker} has persisted monitoring state ${scene.persistedValue}. We're reconstructing the watch, not manufacturing a heartbeat.`;
    return `${scene.ticker} has a persisted outcome label: ${scene.persistedValue}. Welcome to the Confessional. The receipt gets the last word.`;
  }
  return mobReactionLine(key, context);
}

async function loadOverview(signal: AbortSignal): Promise<LivingOverview> {
  const response = await fetch("/living/overview", {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`V7.3 state reconstruction source unavailable: HTTP ${response.status}`);
  return response.json() as Promise<LivingOverview>;
}

export default function PersistedStateReconstructionV731({ view }: { view: View }) {
  const [snapshot, setSnapshot] = useState<LivingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [beatIndex, setBeatIndex] = useState(0);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    const refresh = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await loadOverview(controller.signal);
        if (disposed) return;
        setSnapshot(next);
        setError(null);
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "V7.3 state reconstruction source unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5_000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, []);

  const model = useMemo(() => {
    const telemetry = record(snapshot?.validation?.layers?.factory_telemetry?.payload);
    const promotions = rows(telemetry.recent_promotions) as Promotion[];
    const outcome = record(snapshot?.validation?.layers?.outcome_learning?.payload);
    const scenes = [...promotionScenes(promotions), ...outcomeScenes(outcome)];
    const safeIndex = scenes.length ? Math.min(selectedIndex, scenes.length - 1) : 0;
    const scene = scenes[safeIndex] ?? null;
    return { scenes, safeIndex, scene };
  }, [snapshot, selectedIndex]);

  useEffect(() => {
    if (selectedIndex !== model.safeIndex) setSelectedIndex(model.safeIndex);
    setBeatIndex(0);
  }, [model.safeIndex, selectedIndex, model.scene?.id]);

  const scene = model.scene;
  const safety = snapshot?.safety ?? {};
  const activeSpeaker = scene ? scene.cast[Math.min(beatIndex, scene.cast.length - 1)] : null;

  const older = () => {
    if (!model.scenes.length) return;
    setSelectedIndex((value) => (value + 1) % model.scenes.length);
  };
  const newer = () => {
    if (!model.scenes.length) return;
    setSelectedIndex((value) => (value - 1 + model.scenes.length) % model.scenes.length);
  };
  const nextBeat = () => {
    if (!scene) return;
    setBeatIndex((value) => (value + 1) % scene.cast.length);
  };

  return (
    <section className={`psr731-shell psr731-shell--${view}`} aria-label="V7.3 persisted state reconstruction">
      <header className="psr731-header">
        <div>
          <span>V7.3.1 · PERSISTED STATE RECONSTRUCTION</span>
          <h2>NO EVENT RECEIPT? FINE. SHOW ME THE FUCKIN' STATE THAT ACTUALLY EXISTS.</h2>
          <p>Committee, Risk, Paper, Monitoring and 9J rooms only appear when their persisted fields exist. This reconstructs a historical room from stored state; it never manufactures an event, meeting, approval or trade.</p>
        </div>
        <div className="psr731-stamp"><strong>STATE RECONSTRUCTION</strong><span>NOT A LIVE EVENT · NOT RAW MODEL SPEECH</span></div>
      </header>

      <div className="psr731-truth">
        <span>SOURCE · PERSISTED CASE / 9J STATE ONLY</span>
        <span>MISSING FIELD · NO SCENE</span>
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>TRADE AUTHORITY · {safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
        <span>WRITE AUTHORITY · {safety.backend_write_permission ? "TRUE" : "NONE"}</span>
      </div>

      <div className="psr731-controls">
        <button type="button" onClick={older} disabled={!model.scenes.length}>← OLDER STATE</button>
        <div>
          <span>STATE {model.scenes.length ? model.safeIndex + 1 : 0} OF {model.scenes.length}</span>
          <strong>{scene ? `${ROOM_LABEL[scene.room]} · ${scene.ticker}` : "NO ELIGIBLE PERSISTED STATE"}</strong>
          <small>{scene ? `${scene.sourceLabel} · ${scene.persistedValue}${scene.secondaryValue ? ` · ${scene.secondaryValue}` : ""}` : "Committee/Risk/Paper/Monitoring/9J fields have not produced an eligible reconstruction yet."}</small>
        </div>
        <button className="psr731-nextbeat" type="button" onClick={nextBeat} disabled={!scene}>NEXT FAMILY BEAT →</button>
        <button type="button" onClick={newer} disabled={!model.scenes.length}>NEWER STATE →</button>
      </div>

      {scene ? (
        <div className={`psr731-stage is-${scene.room}`}>
          <aside className="psr731-receipt">
            <span>PERSISTED STATE RECEIPT</span>
            <strong>{scene.sourceLabel}</strong>
            <dl>
              <div><dt>TICKER</dt><dd>{scene.ticker}</dd></div>
              <div><dt>CASE</dt><dd>{scene.caseId}</dd></div>
              <div><dt>ROOM</dt><dd>{ROOM_LABEL[scene.room]}</dd></div>
              <div><dt>STATE</dt><dd>{scene.persistedValue}</dd></div>
              {scene.secondaryValue ? <div><dt>DETAIL</dt><dd>{scene.secondaryValue}</dd></div> : null}
            </dl>
            <footer>RECONSTRUCTION BASIS · {scene.sourceLabel}</footer>
          </aside>

          <section className="psr731-family">
            <header><span>{ROOM_LABEL[scene.room].toUpperCase()}</span><strong>HISTORICAL STATE RECONSTRUCTION</strong></header>
            <div className="psr731-cast">
              {scene.cast.map((key, index) => {
                const active = key === activeSpeaker;
                return (
                  <article key={`${scene.id}:${key}`} className={`${active ? "is-speaking" : "is-reacting"} ${key === "skeptic" ? "is-red" : ""}`}>
                    <div className="psr731-avatar">
                      <CinematicCharacterPortrait characterKey={key} active={active} reacting={active} variant={key === "max" ? "boss" : "scene"} showLabel={false} />
                    </div>
                    <strong>{LIVING_CAST[key].displayName}</strong>
                    <span>{LIVING_CAST[key].title}</span>
                    {active ? <blockquote>“{directorLine(key, scene)}”</blockquote> : <small>{index < beatIndex ? "BEAT COMPLETE" : "WAITING TO SPEAK"}</small>}
                  </article>
                );
              })}
            </div>
            <footer>THE DIALOGUE IS PRESENTATION-ONLY. THE PERSISTED STATE ABOVE IS THE AUTHORITATIVE RECEIPT.</footer>
          </section>
        </div>
      ) : (
        <div className="psr731-empty">
          <strong>NO ELIGIBLE PERSISTED STATE → NO RECONSTRUCTION</strong>
          <span>We do not invent a Committee meeting, Risk decision, paper execution, monitoring state or 9J outcome just to make the room look busy.</span>
        </div>
      )}

      {error ? <div className="psr731-error">READ-ONLY SOURCE WARNING · {error}</div> : null}
    </section>
  );
}

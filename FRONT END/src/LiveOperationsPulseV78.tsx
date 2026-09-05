import { useEffect, useMemo, useState } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import "./LiveOperationsPulseV78.css";

type JsonObject = Record<string, unknown>;
type Props = { view: "floor" | "control" };

type Worker = {
  key: "radar" | "observation" | "paper";
  code: "9E" | "9A" | "9B";
  label: string;
  room: string;
  raw: JsonObject;
  cast: Array<"max" | "market_structure" | "skeptic" | "portfolio">;
};

function record(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function text(value: unknown, fallback = "—"): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseTime(value: unknown): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function secondsSince(value: unknown, now: number): number | null {
  const parsed = parseTime(value);
  return parsed === null ? null : Math.max(0, Math.floor((now - parsed) / 1000));
}

function ageLabel(value: number | null): string {
  if (value === null) return "NO CHECKPOINT";
  if (value < 60) return `${value}s AGO`;
  if (value < 3600) return `${Math.floor(value / 60)}m ${value % 60}s AGO`;
  return `${Math.floor(value / 3600)}h AGO`;
}

function countdown(value: unknown, now: number): string {
  const parsed = parseTime(value);
  if (parsed === null) return "NEXT DUE UNKNOWN";
  const seconds = Math.floor((parsed - now) / 1000);
  if (seconds <= 0) return `${Math.abs(seconds)}s PAST DUE`;
  if (seconds < 60) return `DUE IN ${seconds}s`;
  return `DUE IN ${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function state(raw: JsonObject): string {
  return text(raw.cadence_state, "UNKNOWN").replaceAll("_", " ").toUpperCase();
}

export default function LiveOperationsPulseV78({ view }: Props) {
  const [overview, setOverview] = useState<JsonObject | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;

    const refresh = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const response = await fetch("/living/overview", {
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const next = (await response.json()) as JsonObject;
        if (!disposed) {
          setOverview(next);
          setError(null);
        }
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "overview unavailable");
      }
    };

    void refresh();
    const poll = window.setInterval(() => void refresh(), 5000);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(poll);
      window.clearInterval(clock);
    };
  }, []);

  const model = useMemo(() => {
    const validation = record(overview?.validation);
    const layers = record(validation.layers);
    const telemetryLayer = record(layers.factory_telemetry);
    const telemetry = record(telemetryLayer.payload);
    const cadence = record(telemetry.cadence);
    const safety = record(overview?.safety);

    const workers: Worker[] = [
      {
        key: "radar",
        code: "9E",
        label: "HIGH-SPEED RADAR",
        room: "INTELLIGENCE PIT",
        raw: record(cadence.radar),
        cast: ["max", "market_structure", "skeptic"],
      },
      {
        key: "observation",
        code: "9A",
        label: "OBSERVATION",
        room: "MONITORING",
        raw: record(cadence.observation),
        cast: ["max", "market_structure", "portfolio"],
      },
      {
        key: "paper",
        code: "9B",
        label: "PAPER TRADING",
        room: "PAPER BAY",
        raw: record(cadence.paper_trading),
        cast: ["max", "portfolio"],
      },
    ];

    const withTimes = workers.map((worker) => ({
      ...worker,
      completedMs: parseTime(worker.raw.last_completed_at),
      age: secondsSince(worker.raw.last_completed_at, now),
    }));

    const latest = [...withTimes]
      .filter((worker) => worker.completedMs !== null)
      .sort((a, b) => (b.completedMs ?? 0) - (a.completedMs ?? 0))[0] ?? null;

    // Motion means a REAL persisted worker checkpoint landed recently.
    const motionWorker =
      latest && latest.age !== null && latest.age <= 90 ? latest : null;

    const eventRows = Array.isArray(telemetry.recent_meaningful_events)
      ? telemetry.recent_meaningful_events
      : [];

    return {
      workers: withTimes,
      latest,
      motionWorker,
      safety,
      telemetryAge: num(telemetryLayer.age_seconds),
      eventCount: eventRows.length,
    };
  }, [overview, now]);

  const motionKey = model.motionWorker
    ? `${model.motionWorker.code}:${text(model.motionWorker.raw.last_completed_at, "")}`
    : "quiet";

  return (
    <section className="lop78-shell" aria-label="IIOS real live operations pulse">
      <header className="lop78-header">
        <div>
          <span>V7.8 · LIVE OPERATIONS PULSE</span>
          <h2>SHOW ME THE FUCKIN' FACTORY WORKING — FROM REAL CHECKPOINTS.</h2>
          <p>
            This layer reacts to persisted 9A / 9B / 9E worker checkpoints every five seconds.
            Motion is presentation-only; the checkpoint, cadence and timestamps are authoritative.
          </p>
        </div>
        <div className={`lop78-live ${error ? "is-bad" : model.motionWorker ? "is-moving" : "is-watch"}`}>
          <i />
          <strong>{error ? "SOURCE WARNING" : model.motionWorker ? "REAL WORKER PULSE" : "WATCHING LIVE"}</strong>
          <span>9G AGE {model.telemetryAge === null ? "—" : `${Math.round(model.telemetryAge)}s`}</span>
        </div>
      </header>

      <div className="lop78-truth">
        <span>DATA · PERSISTED WORKER STATE</span>
        <span>POLL · 5 SECONDS</span>
        <span>LIVE EXECUTION · {model.safety.live_execution === true ? "TRUE" : "FALSE"}</span>
        <span>TRADE AUTHORITY · {model.safety.trade_execution_permission === true ? "TRUE" : "FALSE"}</span>
        <span>VIEW · {view.toUpperCase()}</span>
      </div>

      <div className="lop78-workers">
        {model.workers.map((worker) => {
          const tone = state(worker.raw);
          return (
            <article className={`lop78-worker ${tone === "ON CADENCE" ? "is-good" : tone === "UNKNOWN" ? "is-unknown" : "is-warn"}`} key={worker.key}>
              <div className="lop78-worker-code">{worker.code}</div>
              <div>
                <strong>{worker.label}</strong>
                <span>{tone}</span>
              </div>
              <div className="lop78-worker-clock">
                <b>{ageLabel(worker.age)}</b>
                <em>{countdown(worker.raw.next_due_at, now)}</em>
              </div>
            </article>
          );
        })}
      </div>

      <div className="lop78-stage" key={motionKey}>
        <div className="lop78-stage-head">
          <span>{model.motionWorker ? "REAL CHECKPOINT JUST LANDED" : "LIVE FLOOR STATUS"}</span>
          <strong>
            {model.motionWorker
              ? `${model.motionWorker.code} · ${model.motionWorker.label} → ${model.motionWorker.room}`
              : model.latest
                ? `LAST REAL WORKER · ${model.latest.code} · ${ageLabel(model.latest.age)}`
                : "WAITING FOR FIRST WORKER CHECKPOINT"}
          </strong>
          <em>{model.eventCount} meaningful persisted events in current window</em>
        </div>

        <div className={`lop78-route ${model.motionWorker ? "is-pulsing" : ""}`}>
          <div className="lop78-room">INTELLIGENCE PIT <b>9E</b></div>
          <div className="lop78-line"><i /></div>
          <div className="lop78-room">MONITORING <b>9A</b></div>
          <div className="lop78-line"><i /></div>
          <div className="lop78-room">PAPER BAY <b>9B</b></div>
        </div>

        <div className="lop78-cast">
          {(model.motionWorker?.cast ?? ["max"]).map((key, index) => (
            <div className={`lop78-character ${model.motionWorker ? "is-live" : ""}`} style={{ animationDelay: `${index * 180}ms` }} key={`${motionKey}:${key}`}>
              <CinematicCharacterPortrait
                characterKey={key}
                variant={key === "max" ? "boss" : "scene"}
                active={Boolean(model.motionWorker)}
                reacting={Boolean(model.motionWorker)}
              />
              <strong>
                {key === "max"
                  ? "MAX"
                  : key === "market_structure"
                    ? "Mikey Tape"
                    : key === "skeptic"
                      ? "Johnny No"
                      : "Paulie Positions"}
              </strong>
            </div>
          ))}
        </div>

        <div className="lop78-dialogue">
          {model.motionWorker ? (
            <>
              <strong>MAX · PRESENTATION REACTION</strong>
              <p>
                “{model.motionWorker.code} just dropped a real checkpoint. Good. Now show me what the bastards actually found.”
              </p>
            </>
          ) : (
            <>
              <strong>MAX · FLOOR WATCH</strong>
              <p>
                “No new checkpoint in the last ninety seconds. Nobody fake a parade. Watch the clocks.”
              </p>
            </>
          )}
          <span>NARRATIVE WORDING ONLY · NEVER RAW MODEL SPEECH</span>
        </div>
      </div>
    </section>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import AuctionFactory, { RoomView } from "./AuctionFactory";
import { AUCTION_ROOMS, type AuctionRoomId } from "./auctionRegistry";
import { buildAuctionModel, type AuctionModel, type GovernedCase } from "./auctionSceneModel";
import ExpansionWing from "./ExpansionWing";
import UnifiedCommandCenter from "./UnifiedCommandCenter";
import { loadFactoryTruth, type TruthResult } from "./TruthSourceAdapter";
import "./AuctionEdition.css";

type Mode = "gallery" | "story" | "replay" | "command" | "expansion" | "watch";
const MODES: readonly [Mode, string][] = [["gallery", "Gallery"], ["story", "Story"], ["replay", "Replay"], ["command", "Command"], ["expansion", "Expansion Wing"], ["watch", "Factory Watch"]];
const ROTATION: Mode[] = ["gallery", "story", "replay"];

export default function LivingWallApp() {
  const [mode, setMode] = useState<Mode>("gallery");
  const [truth, setTruth] = useState<TruthResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [rotation, setRotation] = useState(true);
  const [wallMode, setWallMode] = useState(true);
  const [plaque, setPlaque] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [room, setRoom] = useState<AuctionRoomId | null>(null);
  const [selectedCase, setSelectedCase] = useState<GovernedCase | null>(null);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try { const next = await loadFactoryTruth(); if (!disposed) { setTruth(next); setError(null); } }
      catch { if (!disposed) setError("Canonical sanitized truth is unavailable."); }
    };
    void load();
    const telemetryTimer = window.setInterval(() => void load(), 15_000);
    const clockTimer = window.setInterval(() => setNow(new Date()), 60_000);
    const visibility = () => { if (document.hidden) setPaused(true); };
    document.addEventListener("visibilitychange", visibility);
    return () => { disposed = true; window.clearInterval(telemetryTimer); window.clearInterval(clockTimer); document.removeEventListener("visibilitychange", visibility); };
  }, []);
  useEffect(() => {
    const syncFullscreen = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", syncFullscreen);
    return () => document.removeEventListener("fullscreenchange", syncFullscreen);
  }, []);

  const model = useMemo(() => buildAuctionModel(truth, error, now), [truth, error, now]);
  const closeRoom = useCallback(() => setRoom(null), []);
  useEffect(() => {
    if (!rotation || paused || document.hidden) return;
    const timer = window.setInterval(() => setMode((current) => ROTATION[(ROTATION.indexOf(current) + 1) % ROTATION.length] ?? "gallery"), 24_000);
    return () => window.clearInterval(timer);
  }, [paused, rotation]);

  const navigate = (next: Mode) => { setMode(next); setRotation(false); setWallMode(next === "gallery"); };
  const toggleFullscreen = async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  };
  return <div className={`auction-shell ${paused ? "is-paused" : ""} ${wallMode ? "is-wall-mode" : "is-command-mode"}`}>
    <Navigation mode={mode} paused={paused} wallMode={wallMode} fullscreen={fullscreen} navigate={navigate} setPaused={setPaused} setWallMode={setWallMode} setPlaque={setPlaque} toggleFullscreen={() => void toggleFullscreen()}/>
    {!model.safety.telemetryReadOnly || model.safety.ledger || model.safety.write || model.safety.trade || model.safety.live ? <SafetyCurtain/> : null}
    {model.condition !== "AVAILABLE" || model.freshness !== "CURRENT" ? <Degraded model={model} error={error}/> : null}
    {mode === "gallery" ? <Gallery model={model} openRoom={setRoom}/> : null}
    {mode === "story" ? <Story model={model} openRoom={setRoom}/> : null}
    {mode === "replay" ? <Replay model={model} openRoom={setRoom}/> : null}
    {mode === "command" ? <Command model={model} selectCase={setSelectedCase}/> : null}
    {mode === "expansion" ? <ExpansionWing/> : null}
    {mode === "watch" ? <FactoryWatch model={model}/> : null}
    {room ? <RoomView roomId={room} model={model} close={closeRoom}/> : null}
    {selectedCase ? <CaseTheater item={selectedCase} close={() => setSelectedCase(null)}/> : null}
    {plaque ? <CollectorPlaque model={model} close={() => setPlaque(false)}/> : null}
  </div>;
}

function Navigation({ mode, paused, wallMode, fullscreen, navigate, setPaused, setWallMode, setPlaque, toggleFullscreen }: { mode: Mode; paused: boolean; wallMode: boolean; fullscreen: boolean; navigate: (mode: Mode) => void; setPaused: (value: boolean) => void; setWallMode: (value: boolean) => void; setPlaque: (value: boolean) => void; toggleFullscreen: () => void }) {
  return <header className="auction-nav"><button className="auction-brand" onClick={() => navigate("gallery")}><span>IIOS LIVING WALL</span><strong>THE AUCTION EDITION</strong></button><nav aria-label="Living Wall experiences">{MODES.map(([key, label]) => <button key={key} className={mode === key ? "is-active" : ""} onClick={() => navigate(key)} aria-current={mode === key ? "page" : undefined}>{label}</button>)}</nav><div className="auction-tools"><button onClick={() => setPaused(!paused)} aria-pressed={paused}>{paused ? "Resume Scene" : "Pause Scene"}</button><button onClick={() => setWallMode(!wallMode)} aria-pressed={wallMode}>{wallMode ? "Reveal Controls" : "Wall Art Mode"}</button><button onClick={toggleFullscreen} aria-pressed={fullscreen}>{fullscreen ? "Exit Full Screen" : "Enter Full Screen"}</button><button onClick={() => setPlaque(true)}>Collector Plaque</button><button disabled title="Sound remains muted until an owned soundscape is supplied">Sound Muted</button></div></header>;
}

function Gallery({ model, openRoom }: { model: AuctionModel; openRoom: (id: AuctionRoomId) => void }) {
  return <main className="auction-gallery"><AuctionFactory model={model} onOpenRoom={openRoom}/><div className="auction-gallery-caption"><span>IIOS LIVING WALL — THE FAMILY FACTORY</span><h1>{model.quiet ? "The House Is Quiet" : "Evidence Is Moving Through the House"}</h1><p>{model.quiet ? "A quiet floor is a truthful floor. MAX patrols; no activity is invented." : "Every illuminated room is anchored to a complete governed receipt."}</p><small>CREATED 2026 · AUCTION EDITION 1.0 · GOVERNED READ MODEL</small></div></main>;
}

function Story({ model, openRoom }: { model: AuctionModel; openRoom: (id: AuctionRoomId) => void }) {
  const events = model.events.filter((event) => !event.historical);
  return <main className="auction-editorial"><header><span>DAILY STORY ENGINE / SOURCE-LINKED</span><h1>{events.length ? "The day, without embellishment." : "Why the factory deliberately did nothing."}</h1><p>{events.length ? "Each scene below is selected by an exact event type, timestamp, and lineage identifier." : "No complete current event receipt was supplied. The correct episode is restraint."}</p></header><ol className="auction-storyline">{events.length ? events.map((event) => <li key={event.id}><button onClick={() => event.room && openRoom(event.room)} disabled={!event.room}><time>{new Date(event.at).toLocaleString()}</time><strong>{event.type.replaceAll("_", " ")}</strong><span>{event.room ? AUCTION_ROOMS.find((candidate) => candidate.id === event.room)?.label : "QUARANTINED / UNMAPPED"}</span><small>CASE {event.caseId ?? "UNKNOWN"} · {event.provenance}</small></button></li>) : <li className="auction-empty"><strong>THE HOUSE IS QUIET</strong><p>Radar supplied no complete receipt. Research makes no claim. Committee has nothing to debate. Risk and Paper remain locked. Monitoring waits. Learning preserves the silence.</p></li>}</ol></main>;
}

function Replay({ model, openRoom }: { model: AuctionModel; openRoom: (id: AuctionRoomId) => void }) {
  return <main className="auction-editorial auction-replay"><header><span>REPLAY THEATER / HISTORICAL ONLY</span><h1>{model.replay.length ? "Completed session receipts" : "No replay session available"}</h1><p>Current activity is never relabeled as history. Playback exists only for explicitly historical receipts.</p></header><div className="auction-filmstrip">{model.replay.map((event, index) => <button key={event.id} onClick={() => event.room && openRoom(event.room)}><span>{String(index + 1).padStart(2, "0")}</span><time>{new Date(event.at).toLocaleString()}</time><strong>{event.type.replaceAll("_", " ")}</strong><small>{event.provenance}</small></button>)}</div></main>;
}

function Command({ model, selectCase }: { model: AuctionModel; selectCase: (item: GovernedCase) => void }) {
  return <main className="auction-command"><section className="auction-command-intro"><span>COMMAND MODE / DETAILED OBSERVER</span><h1>The operating interface behind the artwork.</h1><p>Factory telemetry remains sanitized and read-only. Missing fields remain UNKNOWN.</p></section><UnifiedCommandCenter/><section className="auction-case-index"><header><span>CASE THEATER</span><strong>{model.cases.length ? `${model.cases.length} GOVERNED CASES` : "NO CASE DETAIL SUPPLIED"}</strong></header>{model.cases.length ? model.cases.map((item) => <button key={item.id} onClick={() => selectCase(item)}><b>{item.ticker}</b><span>{item.thesis}</span><small>{item.id}</small></button>) : <p>Aggregate case count may be available, but private case detail is not exposed by this read model.</p>}</section></main>;
}

function FactoryWatch({ model }: { model: AuctionModel }) {
  const fields = [["Availability", model.condition], ["Freshness", model.freshness], ["Generated", model.generatedAt ?? "UNKNOWN"], ["Market validation", model.marketValidation], ["Telemetry read-only", String(model.safety.telemetryReadOnly).toUpperCase()], ["Direct ledger", "FALSE"], ["Backend write", "FALSE"], ["Trade execution", "FALSE"], ["Live execution", "FALSE"]];
  return <main className="auction-watch"><header><span>FACTORY WATCH / NO THEATER</span><h1>The locks have the last word.</h1><p>Operational truth, provenance, freshness, and authority—nothing else.</p></header><section>{fields.map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}</section><aside><b>{model.condition === "AVAILABLE" && model.freshness === "CURRENT" ? "OBSERVATION HEALTHY" : "OBSERVATION DEGRADED"}</b><p>UNKNOWN values are withheld. This view cannot modify the backend, ledger, portfolio, orders, or capital.</p></aside></main>;
}

function CaseTheater({ item, close }: { item: GovernedCase; close: () => void }) {
  const fields = [["Case identity", `${item.ticker} · ${item.id}`], ["Thesis", item.thesis], ["Supporting evidence", item.evidenceFor], ["Opposing evidence", item.evidenceAgainst], ["Committee outcome", item.committee], ["Risk inspection", item.risk], ["Paper decision", item.paper], ["Monitoring", item.monitoring], ["Thesis drift", item.drift], ["Learned outcome", item.learned], ["Provenance", item.provenance]];
  return <div className="auction-room-modal" role="dialog" aria-modal="true" aria-labelledby="case-title" onMouseDown={close}><section onMouseDown={(event) => event.stopPropagation()}><button className="auction-close" onClick={close}>×</button><span>CASE THEATER / READ ONLY</span><h2 id="case-title">{item.ticker}</h2><dl>{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section></div>;
}

function CollectorPlaque({ model, close }: { model: AuctionModel; close: () => void }) {
  return <div className="auction-plaque-backdrop" role="dialog" aria-modal="true" aria-labelledby="plaque-title" onMouseDown={close}><article className="auction-plaque" onMouseDown={(event) => event.stopPropagation()}><button onClick={close}>×</button><span>THE WORK · GOVERNED EDITION</span><h2 id="plaque-title">IIOS Living Wall — The Family Factory</h2><p>A living architectural portrait of an evidence-governed investment intelligence system. Motion is earned by receipts; silence is treated as information.</p><dl><dt>Edition</dt><dd>Auction Edition 1.0</dd><dt>Creation date</dt><dd>2026</dd><dt>Governed state</dt><dd>{model.condition} / {model.freshness}</dd><dt>Medium</dt><dd>Responsive real-time browser artwork</dd><dt>Authority</dt><dd>Observation only</dd></dl><small>No blockchain, NFT, guaranteed-return, or ownership claim is made.</small></article></div>;
}

function Degraded({ model, error }: { model: AuctionModel; error: string | null }) { return <div className="auction-degraded" role="alert"><strong>{model.condition} / {model.freshness}</strong><span>{error ?? "The latest sanitized truth is not both AVAILABLE and CURRENT. Motion is withheld."}</span></div>; }
function SafetyCurtain() { return <div className="auction-safety-curtain" role="alert"><strong>SAFETY LOCK</strong><span>Read-only authority could not be verified. Factory presentation is frozen.</span></div>; }

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import AuctionFactory, { RoomView, NorthstarRoomView, NorthstarAuctionFactory } from "./AuctionFactory";
import { AUCTION_ROOMS, type AuctionRoomId } from "./auctionRegistry";
import { buildAuctionModel, type AuctionModel, type GovernedCase } from "./auctionSceneModel";
import MobExpansionWing from "./MobExpansionWing";
import MuseumControlRoom from "./MuseumControlRoom";
import MuseumCaseLibrary, { type CaseFilter } from "./MuseumCaseLibrary";
import { latestFactoryOutputs, stationOutput } from "./museumLiveBinding";
import { useExpansionWingSnapshot } from "./ExpansionWingSnapshotContext";
import { adaptExpansionSnapshot } from "./TruthSourceAdapter";
import { activateDialog, activateNorthstarDialog, requestDialogClose } from "./dialogAccessibility";
import { resolveAuctionPresentation, type AuctionMode } from "./auctionPresentation";
import { BRIGHTNESS_PROFILES, nextBrightnessProfile, resolveProtectionState, type BrightnessProfile } from "./commissioningProfile";
import "./AuctionEdition.css";
import "./MuseumLegibility.css";
import { useNorthstar } from './northstarContext';
import { NorthstarSessionStatus, NorthstarGroup, NorthstarHistory, NorthstarRow } from './NorthstarPanels';
import { stationRows, northstarFloorOutputs } from './northstarSession';
import { NorthstarControlRoom } from './MuseumControlRoom';
import { NorthstarCaseLibrary } from './MuseumCaseLibrary';
import { NorthstarExpansionWing } from './MobExpansionWing';
import { boundedNavigation } from './northstarNavigation';

type Mode = AuctionMode;
const MODES: readonly [Mode, string][] = [["gallery", "Gallery"], ["story", "Story"], ["replay", "Replay"], ["command", "Command"], ["cases", "Cases"], ["expansion", "Expansion Wing"], ["watch", "Factory Watch"]];
const ROTATION: Mode[] = ["gallery", "story", "replay"];
const modeFromHash = (): Mode => {
  const requested = typeof window === "undefined" ? "" : window.location.hash.slice(1);
  const namespace = requested.split("/", 1)[0];
  return MODES.some(([mode]) => mode === namespace) ? namespace as Mode : namespace === "expansion-wing" ? "expansion" : namespace === "factory-watch" ? "watch" : "gallery";
};

export default function LivingWallApp() {
  const { snapshot, sanitizedOverview, connection, fixtureMode, snapshotAgeSeconds, runtimeCapabilities } = useExpansionWingSnapshot();
  const startInWallMode = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("wall") === "1";
  const [mode, setMode] = useState<Mode>(modeFromHash);
  const [paused, setPaused] = useState(false);
  const [rotation, setRotation] = useState(!startInWallMode);
  const [wallMode, setWallMode] = useState(startInWallMode);
  const [plaque, setPlaque] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [room, setRoom] = useState<AuctionRoomId | null>(null);
  const [roomOpener, setRoomOpener] = useState<HTMLElement | null>(null);
  const [selectedCase, setSelectedCase] = useState<GovernedCase | null>(null);
  const [caseFilter, setCaseFilter] = useState<CaseFilter>("ALL");
  const [now, setNow] = useState(() => new Date());
  const [brightness, setBrightness] = useState<BrightnessProfile>(() => {
    const saved = typeof window === "undefined" ? null : window.localStorage.getItem("iios.museum.brightness");
    return saved === "conservation" || saved === "evening" ? saved : "exhibition";
  });
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const clockTimer = window.setInterval(() => setNow(new Date()), 60_000);
    const visibility = () => { if (document.hidden) setPaused(true); };
    document.addEventListener("visibilitychange", visibility);
    return () => { window.clearInterval(clockTimer); document.removeEventListener("visibilitychange", visibility); };
  }, []);
  useEffect(() => {
    const restore = () => { setMode(modeFromHash()); setRotation(false); setWallMode(false); };
    window.addEventListener("popstate", restore);
    window.addEventListener("hashchange", restore);
    return () => { window.removeEventListener("popstate", restore); window.removeEventListener("hashchange", restore); };
  }, []);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReducedMotion(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    const syncFullscreen = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", syncFullscreen);
    return () => document.removeEventListener("fullscreenchange", syncFullscreen);
  }, []);

  const truth = useMemo(() => snapshot ? adaptExpansionSnapshot(snapshot, connection, snapshotAgeSeconds) : null, [snapshot, connection, snapshotAgeSeconds]);
  const error = snapshot ? null : "Canonical sanitized truth is unavailable.";
  const model = useMemo(() => buildAuctionModel(truth, error, now), [truth, error, now]);
  const safetyLocked = !model.safety.telemetryReadOnly || model.safety.ledger || model.safety.write || model.safety.trade || model.safety.live;
  const unavailableSince = connection === "CURRENT" ? null : snapshotAgeSeconds === null ? now.getTime() : now.getTime() - snapshotAgeSeconds * 1000;
  const protection = resolveProtectionState(now, unavailableSince);
  const presentation = resolveAuctionPresentation({ mode, wallMode, paused, reducedMotion, safetyLocked });
  const openRoom = useCallback((roomId: AuctionRoomId, opener?: HTMLElement) => {
    setRoomOpener(opener ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null));
    setRoom(roomId);
  }, []);
  const closeRoom = useCallback(() => setRoom(null), []);
  useEffect(() => {
    if (!rotation || paused || document.hidden) return;
    const timer = window.setInterval(() => setMode((current) => ROTATION[(ROTATION.indexOf(current) + 1) % ROTATION.length] ?? "gallery"), 24_000);
    return () => window.clearInterval(timer);
  }, [paused, rotation]);

  const navigate = (next: Mode) => { window.history.pushState({ museumMode: next }, "", `#${next}`); setMode(next); setRotation(false); setWallMode(false); };
  const openCases = (filter: CaseFilter = "ALL") => { setCaseFilter(filter); navigate("cases"); };
  const enterWallArtMode = () => { setMode("gallery"); setRotation(false); setWallMode(true); };
  const cycleBrightness = () => setBrightness((current) => {
    const next = nextBrightnessProfile(current);
    window.localStorage.setItem("iios.museum.brightness", next);
    return next;
  });
  const toggleFullscreen = async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  };
  return <div className={`auction-shell auction-master-1-1 auction-master-1-2 brightness-${brightness} protection-${protection} ${paused ? "is-paused" : ""} ${reducedMotion ? "is-reduced-motion" : ""} ${model.motion.ambient ? "" : "is-truth-frozen"} ${wallMode ? "is-wall-mode" : "is-command-mode"}`} data-edition="Museum Master 1.2" data-protection-state={protection} style={{ "--exhibition-level": BRIGHTNESS_PROFILES[brightness].sceneLevel } as React.CSSProperties}>
    <Navigation mode={presentation.effectiveMode} paused={paused} wallMode={wallMode} fullscreen={fullscreen} brightness={brightness} navigate={navigate} enterWallArtMode={enterWallArtMode} cycleBrightness={cycleBrightness} setPaused={setPaused} setWallMode={setWallMode} setPlaque={setPlaque} toggleFullscreen={() => void toggleFullscreen()}/>
    {safetyLocked ? <SafetyCurtain compact={presentation.compactSafetyIndicator}/> : null}
    {model.condition !== "AVAILABLE" || model.freshness !== "CURRENT" ? <Degraded model={model} error={error}/> : null}
    <WallHealth model={model} protection={protection}/>
    <div className="auction-scene-plane">
    {presentation.factoryVisible ? <Gallery model={model} snapshot={snapshot} overview={sanitizedOverview} openRoom={openRoom} openCases={openCases} navigate={navigate}/> : null}
    {presentation.effectiveMode === "story" ? <Story model={model} openRoom={openRoom}/> : null}
    {presentation.effectiveMode === "replay" ? <Replay model={model} openRoom={openRoom} navigate={navigate}/> : null}
    {presentation.effectiveMode === "command" ? <Command model={model} selectCase={setSelectedCase} fixtureMode={fixtureMode} openCases={openCases} navigate={navigate}/> : null}
    {presentation.effectiveMode === "cases" ? <MuseumCaseLibrary key={caseFilter} initialFilter={caseFilter}/> : null}
    {presentation.effectiveMode === "expansion" ? <MobExpansionWing/> : null}
    {presentation.effectiveMode === "watch" ? <FactoryWatch model={model} publisherControl={runtimeCapabilities.publisherControl}/> : null}
    </div>
    {room ? <RoomView roomId={room} model={model} snapshot={snapshot} overview={sanitizedOverview} opener={roomOpener} close={closeRoom}/> : null}
    {selectedCase ? <CaseTheater item={selectedCase} close={() => setSelectedCase(null)}/> : null}
    {plaque ? <CollectorPlaque model={model} close={() => setPlaque(false)}/> : null}
  </div>;
}

function Navigation({ mode, paused, wallMode, fullscreen, brightness, navigate, enterWallArtMode, cycleBrightness, setPaused, setWallMode, setPlaque, toggleFullscreen }: { mode: Mode; paused: boolean; wallMode: boolean; fullscreen: boolean; brightness: BrightnessProfile; navigate: (mode: Mode) => void; enterWallArtMode: () => void; cycleBrightness: () => void; setPaused: Dispatch<SetStateAction<boolean>>; setWallMode: Dispatch<SetStateAction<boolean>>; setPlaque: Dispatch<SetStateAction<boolean>>; toggleFullscreen: () => void }) {
  return <header className="auction-nav"><button className="auction-brand" onClick={() => navigate("gallery")}><span>IIOS LIVING WALL</span><strong>THE AUCTION EDITION · MUSEUM MASTER 1.2</strong></button><nav aria-label="Living Wall experiences">{MODES.map(([key, label]) => <button key={key} className={mode === key ? "is-active" : ""} onClick={() => navigate(key)} aria-current={mode === key ? "page" : undefined}>{label}</button>)}</nav><div className="auction-tools"><button onClick={() => setPaused((current) => !current)} aria-pressed={paused}>{paused ? "Resume Scene" : "Pause Scene"}</button><button onClick={() => wallMode ? setWallMode(false) : enterWallArtMode()} aria-pressed={wallMode}>{wallMode ? "Reveal Controls" : "Wall Art Mode"}</button><button onClick={toggleFullscreen} aria-pressed={fullscreen}>{fullscreen ? "Exit Full Screen" : "Enter Full Screen"}</button><button onClick={cycleBrightness}>Brightness: {BRIGHTNESS_PROFILES[brightness].label}</button><button onClick={() => setPlaque(true)}>Collector Plaque</button><button disabled title="Sound remains muted until an owned soundscape is supplied">Sound Muted</button></div></header>;
}

function Gallery({ model, snapshot, overview, openRoom, openCases, navigate }: { model: AuctionModel; snapshot: import("./ExpansionWingSnapshotContext").ExpansionSnapshot | null; overview: unknown; openRoom: (id: AuctionRoomId, opener?: HTMLElement) => void; openCases:(filter?:CaseFilter)=>void; navigate:(mode:Mode)=>void }) {
  const marketOutput = stationOutput("calendar", snapshot, overview);
  const publisherOutput = stationOutput("publisher", snapshot, overview);
  const ambient = marketOutput.value.includes("MARKET_CLOSED") ? "MARKET-CLOSED NIGHT WATCH" : model.freshness === "STALE" ? "WAITING-FOR-EVIDENCE INSPECTION" : publisherOutput.value.includes("SEQUENCE") ? "PUBLISHER OBSERVATION WATCH" : "DEPARTMENT READINESS WATCH";
  const outputs = latestFactoryOutputs(overview, 4);
  return <main className="auction-gallery">
    <nav className="auction-gallery-shortcuts" aria-label="Case activity and product destinations">
      <button onClick={() => openCases("ALL")}>Radar · 40 authenticated cases</button><button onClick={() => openCases("COMMITTEE")}>Committee · 35 cases</button><button onClick={() => openCases("RISK")}>Risk · 5 cases</button><button onClick={() => openCases("INCOMPLETE")}>Evidence · 40 incomplete</button><button onClick={() => openCases("OUTCOMES")}>Learning · 0 outcomes</button><button onClick={() => navigate("replay")}>Replay · 0 authenticated</button><button onClick={() => navigate("expansion")}>24 Product Accounts</button>
    </nav>
    <AuctionFactory model={model} snapshot={snapshot} overview={overview} onOpenRoom={openRoom}/>
    <aside className="auction-latest-feed" aria-label="Latest Factory Outputs"><span>LATEST FACTORY OUTPUTS</span>{outputs.length ? outputs.map((item) => <div key={item.id}><time>{new Date(item.timestamp).toLocaleTimeString()}</time><b>{item.module} · {item.category}</b><small>{item.explanation}</small></div>) : <p>No authenticated output receipts reported.</p>}</aside>
    <div className="auction-gallery-caption" data-testid="quiet-caption" data-ambient-scene={ambient}><span>IIOS LIVING WALL — THE FAMILY FACTORY</span><h1>{model.quiet ? "The House Is Quiet — and attentive" : "Evidence Is Moving Through the House"}</h1><p>{model.quiet ? "MAX keeps the watch while departments inspect, file, and wait. This is visible ambient factory life—not evidence movement." : "Every illuminated case route is anchored to a complete governed receipt."}</p><b className="auction-ambient-cue">AMBIENT PRESENTATION · {ambient}</b><p>No candidate, trade, position, order, recommendation, endorsement, profit, or provider connection is implied.</p><small><span>CREATED 2026</span><i>·</i><span>THE AUCTION EDITION</span><i>·</i><span>MUSEUM MASTER 1.2</span><i>·</i><span>GOVERNED READ MODEL</span></small></div>
  </main>;
}

function Story({ model, openRoom }: { model: AuctionModel; openRoom: (id: AuctionRoomId) => void }) {
  const events = model.events.filter((event) => !event.historical);
  return <main className="auction-editorial"><header><span>DAILY STORY ENGINE / SOURCE-LINKED</span><h1>{events.length ? "The day, without embellishment." : "Why the factory deliberately did nothing."}</h1><p>{events.length ? "Each scene below is selected by an exact event type, timestamp, and lineage identifier." : "No complete current event receipt was supplied. The correct episode is restraint."}</p></header><ol className="auction-storyline">{events.length ? events.map((event) => <li key={event.id}><button onClick={() => event.room && openRoom(event.room)} disabled={!event.room}><time>{new Date(event.at).toLocaleString()}</time><strong>{event.type.replaceAll("_", " ")}</strong><span>{event.room ? AUCTION_ROOMS.find((candidate) => candidate.id === event.room)?.label : "QUARANTINED / UNMAPPED"}</span><small>CASE {event.caseId ?? "UNKNOWN"} · {event.provenance}</small></button></li>) : <li className="auction-empty"><strong>THE HOUSE IS QUIET</strong><p>Radar supplied no complete receipt. Research makes no claim. Committee has nothing to debate. Risk and Paper remain locked. Monitoring waits. Learning preserves the silence.</p></li>}</ol></main>;
}

function Replay({ model, openRoom, navigate }: { model: AuctionModel; openRoom: (id: AuctionRoomId) => void; navigate: (mode: Mode) => void }) {
  return <main className="auction-editorial auction-replay"><header><span>REPLAY THEATER / HISTORICAL ONLY</span><h1>{model.replay.length ? "Completed session receipts" : "No authenticated replay is available"}</h1><p>Current activity is never relabeled as history. Playback requires an explicitly historical, sanitized receipt with a valid timestamp, immutable lineage, and governed provenance.</p></header>{model.replay.length ? <div className="auction-filmstrip">{model.replay.map((event, index) => <button key={event.id} onClick={() => event.room && openRoom(event.room)}><span>{String(index + 1).padStart(2, "0")}</span><time>{new Date(event.at).toLocaleString()}</time><strong>{event.type.replaceAll("_", " ")}</strong><small>{event.provenance}</small></button>)}</div> : <section className="auction-replay-empty"><span>WHY THE SCREEN IS EMPTY</span><h2>No qualifying historical receipt was supplied.</h2><p>The latest sanitized snapshot is <strong>{model.condition} / {model.freshness}</strong>{model.generatedAt ? `, generated ${new Date(model.generatedAt).toLocaleString()}` : "; its generation time is unavailable"}. It describes present observation state and is not replay history.</p><dl><div><dt>Authenticated replay requires</dt><dd>Historical marker · valid time · immutable lineage · sanitized provenance</dd></div><div><dt>Current evidence movement</dt><dd>{model.motion.evidence ? "PRESENT — NOT RELABELED AS HISTORY" : "NONE"}</dd></div></dl><div><button onClick={() => navigate("gallery")}>Return to Gallery</button><button onClick={() => navigate("command")}>Open Control Room</button></div></section>}</main>;
}

function Command({ model, selectCase, fixtureMode, openCases, navigate }: { model: AuctionModel; selectCase: (item: GovernedCase) => void; fixtureMode: boolean; openCases:(filter?:CaseFilter)=>void; navigate:(mode:Mode)=>void }) {
  return <MuseumControlRoom model={model} fixtureMode={fixtureMode} selectCase={selectCase} openCases={openCases} openProducts={()=>navigate("expansion")}/>;
}

function FactoryWatch({ model, publisherControl }: { model: AuctionModel; publisherControl: boolean }) {
  const fields = [["Availability", model.condition], ["Freshness", model.freshness], ["Generated", model.generatedAt ?? "UNKNOWN"], ["Market validation", model.marketValidation], ["Telemetry read-only", String(model.safety.telemetryReadOnly).toUpperCase()], ["Browser publisher control", String(publisherControl).toUpperCase()], ["Direct ledger", "FALSE"], ["Backend write", "FALSE"], ["Trade execution", "FALSE"], ["Live execution", "FALSE"]];
  return <main className="auction-watch"><header><span>FACTORY WATCH / NO THEATER</span><h1>The locks have the last word.</h1><p>Operational truth, provenance, freshness, and authority—nothing else.</p></header><section>{fields.map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}</section><aside><b>{model.condition === "AVAILABLE" && model.freshness === "CURRENT" ? "OBSERVATION HEALTHY" : "OBSERVATION DEGRADED"}</b><p>UNKNOWN values are withheld. This view cannot modify the backend, ledger, portfolio, orders, or capital.</p></aside></main>;
}

function CaseTheater({ item, close }: { item: GovernedCase; close: () => void }) {
  const fields = [["Case identity", `${item.ticker} · ${item.id}`], ["Thesis", item.thesis], ["Supporting evidence", item.evidenceFor], ["Opposing evidence", item.evidenceAgainst], ["Committee outcome", item.committee], ["Risk inspection", item.risk], ["Paper decision", item.paper], ["Monitoring", item.monitoring], ["Thesis drift", item.drift], ["Learned outcome", item.learned], ["Provenance", item.provenance]];
  return <AccessibleDialog className="auction-room-modal auction-case-theater" titleId="case-title" descriptionId="case-description" close={close}><span>CASE THEATER / READ ONLY</span><h2 id="case-title">{item.ticker}</h2><p id="case-description">A cinematic evidence ledger. Absent fields remain explicitly UNKNOWN.</p><dl>{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></AccessibleDialog>;
}

function CollectorPlaque({ model, close }: { model: AuctionModel; close: () => void }) {
  return <AccessibleDialog className="auction-plaque-backdrop" surfaceClassName="auction-plaque" titleId="plaque-title" descriptionId="plaque-description" close={close}><span>THE WORK · GOVERNED EDITION</span><h2 id="plaque-title">IIOS Living Wall — The Auction Edition</h2><p id="plaque-description">A living architectural portrait of an evidence-governed intelligence factory. Motion is earned by receipts; silence is treated as information.</p><dl><dt>Edition</dt><dd>Museum Master 1.2 / 77-Inch Commissioning Edition</dd><dt>Creation date</dt><dd>2026</dd><dt>Governed state</dt><dd>{model.condition} / {model.freshness}</dd><dt>Medium</dt><dd>Responsive real-time browser artwork</dd><dt>Motion authority</dt><dd>{model.motion.reason}</dd><dt>Authority</dt><dd>Observation and governed paper-market research only</dd></dl><small>Ownership grants no trading authority, credentials, source-control access, financial guarantee, blockchain title, NFT right, or live-execution capability.</small></AccessibleDialog>;
}

function WallHealth({ model, protection }: { model: AuctionModel; protection: "awake" | "dim" | "rest" }) { return <aside className="auction-wall-health" data-testid="wall-health" aria-live="polite"><strong>{model.condition} / {model.freshness}</strong><span>READ ONLY · LEDGER FALSE · WRITE FALSE · TRADE FALSE · LIVE FALSE</span><small>DISPLAY {protection.toUpperCase()}</small></aside>; }

function AccessibleDialog({ className, surfaceClassName, titleId, descriptionId, close, children }: { className: string; surfaceClassName?: string; titleId: string; descriptionId: string; close: () => void; children: ReactNode }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(typeof document === "undefined" ? null : document.activeElement instanceof HTMLElement ? document.activeElement : null);
  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    const initialFocus = closeRef.current;
    if (!dialog || !initialFocus || !dialog.parentElement) return;
    const background = Array.from(dialog.parentElement.children).filter((element): element is HTMLElement => element instanceof HTMLElement && element !== dialog);
    return activateDialog({ dialog, initialFocus, opener: openerRef.current, background, close, documentTarget: document });
  }, [close]);
  return <div ref={dialogRef} className={className} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} tabIndex={-1} onMouseDown={close}><section className={surfaceClassName} onMouseDown={(event) => event.stopPropagation()}><button ref={closeRef} className="auction-close" onClick={() => requestDialogClose(close)} aria-label="Close dialog">×</button>{children}</section></div>;
}

function Degraded({ model, error }: { model: AuctionModel; error: string | null }) { return <div className="auction-degraded" data-testid="truth-indicator" role="alert"><strong>{model.condition} / {model.freshness}</strong><span>{error ?? "The latest sanitized truth is not both AVAILABLE and CURRENT. Motion is withheld."}</span></div>; }
function SafetyCurtain({ compact }: { compact: boolean }) { return <div className={`auction-safety-curtain ${compact ? "is-compact" : ""}`} data-testid="safety-indicator" role="alert"><strong>SAFETY LOCK</strong><span>Read-only authority could not be verified. Factory motion is frozen.</span></div>; }

// Separate exported entry: no permanent snapshot provider or legacy destination is mounted.
export function NorthstarLivingWall() {
  const shadow = useNorthstar(); const { view, status } = shadow;
  const [mode, setMode] = useState<Mode>(modeFromHash);
  const [wallMode, setWallMode] = useState(false);
  const [plaque, setPlaque] = useState(false); const [brightness, setBrightness] = useState<BrightnessProfile>('exhibition');
  const [plaqueOpener, setPlaqueOpener] = useState<HTMLElement | null>(null);
  const [routeError, setRouteError] = useState(false);
  const [room, setRoom] = useState<AuctionRoomId | null>(null); const [opener, setOpener] = useState<HTMLElement | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const closeRoom = useCallback(() => setRoom(null), []);
  const closePlaque = useCallback(() => setPlaque(false), []);
  useEffect(() => {
    const restore = () => { setMode(modeFromHash()); setRoom(null); };
    const sync = () => setFullscreen(Boolean(document.fullscreenElement));
    window.addEventListener('hashchange', restore); window.addEventListener('popstate', restore); document.addEventListener('fullscreenchange', sync);
    return () => { window.removeEventListener('hashchange', restore); window.removeEventListener('popstate', restore); document.removeEventListener('fullscreenchange', sync); };
  }, []);
  // The floor is presentation, not a fabricated event adapter. Keep routes frozen.
  const model = useMemo(() => {
    const base = buildAuctionModel(null, 'NO_CURRENT_CASE_DOSSIER_IN_SHADOW_PROJECTION', new Date(0));
    return { ...base, generatedAt: view?.published_at ?? null, freshness: status,
      condition: status === 'CURRENT' ? 'AVAILABLE' as const : status,
      marketValidation: 'SHADOW_OBSERVATION_NOT_MARKET_DATA',
      safety: { telemetryReadOnly: true, ledger: false, write: false, trade: false, live: false } };
  }, [view, status]);
  const navigate = (next: Mode) => {
    if (!boundedNavigation(history, window.location.hash, `#${next}`, { museumMode: next })) { setRouteError(true); return; }
    setRouteError(false); setMode(next); setRoom(null); setPlaque(false);
  };
  const floor = <><p className="northstar-floor-label">MAX · NARRATIVE PRESENTATION ONLY. The house observes retained governed facts; no research, decisions or trades are implied by character artwork.</p>
    <NorthstarAuctionFactory model={model} outputs={northstarFloorOutputs(shadow)} onOpenRoom={(id, el) => { setRoom(id); setOpener(el ?? null); }}/></>;
  return <div className={`auction-shell auction-master-1-1 auction-master-1-2 northstar-full-session brightness-${brightness} is-truth-frozen ${wallMode ? 'is-wall-mode' : 'is-command-mode'}`} data-edition="Museum Master 1.2" data-shadow-state={status}>
    <NorthstarNavigation mode={mode} wallMode={wallMode} fullscreen={fullscreen} brightness={brightness} navigate={navigate}
      enterWallArtMode={() => { setWallMode(true); navigate('gallery'); }} cycleBrightness={() => setBrightness(nextBrightnessProfile(brightness))}
      setWallMode={setWallMode} openPlaque={element => { setRoom(null); setPlaqueOpener(element); setPlaque(true); }} toggleFullscreen={() => {
        void (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch(() => undefined);
      }}/>
    {routeError && <p role="alert">Browser navigation update unavailable. No source data or authority changed.</p>}
    <NorthstarSessionStatus/>
    <div className="auction-scene-plane">
      {mode === 'gallery' && <main className="auction-gallery">{floor}<NorthstarGroup group="rooms"/><NorthstarGroup group="agents"/><NorthstarGroup group="governance"/></main>}
      {mode === 'story' && <main className="auction-editorial"><h1>Source before story</h1><p>NARRATIVE is not evidence. Original classifications and timestamps remain intact.</p><NorthstarHistory/></main>}
      {mode === 'replay' && <main className="auction-editorial"><h1>Historical and Replay remain distinct</h1><NorthstarHistory/></main>}
      {mode === 'command' && <NorthstarControlRoom/>}
      {mode === 'cases' && <NorthstarCaseLibrary/>}
      {mode === 'expansion' && <NorthstarExpansionWing/>}
      {mode === 'watch' && <main className="auction-watch"><NorthstarGroup group="routes"/><NorthstarGroup group="subsystems"/></main>}
    </div>
    {room && <NorthstarRoomView roomId={room} model={model} opener={opener} close={closeRoom}
      governedContent={<section><h2>Governed shadow station evidence · {status}</h2><p>Station grouping is presentation only; individual activity requires an explicit binding.</p>
        {stationRows(view?.factory, room).map(row => <details key={row.id}><summary>{row.name}</summary><NorthstarRow row={row}/></details>)}
        {!stationRows(view?.factory, room).length && <p>UNAVAILABLE — no bound station evidence.</p>}</section>}/>}
    {plaque && <NorthstarCollectorPlaque model={model} opener={plaqueOpener} close={closePlaque}/>}
  </div>;
}

function NorthstarNavigation({ mode, wallMode, fullscreen, brightness, navigate, enterWallArtMode, cycleBrightness, setWallMode, openPlaque, toggleFullscreen }: {
  mode: Mode; wallMode: boolean; fullscreen: boolean; brightness: BrightnessProfile; navigate: (mode: Mode) => void;
  enterWallArtMode: () => void; cycleBrightness: () => void; setWallMode: Dispatch<SetStateAction<boolean>>;
  openPlaque: (opener: HTMLElement) => void; toggleFullscreen: () => void;
}) {
  return <header className="auction-nav"><button className="auction-brand" onClick={() => navigate('gallery')}><span>IIOS LIVING WALL</span><strong>THE AUCTION EDITION · MUSEUM MASTER 1.2</strong></button>
    <nav aria-label="Living Wall experiences">{MODES.map(([key, label]) => <button key={key} className={mode === key ? 'is-active' : ''} onClick={() => navigate(key)} aria-current={mode === key ? 'page' : undefined}>{label}</button>)}</nav>
    <div className="auction-tools"><button disabled title="Isolated deny-only mode keeps scene motion frozen; governed status continues to refresh.">Scene Frozen · Deny-only</button>
      <button onClick={() => wallMode ? setWallMode(false) : enterWallArtMode()} aria-pressed={wallMode}>{wallMode ? 'Reveal Controls' : 'Wall Art Mode'}</button>
      <button onClick={toggleFullscreen} aria-pressed={fullscreen}>{fullscreen ? 'Exit Full Screen' : 'Enter Full Screen'}</button>
      <button onClick={cycleBrightness}>Brightness: {BRIGHTNESS_PROFILES[brightness].label}</button>
      <button data-northstar-plaque-opener onClick={event => openPlaque(event.currentTarget)}>Collector Plaque</button>
      <button disabled title="Sound remains muted until an owned soundscape is supplied">Sound Muted</button></div>
  </header>;
}

function NorthstarCollectorPlaque({ model, opener, close }: { model: AuctionModel; opener: HTMLElement | null; close: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null); const headingRef = useRef<HTMLHeadingElement>(null);
  useLayoutEffect(() => {
    const dialog = dialogRef.current, initialFocus = headingRef.current;
    if (!dialog || !initialFocus || !dialog.parentElement) return;
    const background = [...dialog.parentElement.children].filter((element): element is HTMLElement => element instanceof HTMLElement && element !== dialog);
    return activateNorthstarDialog({ dialog, initialFocus, opener, background, close, documentTarget: document });
  }, [close, opener]);
  return <div ref={dialogRef} className="auction-room-modal northstar-station-backdrop" role="dialog" aria-modal="true" aria-labelledby="northstar-plaque-title" aria-describedby="northstar-plaque-description" onMouseDown={close}>
    <section className="northstar-station-dialog northstar-collector-plaque" onMouseDown={event => event.stopPropagation()}>
      <header className="northstar-dialog-header"><div><span>THE WORK · GOVERNED EDITION</span><h2 ref={headingRef} tabIndex={-1} id="northstar-plaque-title">IIOS Living Wall — The Auction Edition</h2></div><button className="auction-close" onClick={close} aria-label="Close Collector Plaque">×</button></header>
      <div className="northstar-dialog-body" tabIndex={0} role="region" aria-label="Collector Plaque content">
        <p id="northstar-plaque-description">A living architectural portrait of an evidence-governed intelligence factory. Motion is earned by receipts; silence is treated as information.</p>
        <dl>{[['Edition','Museum Master 1.2 / 77-Inch Commissioning Edition'],['Creation date','2026'],['Governed state',`${model.condition} / ${model.freshness}`],['Medium','Responsive real-time browser artwork'],['Motion authority',model.motion.reason],['Authority','Observation and governed paper-market research only']].map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        <small>Ownership grants no trading authority, credentials, source-control access, financial guarantee, blockchain title, NFT right, or live-execution capability.</small>
      </div>
    </section>
  </div>;
}

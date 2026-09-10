import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { AUCTION_ROOMS, type AuctionRoom, type AuctionRoomId } from "./auctionRegistry";
import type { AuctionModel } from "./auctionSceneModel";
import { LIVING_CAST } from "./livingCast";
import { MUSEUM_PORTRAIT_PRESENTATION } from "./museumPortraitPresentation";
import { activateDialog, activateNorthstarDialog, requestDialogClose } from "./dialogAccessibility";
import type { ExpansionSnapshot } from "./ExpansionWingSnapshotContext";
import { roomOutput, type MuseumOutput } from "./museumLiveBinding";

const money = (value: number | null) => value === null ? "UNKNOWN" : value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export default function AuctionFactory({ model, snapshot, overview, onOpenRoom }: { model: AuctionModel; snapshot: ExpansionSnapshot | null; overview: unknown; onOpenRoom: (id: AuctionRoomId, opener?: HTMLElement) => void }) {
  const levels = [AUCTION_ROOMS.slice(0, 5), AUCTION_ROOMS.slice(5, 10), AUCTION_ROOMS.slice(10)];
  const route = ["radar","research","external","committee","skeptic","risk","paper","portfolio","monitoring","learning"] as const;
  const activeRouteIndex = model.activeRoom ? route.indexOf(model.activeRoom as typeof route[number]) : -1;
  const shiftPerspective = (event: React.PointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--parallax-x", `${((event.clientX - bounds.left) / bounds.width - .5) * 2}`);
    event.currentTarget.style.setProperty("--parallax-y", `${((event.clientY - bounds.top) / bounds.height - .5) * 2}`);
  };

  return <div className={`auction-factory auction-light--${model.lighting} ${model.motion.ambient ? "has-ambient-motion" : "is-motion-frozen"} ${model.motion.evidence ? "has-evidence-motion" : ""}`} data-testid="auction-factory" data-motion-reason={model.motion.reason} onPointerMove={shiftPerspective} onPointerLeave={(event) => { event.currentTarget.style.setProperty("--parallax-x", "0"); event.currentTarget.style.setProperty("--parallax-y", "0"); }}>
    <div className="auction-atmosphere" aria-hidden="true"><i/><i/><i/></div>
    <header className="auction-house-mark"><span>IIOS PRIVATE INTELLIGENCE WORKS · OBSERVATION HOUSE 01</span><strong>{model.quiet ? "THE HOUSE IS QUIET" : "A VERIFIED RECEIPT IS MOVING"}</strong><small>{model.quiet ? "No theater. No invented motion. The house remains attentive." : "Movement follows the latest complete governed event."}</small></header>
    <div className="auction-building" data-testid="auction-building" aria-label="Interactive multi-level architectural cutaway of the IIOS factory">
      <div className="auction-roofline" aria-hidden="true"><i/><i/><i/><span>THE FAMILY FACTORY · EST. 2026</span></div>
      <div className="auction-service-core" aria-hidden="true"><span>IIOS</span><i/><i/><i/></div>
      {levels.map((rooms, levelIndex) => <section className={`auction-level auction-level--${levelIndex + 1}`} key={levelIndex} aria-label={`Factory level ${levelIndex + 1}`}>
        <div className="auction-level__legend" aria-hidden="true"><span>0{3 - levelIndex}</span><b>{["INTELLIGENCE & CONTEXT", "DELIBERATION & CONTROL", "STEWARDSHIP & MEMORY"][levelIndex]}</b></div>
        <div className="auction-level__rooms">{rooms.map((room) => {
          const index = AUCTION_ROOMS.indexOf(room);
          return <Room key={room.id} room={room} index={index} state={model.rooms[room.id]} output={roomOutput(room.id, snapshot, overview)} open={(opener) => onOpenRoom(room.id, opener)}/>;
        })}</div>
      </section>)}
      <div className="auction-evidence-spine" aria-hidden="true"><i/><i/><i/><span>EVIDENCE LIFT</span></div>
      <div className={`auction-max-walkway ${model.activeRoom ? "is-watching" : ""}`} data-testid="auction-max"><div className="auction-walkway-rail" aria-hidden="true"/><CinematicCharacterPortrait characterKey="max" variant="boss"/><div><small>FOREMAN / OBSERVER</small><b>MAX’S WALKWAY</b><span>{model.quiet ? "Quiet-floor patrol" : `Watching ${model.activeRoom?.toUpperCase()}`}</span></div></div>
      <div className={`auction-route ${activeRouteIndex >= 0 ? "has-receipt" : ""}`} aria-hidden="true">{["Radar","Research","External","Committee","Skeptic","Risk","Paper","Portfolio","Monitor","Learning"].map((step, index) => <span key={step} className={activeRouteIndex >= index ? "is-lit" : ""}><i/>{step}</span>)}</div>
      <div className="auction-foundation" aria-hidden="true"><i/><i/><i/><span>READ MODEL · SANITIZED TELEMETRY · ZERO EXECUTION AUTHORITY</span></div>
    </div>
    <aside className="auction-activity-legend" aria-label="Factory activity legend"><span className="is-ambient"><i/>Ambient factory activity</span><span className="is-evidence"><i/>Evidence-driven case movement</span><span className="is-closed"><i/>Market closed</span><span className="is-failed"><i/>Failed closed</span></aside>
    <div className="auction-ambient-work" aria-label="Ambient presentation only; no evidence or case movement"><span>FILING</span><span>INSPECTION</span><span>MAX NIGHT WATCH</span><strong>AMBIENT ONLY · CASE ROUTE FROZEN</strong></div>
    <section className="auction-status-rail" aria-label="Governed factory status">
      <div><span>HOUSE CONDITION</span><strong>{model.condition} / {model.freshness}</strong></div>
      <div><span>MARKET VALIDATION</span><strong>{model.marketValidation}</strong></div>
      <div><span>PAPER NAV</span><strong>{money(model.nav)}</strong></div>
      <div><span>TELEMETRY</span><strong>{model.safety.telemetryReadOnly ? "SANITIZED / OBSERVING" : "LOCKED"}</strong></div>
      <div><span>LIVE EXECUTION</span><strong>FALSE</strong></div>
    </section>
  </div>;
}

export function NorthstarAuctionFactory({ model, outputs, onOpenRoom }: { model: AuctionModel; outputs: Record<AuctionRoomId, MuseumOutput>; onOpenRoom: (id: AuctionRoomId, opener?: HTMLElement) => void }) {
  const levels = [AUCTION_ROOMS.slice(0, 5), AUCTION_ROOMS.slice(5, 10), AUCTION_ROOMS.slice(10)];
  const route = ["radar","research","external","committee","skeptic","risk","paper","portfolio","monitoring","learning"] as const;
  const activeRouteIndex = model.activeRoom ? route.indexOf(model.activeRoom as typeof route[number]) : -1;
  const shiftPerspective = (event: React.PointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--parallax-x", `${((event.clientX - bounds.left) / bounds.width - .5) * 2}`);
    event.currentTarget.style.setProperty("--parallax-y", `${((event.clientY - bounds.top) / bounds.height - .5) * 2}`);
  };

  return <div className={`auction-factory auction-light--${model.lighting} ${model.motion.ambient ? "has-ambient-motion" : "is-motion-frozen"} ${model.motion.evidence ? "has-evidence-motion" : ""}`} data-testid="auction-factory" data-motion-reason={model.motion.reason} onPointerMove={shiftPerspective} onPointerLeave={(event) => { event.currentTarget.style.setProperty("--parallax-x", "0"); event.currentTarget.style.setProperty("--parallax-y", "0"); }}>
    <div className="auction-atmosphere" aria-hidden="true"><i/><i/><i/></div>
    <header className="auction-house-mark"><span>IIOS PRIVATE INTELLIGENCE WORKS · OBSERVATION HOUSE 01</span><strong>{model.quiet ? "THE HOUSE IS QUIET" : "A VERIFIED RECEIPT IS MOVING"}</strong><small>{model.quiet ? "No theater. No invented motion. The house remains attentive." : "Movement follows the latest complete governed event."}</small></header>
    <div className="auction-building" data-testid="auction-building" aria-label="Interactive multi-level architectural cutaway of the IIOS factory">
      <div className="northstar-service-decoration" aria-hidden="true"><div className="auction-service-core"><span>IIOS</span><i/><i/><i/></div><div className="auction-evidence-spine"><i/><i/><i/><span>EVIDENCE LIFT</span></div>
      <div className="auction-roofline" aria-hidden="true"><i/><i/><i/><span>THE FAMILY FACTORY · EST. 2026</span></div>
      <div className={`auction-route ${activeRouteIndex >= 0 ? "has-receipt" : ""}`} aria-hidden="true">{["Radar","Research","External","Committee","Skeptic","Risk","Paper","Portfolio","Monitor","Learning"].map((step, index) => <span key={step} className={activeRouteIndex >= index ? "is-lit" : ""}><i/>{step}</span>)}</div>
      <div className="auction-foundation" aria-hidden="true"><i/><i/><i/><span>READ MODEL · SANITIZED TELEMETRY · ZERO EXECUTION AUTHORITY</span></div>
      </div>
      {levels.map((rooms, levelIndex) => <section className={`auction-level auction-level--${levelIndex + 1}`} key={levelIndex} aria-label={`Factory level ${levelIndex + 1}`}>
        <div className="auction-level__legend" aria-hidden="true"><span>0{3 - levelIndex}</span><b>{["INTELLIGENCE & CONTEXT", "DELIBERATION & CONTROL", "STEWARDSHIP & MEMORY"][levelIndex]}</b></div>
        <div className="auction-level__rooms">{rooms.map((room) => {
          const index = AUCTION_ROOMS.indexOf(room);
          return <NorthstarRoom key={room.id} room={room} index={index} state={model.rooms[room.id]} output={outputs[room.id]} open={(opener) => onOpenRoom(room.id, opener)}/>;
        })}</div>
      </section>)}
      <div className={`auction-max-walkway ${model.activeRoom ? "is-watching" : ""}`} data-testid="auction-max"><div className="auction-walkway-rail" aria-hidden="true"/><CinematicCharacterPortrait characterKey="max" variant="boss"/><div><small>FOREMAN / OBSERVER</small><b>MAX’S WALKWAY</b><span>{model.quiet ? "Quiet-floor patrol" : `Watching ${model.activeRoom?.toUpperCase()}`}</span></div></div>
    </div>
    <aside className="auction-activity-legend" aria-label="Factory activity legend"><span className="is-ambient"><i/>Ambient factory activity</span><span className="is-evidence"><i/>Evidence-driven case movement</span><span className="is-closed"><i/>Market closed</span><span className="is-failed"><i/>Failed closed</span></aside>
    <div className="auction-ambient-work" aria-label="Ambient presentation only; no evidence or case movement"><span>FILING</span><span>INSPECTION</span><span>MAX NIGHT WATCH</span><strong>AMBIENT ONLY · CASE ROUTE FROZEN</strong></div>
    <section className="auction-status-rail" aria-label="Governed factory status">
      <div><span>HOUSE CONDITION</span><strong>{model.condition} / {model.freshness}</strong></div>
      <div><span>MARKET VALIDATION</span><strong>{model.marketValidation}</strong></div>
      <div><span>PAPER NAV</span><strong>{money(model.nav)}</strong></div>
      <div><span>TELEMETRY</span><strong>{model.safety.telemetryReadOnly ? "SANITIZED / OBSERVING" : "LOCKED"}</strong></div>
      <div><span>LIVE EXECUTION</span><strong>FALSE</strong></div>
    </section>
  </div>;
}

function Room({ room, index, state, output, open }: { room: AuctionRoom; index: number; state: string; output: MuseumOutput; open: (opener: HTMLElement) => void }) {
  const [artFailed, setArtFailed] = useState(false);
  const character = room.characterKeys[0];
  return <button className={`auction-room auction-room--${room.id} auction-room--${state}`} data-testid="auction-room" data-room-id={room.id} data-silhouette={room.silhouette} style={{ "--room-index": index } as React.CSSProperties} onClick={(event) => open(event.currentTarget)} aria-label={`Open ${room.label}; ${state}; ${room.silhouette}`}>
    <span className="auction-room__number">{String(index + 1).padStart(2, "0")}</span><div className="auction-room__identity"><b>{room.shortLabel}</b><small>{state.toUpperCase()}</small></div>
    <div className="auction-room__set" aria-hidden="true"><span className="auction-room__lamp"/><span className="auction-room__window"/><span className="auction-room__desk"><i/><i/><i/></span><span className="auction-room__machine"><i/><i/><i/></span><span className="auction-room__artifact"/></div>
    {character && !artFailed ? <div className="auction-room__character" onError={() => setArtFailed(true)}><CinematicCharacterPortrait characterKey={character} variant="scene" active={state === "active"}/></div> : null}
    <span className="auction-room__output"><b>{output.state.replaceAll("_", " ")}</b><small>{output.value}</small></span>{room.guests.length ? <em>{room.guests.join(" · ")}</em> : null}
  </button>;
}

// Explicit native tab eligibility is isolated from the permanent Room graph.
function NorthstarRoom({ room, index, state, output, open }: { room: AuctionRoom; index: number; state: string; output: MuseumOutput; open: (opener: HTMLElement) => void }) {
  const [artFailed, setArtFailed] = useState(false);
  const character = room.characterKeys[0];
  return <button type="button" tabIndex={0} className={`auction-room auction-room--${room.id} auction-room--${state}`} data-testid="auction-room" data-room-id={room.id} data-silhouette={room.silhouette} style={{ "--room-index": index } as React.CSSProperties} onFocus={(event) => {
    const card = event.currentTarget;
    // Scroll the genuinely focused control, never assign focus or rewrite order.
    // Exact post-dialog restoration must retain the saved document position.
    if (card.matches(':focus-visible') && !card.hasAttribute('data-northstar-restored-focus')) card.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
  }} onClick={(event) => open(event.currentTarget)} aria-label={`Open ${room.label}; ${state}; ${room.silhouette}`}>
    <span className="auction-room__number">{String(index + 1).padStart(2, "0")}</span><div className="auction-room__identity"><b>{room.shortLabel}</b><small>{state.toUpperCase()}</small></div>
    <div className="auction-room__set" aria-hidden="true"><span className="auction-room__lamp"/><span className="auction-room__window"/><span className="auction-room__desk"><i/><i/><i/></span><span className="auction-room__machine"><i/><i/><i/></span><span className="auction-room__artifact"/></div>
    {character && !artFailed ? <div className="auction-room__character" onError={() => setArtFailed(true)}><CinematicCharacterPortrait characterKey={character} variant="scene" active={state === "active"}/></div> : null}
    <span className="auction-room__output"><b>{output.state.replaceAll("_", " ")}</b><small>{output.value}</small></span>{room.guests.length ? <em>{room.guests.join(" · ")}</em> : null}
  </button>;
}

export function RoomView({ roomId, model, snapshot, overview, opener, close }: { roomId: AuctionRoomId; model: AuctionModel; snapshot: ExpansionSnapshot | null; overview: unknown; opener: HTMLElement | null; close: () => void }) {
  const room = AUCTION_ROOMS.find((candidate) => candidate.id === roomId)!;
  const dialogRef = useRef<HTMLDivElement>(null);
  const surfaceRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const titleId = `auction-room-title-${room.id}`;
  const descriptionId = `auction-room-description-${room.id}`;
  const output = roomOutput(roomId, snapshot, overview);
  const singleCast = room.characterKeys.length === 1 && room.guests.length === 0;

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    const initialFocus = headingRef.current;
    if (!dialog || !initialFocus || !dialog.parentElement) return;
    surfaceRef.current?.scrollTo({ top: 0, left: 0, behavior: "instant" });
    const background = Array.from(dialog.parentElement.children).filter((element): element is HTMLElement => element instanceof HTMLElement && element !== dialog);
    return activateDialog({ dialog, initialFocus, opener, background, close, documentTarget: document });
  }, [close, opener, roomId]);

  return <div ref={dialogRef} className={`auction-room-modal auction-room-modal--${room.id}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} tabIndex={-1} onMouseDown={close}>
    <section ref={surfaceRef} onMouseDown={(event) => event.stopPropagation()}>
      <div className="auction-interior-architecture" aria-hidden="true"><i/><i/><i/><span/></div>
      <button className="auction-close" onClick={() => requestDialogClose(close)} aria-label={`Close ${room.label}`}>×</button>
      <header className="auction-interior-heading"><span>{room.shortLabel} / {model.rooms[room.id].toUpperCase()}</span><h2 ref={headingRef} tabIndex={-1} id={titleId}>{room.label}</h2><p id={descriptionId}>{room.purpose}</p><small>{room.silhouette} · {room.light}</small></header>
      <div className={`auction-room-stage ${singleCast ? "is-single-cast" : "is-multi-cast"}`} data-cast-size={room.characterKeys.length + room.guests.length}>
        <div className="auction-room-cinema">{room.characterKeys.map((key) => { const portrait = MUSEUM_PORTRAIT_PRESENTATION[key]; return <article key={key} data-character={key} data-presentation={singleCast ? portrait.mode : "group-card"}>{singleCast ? <img className="auction-single-portrait" src={portrait.asset} width={portrait.sourceWidth} height={portrait.sourceHeight} alt={portrait.alt} draggable={false}/> : <CinematicCharacterPortrait characterKey={key} variant="card"/>}<b>{LIVING_CAST[key].displayName}</b><small>{LIVING_CAST[key].governedRole}</small></article>; })}{room.guests.map((guest) => <article className="auction-guest" key={guest}><b>{guest}</b><small>CONTROLLED EXTERNAL INTELLIGENCE</small></article>)}</div>
        {output.state === "UNAVAILABLE" || output.state === "NOT_REPORTED" || output.state === "UNKNOWN" ? <aside className="auction-evidence-stage"><strong>EVIDENCE STAGE QUIET</strong><span>No authenticated current visual output is available.</span><small>The room remains read-only and attentive.</small></aside> : null}
      </div>
      <div className="auction-interior-console" aria-hidden="true"><i/><i/><i/><i/><span>{room.instruments.join(" / ").toUpperCase()}</span></div>
      <details className="auction-technical-details"><summary>Technical details · exact sanitized machine state</summary><dl><div><dt>Sanitized current output</dt><dd>{output.value}</dd></div><div><dt>Latest state</dt><dd>{output.state}</dd></div><div><dt>Sanitized endpoint source</dt><dd>{output.source}</dd></div><div><dt>Evidence timestamp</dt><dd>{output.timestamp ?? "AUTHENTICATED FIELD NOT REPORTED"}</dd></div><div><dt>Freshness</dt><dd>{output.freshness}</dd></div><div><dt>Latest event category</dt><dd>{output.eventCategory ?? "AUTHENTICATED FIELD NOT REPORTED"}</dd></div><div><dt>Count</dt><dd>{output.count ?? "AUTHENTICATED FIELD NOT REPORTED"}</dd></div><div><dt>Blocker</dt><dd>{output.blocker ?? "NONE REPORTED"}</dd></div><div><dt>Room contract</dt><dd>{room.source}</dd></div><div><dt>Quiet behavior</dt><dd>{room.idleBehavior}</dd></div><div><dt>Motion authority</dt><dd>{model.motion.reason}</dd></div><div><dt>Authority</dt><dd>READ-ONLY · NO LEDGER WRITE · NO TRADE EXECUTION · LIVE EXECUTION FALSE</dd></div></dl></details>
    </section>
  </div>;
}

// Isolated named export preserves the permanent dialog build and approved art geometry.
export function NorthstarRoomView({ roomId, model, opener, close, governedContent }: { roomId: AuctionRoomId; model: AuctionModel; opener: HTMLElement | null; close: () => void; governedContent: ReactNode }) {
  const room = AUCTION_ROOMS.find((candidate) => candidate.id === roomId)!;
  const dialogRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const titleId = `auction-room-title-${room.id}`;
  const descriptionId = `auction-room-description-${room.id}`;
  // Canonical session metadata carries no current visual-output image.
  const output = { state: 'UNAVAILABLE' };
  const singleCast = room.characterKeys.length === 1 && room.guests.length === 0;

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    const initialFocus = headingRef.current;
    if (!dialog || !initialFocus || !dialog.parentElement) return;
    bodyRef.current?.scrollTo({ top: 0, left: 0, behavior: "instant" });
    const background = Array.from(dialog.parentElement.children).filter((element): element is HTMLElement => element instanceof HTMLElement && element !== dialog);
    return activateNorthstarDialog({ dialog, initialFocus, opener, background, close, documentTarget: document });
  }, [close, opener, roomId]);

  return <div ref={dialogRef} className={`auction-room-modal northstar-station-backdrop auction-room-modal--${room.id}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} tabIndex={-1} onMouseDown={close}>
    <section className="northstar-station-dialog" onMouseDown={(event) => event.stopPropagation()}>
      <header className="northstar-dialog-header"><div><span>{room.shortLabel} / {model.rooms[room.id].toUpperCase()}</span><h2 ref={headingRef} tabIndex={-1} id={titleId}>{room.label}</h2></div>
      <button className="auction-close" onClick={() => requestDialogClose(close)} aria-label={`Close ${room.label}`}>×</button>
      </header>
      <div ref={bodyRef} className="northstar-dialog-body" tabIndex={0} role="region" aria-label={`${room.label} content`}>
      <div className="auction-interior-architecture" aria-hidden="true"><i/><i/><i/><span/></div>
      <div className="auction-interior-heading"><p id={descriptionId}>{room.purpose}</p><small>{room.silhouette} · {room.light}</small></div>
      <div className={`auction-room-stage ${singleCast ? "is-single-cast" : "is-multi-cast"}`} data-cast-size={room.characterKeys.length + room.guests.length}>
        <div className="auction-room-cinema">{room.characterKeys.map((key) => { const portrait = MUSEUM_PORTRAIT_PRESENTATION[key]; return <article key={key} data-character={key} data-presentation={singleCast ? portrait.mode : "group-card"}>{singleCast ? <img className="auction-single-portrait" src={portrait.asset} width={portrait.sourceWidth} height={portrait.sourceHeight} alt={portrait.alt} draggable={false}/> : <CinematicCharacterPortrait characterKey={key} variant="card"/>}<b>{LIVING_CAST[key].displayName}</b><small>{LIVING_CAST[key].governedRole}</small></article>; })}{room.guests.map((guest) => <article className="auction-guest" key={guest}><b>{guest}</b><small>CONTROLLED EXTERNAL INTELLIGENCE</small></article>)}</div>
        {output.state === "UNAVAILABLE" || output.state === "NOT_REPORTED" || output.state === "UNKNOWN" ? <aside className="auction-evidence-stage"><strong>EVIDENCE STAGE QUIET</strong><span>No authenticated current visual output is available.</span><small>The room remains read-only and attentive.</small></aside> : null}
      </div>
      <div className="auction-interior-console" aria-hidden="true"><i/><i/><i/><i/><span>{room.instruments.join(" / ").toUpperCase()}</span></div>
      {governedContent}
      </div>
    </section>
  </div>;
}

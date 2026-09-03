import { useLayoutEffect, useRef, useState } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { AUCTION_ROOMS, type AuctionRoom, type AuctionRoomId } from "./auctionRegistry";
import type { AuctionModel } from "./auctionSceneModel";
import { LIVING_CAST } from "./livingCast";
import { activateDialog, requestDialogClose } from "./dialogAccessibility";

const money = (value: number | null) => value === null ? "UNKNOWN" : value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export default function AuctionFactory({ model, onOpenRoom }: { model: AuctionModel; onOpenRoom: (id: AuctionRoomId) => void }) {
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
          return <Room key={room.id} room={room} index={index} state={model.rooms[room.id]} open={() => onOpenRoom(room.id)}/>;
        })}</div>
      </section>)}
      <div className="auction-evidence-spine" aria-hidden="true"><i/><i/><i/><span>EVIDENCE LIFT</span></div>
      <div className={`auction-max-walkway ${model.activeRoom ? "is-watching" : ""}`} data-testid="auction-max"><div className="auction-walkway-rail" aria-hidden="true"/><CinematicCharacterPortrait characterKey="max" variant="boss"/><div><small>FOREMAN / OBSERVER</small><b>MAX’S WALKWAY</b><span>{model.quiet ? "Quiet-floor patrol" : `Watching ${model.activeRoom?.toUpperCase()}`}</span></div></div>
      <div className={`auction-route ${activeRouteIndex >= 0 ? "has-receipt" : ""}`} aria-hidden="true">{["Radar","Research","External","Committee","Skeptic","Risk","Paper","Portfolio","Monitor","Learning"].map((step, index) => <span key={step} className={activeRouteIndex >= index ? "is-lit" : ""}><i/>{step}</span>)}</div>
      <div className="auction-foundation" aria-hidden="true"><i/><i/><i/><span>READ MODEL · SANITIZED TELEMETRY · ZERO EXECUTION AUTHORITY</span></div>
    </div>
    <section className="auction-status-rail" aria-label="Governed factory status">
      <div><span>HOUSE CONDITION</span><strong>{model.condition} / {model.freshness}</strong></div>
      <div><span>MARKET VALIDATION</span><strong>{model.marketValidation}</strong></div>
      <div><span>PAPER NAV</span><strong>{money(model.nav)}</strong></div>
      <div><span>TELEMETRY</span><strong>{model.safety.telemetryReadOnly ? "SANITIZED / OBSERVING" : "LOCKED"}</strong></div>
      <div><span>LIVE EXECUTION</span><strong>FALSE</strong></div>
    </section>
  </div>;
}

function Room({ room, index, state, open }: { room: AuctionRoom; index: number; state: string; open: () => void }) {
  const [artFailed, setArtFailed] = useState(false);
  const character = room.characterKeys[0];
  return <button className={`auction-room auction-room--${room.id} auction-room--${state}`} data-testid="auction-room" data-room-id={room.id} data-silhouette={room.silhouette} style={{ "--room-index": index } as React.CSSProperties} onClick={open} aria-label={`Open ${room.label}; ${state}; ${room.silhouette}`}>
    <span className="auction-room__number">{String(index + 1).padStart(2, "0")}</span><div className="auction-room__identity"><b>{room.shortLabel}</b><small>{state.toUpperCase()}</small></div>
    <div className="auction-room__set" aria-hidden="true"><span className="auction-room__lamp"/><span className="auction-room__window"/><span className="auction-room__desk"><i/><i/><i/></span><span className="auction-room__machine"><i/><i/><i/></span><span className="auction-room__artifact"/></div>
    {character && !artFailed ? <div className="auction-room__character" onError={() => setArtFailed(true)}><CinematicCharacterPortrait characterKey={character} variant="scene" active={state === "active"}/></div> : null}
    {room.guests.length ? <em>{room.guests.join(" · ")}</em> : null}
  </button>;
}

export function RoomView({ roomId, model, close }: { roomId: AuctionRoomId; model: AuctionModel; close: () => void }) {
  const room = AUCTION_ROOMS.find((candidate) => candidate.id === roomId)!;
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(typeof document === "undefined" ? null : document.activeElement instanceof HTMLElement ? document.activeElement : null);
  const titleId = `auction-room-title-${room.id}`;
  const descriptionId = `auction-room-description-${room.id}`;

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    const initialFocus = closeRef.current;
    if (!dialog || !initialFocus || !dialog.parentElement) return;
    const background = Array.from(dialog.parentElement.children).filter((element): element is HTMLElement => element instanceof HTMLElement && element !== dialog);
    return activateDialog({ dialog, initialFocus, opener: openerRef.current, background, close, documentTarget: document });
  }, [close]);

  return <div ref={dialogRef} className={`auction-room-modal auction-room-modal--${room.id}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} tabIndex={-1} onMouseDown={close}>
    <section onMouseDown={(event) => event.stopPropagation()}>
      <div className="auction-interior-architecture" aria-hidden="true"><i/><i/><i/><span/></div>
      <button ref={closeRef} className="auction-close" onClick={() => requestDialogClose(close)} aria-label={`Close ${room.label}`}>×</button>
      <header className="auction-interior-heading"><span>{room.shortLabel} / {model.rooms[room.id].toUpperCase()}</span><h2 id={titleId}>{room.label}</h2><p id={descriptionId}>{room.purpose}</p><small>{room.silhouette} · {room.light}</small></header>
      <div className="auction-room-cinema">{room.characterKeys.map((key) => <article key={key}><CinematicCharacterPortrait characterKey={key} variant="card"/><b>{LIVING_CAST[key].displayName}</b><small>{LIVING_CAST[key].governedRole}</small></article>)}{room.guests.map((guest) => <article className="auction-guest" key={guest}><b>{guest}</b><small>CONTROLLED EXTERNAL INTELLIGENCE</small></article>)}</div>
      <div className="auction-interior-console" aria-hidden="true"><i/><i/><i/><i/><span>{room.instruments.join(" / ").toUpperCase()}</span></div>
      <dl><div><dt>Authoritative source</dt><dd>{room.source}</dd></div><div><dt>Current state</dt><dd>{model.rooms[room.id].toUpperCase()}</dd></div><div><dt>Provenance</dt><dd>{model.generatedAt ?? "UNKNOWN"}</dd></div><div><dt>Quiet behavior</dt><dd>{room.idleBehavior}</dd></div><div><dt>Motion authority</dt><dd>{model.motion.reason}</dd></div><div><dt>Authority</dt><dd>READ-ONLY · NO LEDGER WRITE · NO TRADE EXECUTION · LIVE EXECUTION FALSE</dd></div></dl>
    </section>
  </div>;
}

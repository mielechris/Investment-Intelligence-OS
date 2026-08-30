import "./CinematicRoomScene.css";

export type CinematicStation =
  | "radar"
  | "research"
  | "committee"
  | "risk"
  | "paper"
  | "monitoring"
  | "learning";

type Props = {
  station: CinematicStation;
  active?: boolean;
  eventCount?: number;
};

function StationProps({ station }: { station: CinematicStation }) {
  switch (station) {
    case "radar":
      return (
        <>
          <div className="crs-map"><i /><i /><i /><i /><i /></div>
          <div className="crs-screen-wall"><span>9E</span><span>WIRE</span><span>HITS</span></div>
          <div className="crs-console"><b /><b /><b /><b /></div>
        </>
      );
    case "research":
      return (
        <>
          <div className="crs-shelves"><i /><i /><i /><i /><i /><i /></div>
          <div className="crs-research-desk"><span /><span /><em /></div>
          <div className="crs-paper-stack"><i /><i /><i /></div>
        </>
      );
    case "committee":
      return (
        <>
          <div className="crs-committee-table"><i /><i /><i /><i /><i /></div>
          <div className="crs-dossiers"><span /><span /><span /></div>
          <div className="crs-commission-lamp" />
        </>
      );
    case "risk":
      return (
        <>
          <div className="crs-risk-gauge"><i /></div>
          <div className="crs-risk-board"><span /><span /><span /><span /></div>
          <div className="crs-gate-bars"><i /><i /><i /></div>
        </>
      );
    case "paper":
      return (
        <>
          <div className="crs-tape-printer"><i /><i /><i /></div>
          <div className="crs-ledger"><span /><span /><span /><span /></div>
          <div className="crs-cash-drawer"><i /><i /></div>
        </>
      );
    case "monitoring":
      return (
        <>
          <div className="crs-monitor-bank"><span /><span /><span /><span /></div>
          <div className="crs-monitor-chair" />
          <div className="crs-alert-lamp" />
        </>
      );
    case "learning":
      return (
        <>
          <div className="crs-archive"><i /><i /><i /><i /><i /><i /><i /><i /></div>
          <div className="crs-memory-table"><span /><span /><span /></div>
          <div className="crs-record-lamp" />
        </>
      );
  }
}

export default function CinematicRoomScene({
  station,
  active = false,
  eventCount = 0,
}: Props) {
  return (
    <div
      className={`crs-room crs-room--${station} ${active ? "is-active" : ""}`}
      aria-hidden="true"
    >
      <div className="crs-room__ceiling"><i /><i /><i /></div>
      <div className="crs-room__light" />
      <div className="crs-room__smoke"><i /><i /></div>
      <div className="crs-room__backwall" />
      <StationProps station={station} />
      <div className="crs-room__floor" />
      <div className="crs-room__figure"><i /><span /></div>
      <div className="crs-room__event-count">{eventCount > 0 ? String(eventCount).padStart(2, "0") : "—"}</div>
    </div>
  );
}

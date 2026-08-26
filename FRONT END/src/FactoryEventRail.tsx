import { useEffect, useMemo, useState } from "react";
import { adaptLedgerEvents } from "./factoryLedgerAdapter";
import type { RawLedgerEvent } from "./factoryLedgerAdapter";

const API = "http://127.0.0.1:8002";
const POLL_MS = 5000;

type FactoryStatus = {
  activity?: {
    recent_events?: RawLedgerEvent[];
    recent_event_count?: number;
  };
};

type RailState = {
  status: FactoryStatus | null;
  online: boolean;
  error: string | null;
};

async function fetchStatus(): Promise<FactoryStatus> {
  const response = await fetch(`${API}/factory-room/status`);
  if (!response.ok) throw new Error(`/factory-room/status HTTP ${response.status}`);
  return response.json() as Promise<FactoryStatus>;
}

export default function FactoryEventRail() {
  const [state, setState] = useState<RailState>({ status: null, online: false, error: null });

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const status = await fetchStatus();
        if (!active) return;
        setState({ status, online: true, error: null });
      } catch (error) {
        if (!active) return;
        setState((current) => ({
          ...current,
          online: false,
          error: error instanceof Error ? error.message : "Event rail request failed",
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

  const adapted = useMemo(
    () => adaptLedgerEvents(state.status?.activity?.recent_events || []),
    [state.status?.activity?.recent_events]
  );

  const recognized = adapted.filter((entry) => entry.canonical !== null);
  const ignored = adapted.filter((entry) => entry.canonical === null);

  return (
    <section
      style={{
        marginBottom: "22px",
        padding: "16px",
        borderRadius: "15px",
        border: "1px solid rgba(94,128,160,.28)",
        background: "rgba(5,9,14,.94)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
        <div>
          <div style={{ color: "#66829d", fontSize: "9px", letterSpacing: "2px", fontWeight: 900 }}>X2 · LEDGER EVENT RAIL</div>
          <div style={{ marginTop: "5px", fontSize: "18px", fontWeight: 900 }}>BACKEND AUDIT → CANONICAL FACTORY EVENTS</div>
        </div>
        <div style={{ textAlign: "right", fontSize: "9px" }}>
          <div style={{ color: state.online ? "#63e6a5" : "#ff6d7c", fontWeight: 900 }}>{state.online ? "EVENT SOURCE LIVE" : "EVENT SOURCE OFFLINE"}</div>
          <div style={{ color: "#6d7e90", marginTop: "4px" }}>{recognized.length} recognized · {ignored.length} ignored</div>
        </div>
      </div>

      <div style={{ color: "#718397", fontSize: "10px", lineHeight: 1.5, marginTop: "9px" }}>
        Only ledger events that match the strict adapter become X2 movement signals. Unknown event types remain visible as ignored and never move a case.
      </div>

      {state.error && <div style={{ color: "#ff8a96", fontSize: "9px", marginTop: "8px" }}>{state.error}</div>}

      <div style={{ display: "grid", gap: "6px", marginTop: "12px", maxHeight: "260px", overflowY: "auto" }}>
        {adapted.slice(0, 24).map((entry, index) => {
          const canonical = entry.canonical;
          return (
            <div
              key={entry.raw.event_id || `${entry.raw.case_id || "unknown"}-${index}`}
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(110px,.55fr) minmax(150px,1fr) minmax(140px,1fr) minmax(120px,.8fr)",
                gap: "8px",
                alignItems: "center",
                padding: "7px 9px",
                borderRadius: "8px",
                border: canonical ? "1px solid rgba(99,230,165,.18)" : "1px solid rgba(232,201,107,.18)",
                background: canonical ? "rgba(10,31,26,.42)" : "rgba(31,27,13,.34)",
                fontSize: "8px",
              }}
            >
              <div style={{ color: "#98a9b9", overflow: "hidden", textOverflow: "ellipsis" }}>{entry.raw.case_id || "UNKNOWN CASE"}</div>
              <div style={{ color: "#6e8194", overflow: "hidden", textOverflow: "ellipsis" }}>{entry.raw.event_type || "UNKNOWN EVENT"}</div>
              <div style={{ color: canonical ? "#bff9dc" : "#e8c96b", fontWeight: 900 }}>{canonical?.eventType || "IGNORED"}</div>
              <div style={{ color: "#6c8296" }}>{entry.zone || "NO FACTORY ZONE"}</div>
            </div>
          );
        })}
        {!adapted.length && (
          <div style={{ color: "#64778a", fontSize: "10px", padding: "10px 0" }}>
            No recent ledger events are currently available in the backend activity window.
          </div>
        )}
      </div>
    </section>
  );
}

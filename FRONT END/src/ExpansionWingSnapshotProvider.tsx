import { type ReactNode, useEffect, useMemo, useState } from "react";
import { type ExpansionSnapshot, SnapshotContext, type TruthState } from "./ExpansionWingSnapshotContext";

const LIVE_READ_ONLY = import.meta.env.VITE_EXPANSION_WING_LIVE_READONLY === "1" && import.meta.env.VITE_BACKEND_RECOVERY_GREEN === "1";
const ENDPOINT = LIVE_READ_ONLY
  ? (import.meta.env.VITE_EXPANSION_WING_READONLY_ENDPOINT || "http://127.0.0.1:8002/expansion-wing/status")
  : "/fixtures/expansion-wing.json";

export function ExpansionWingSnapshotProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<ExpansionSnapshot | null>(null);
  const [connection, setConnection] = useState<TruthState>("UNKNOWN");
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const load = async () => {
      try {
        const response = await fetch(ENDPOINT, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error(String(response.status));
        const payload = await response.json() as ExpansionSnapshot;
        if (active) { setSnapshot(payload); setConnection("CURRENT"); }
      } catch (error) {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) { setSnapshot(null); setConnection("UNAVAILABLE"); }
      }
    };
    const initial = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(() => void load(), 15_000);
    return () => { active = false; window.clearTimeout(initial); window.clearInterval(timer); controller.abort(); };
  }, []);
  const value = useMemo(() => ({ snapshot, connection, fixtureMode: !LIVE_READ_ONLY }), [snapshot, connection]);
  return <SnapshotContext.Provider value={value}>{children}</SnapshotContext.Provider>;
}

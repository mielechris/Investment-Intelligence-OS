import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { type ExpansionSnapshot, SnapshotContext, type TruthState } from "./ExpansionWingSnapshotContext";

const LIVE_READ_ONLY = import.meta.env.VITE_EXPANSION_WING_LIVE_READONLY === "1" && import.meta.env.VITE_BACKEND_RECOVERY_GREEN === "1";
const FIXTURE_MODE = import.meta.env.VITE_EXPANSION_WING_FIXTURE === "1";
const ENDPOINT = LIVE_READ_ONLY
  ? (import.meta.env.VITE_EXPANSION_WING_READONLY_ENDPOINT || "http://127.0.0.1:8002/expansion-wing/status")
  : "/fixtures/expansion-wing.json";
const POLL_MS = 15_000;
const MAX_BACKOFF_MS = 60_000;

function immutableSnapshot<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.freeze(value);
    Object.values(value).forEach((item) => immutableSnapshot(item));
  }
  return value;
}

export function ExpansionWingSnapshotProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<ExpansionSnapshot | null>(null);
  const [connection, setConnection] = useState<TruthState>("UNKNOWN");
  const receivedAt = useRef<number | null>(null);
  const [snapshotAgeSeconds, setSnapshotAgeSeconds] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let timer: number | undefined;
    let failures = 0;
    const load = async () => {
      if (!active || controller) return;
      const requestController = new AbortController();
      controller = requestController;
      try {
        const response = await fetch(ENDPOINT, { signal: requestController.signal, cache: "no-store" });
        if (!response.ok) throw new Error(String(response.status));
        const payload = immutableSnapshot(await response.json() as ExpansionSnapshot);
        if (active) {
          const now = Date.now();
          failures = 0; setSnapshot(payload); receivedAt.current = now; setSnapshotAgeSeconds(0); setConnection("CURRENT");
        }
      } catch (error) {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) {
          failures += 1; setSnapshotAgeSeconds(receivedAt.current === null ? null : Math.max(0, Math.floor((Date.now() - receivedAt.current) / 1000)));
          setConnection(receivedAt.current === null ? "UNAVAILABLE" : "STALE");
        }
      } finally {
        if (controller === requestController) controller = null;
        if (active) timer = window.setTimeout(() => void load(), Math.min(MAX_BACKOFF_MS, POLL_MS * 2 ** failures));
      }
    };
    void load();
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer); controller?.abort(); };
  }, []);
  const value = useMemo(() => ({ snapshot, connection, fixtureMode: FIXTURE_MODE, snapshotAgeSeconds }), [snapshot, connection, snapshotAgeSeconds]);
  return <SnapshotContext.Provider value={value}>{children}</SnapshotContext.Provider>;
}

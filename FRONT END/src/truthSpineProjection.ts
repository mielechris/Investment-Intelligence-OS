export type Projection = {
  schema: string; classification: "REPLAY"; content_hash: string; topology_identity: string;
  generation_id: string; release_id: string; runtime_id: string; ledger_identity: string;
  session_id: string; observed_at: string; phase: string; case_id: string; trace_id: string;
  case_state: string; committee_state: string; reason_codes: string[]; event_ids: string[];
  evidence_ids: string[]; receipt_id: string; authority: Record<string, boolean>;
  risk: { state: string; decision: string }; paper: { state: string; orders: number };
  outcome: { state: string }; memory: { state: string; admissions: number };
  paper_fund: { nav: string | null; cash: string | null; source: string; reconciled_at: string | null };
  agent_states: Record<string, { name: string; invoked: boolean; reason: string }>;
};
function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (value !== null && typeof value === "object") return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([k, v]) => [k, stable(v)]));
  return value;
}
export function projectionSelection(x: Projection): string {
  return JSON.stringify([x.topology_identity, x.release_id, x.runtime_id, x.ledger_identity, x.generation_id, x.session_id]);
}
export async function validateProjection(value: unknown, selected: string | null): Promise<Projection> {
  if (!value || typeof value !== "object") throw new Error("UNAVAILABLE");
  const x = value as Projection;
  const { content_hash, ...unsigned } = x;
  const ascii = JSON.stringify(stable(unsigned)).replace(/[\u0080-\uffff]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
  const bytes = new TextEncoder().encode(ascii + "\n");
  const observed = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), n => n.toString(16).padStart(2, "0")).join("");
  const age = Date.now() - Date.parse(x.observed_at);
  const keys = ["broker", "paper_order", "promotion", "ledger_write", "live_execution"];
  if (x.schema !== "iios-truth-projection-v1" || x.classification !== "REPLAY" || content_hash !== observed
      || (selected !== null && selected !== projectionSelection(x)) || !Number.isFinite(age) || age < 0 || age > 15000
      || ![x.topology_identity, x.ledger_identity, x.receipt_id].every(v => typeof v === "string" && /^[a-f0-9]{64}$/.test(v))
      || ![x.release_id, x.runtime_id, x.generation_id, x.session_id, x.trace_id, x.case_id].every(v => typeof v === "string" && v.length > 0)
      || !["WATCH", "NO_TRADE"].includes(x.case_state) || x.phase !== "SESSION_CLOSED"
      || !Array.isArray(x.reason_codes) || !x.reason_codes.length || !x.agent_states
      || x.risk?.decision !== "NO_PAPER_AUTHORITY" || x.paper?.state !== "ABSTAINED"
      || x.outcome?.state !== "OUTCOME_PENDING" || !x.paper_fund
      || !x.authority || Object.keys(x.authority).length !== keys.length || keys.some(k => x.authority[k] !== false)
      || !x.event_ids?.length || !x.evidence_ids?.length || x.paper?.orders !== 0 || x.memory?.admissions !== 0) throw new Error("UNAVAILABLE");
  return x;
}

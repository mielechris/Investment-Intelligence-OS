import { adaptLedgerEvents, type RawLedgerEvent } from "./factoryLedgerAdapter";
import type { FactoryEventType } from "./factoryMovement";

export type DeskActivityState = "BUSY" | "RECENT" | "IDLE" | "UNKNOWN";
export type DeskActivity = { key:string; label:string; state:DeskActivityState; lastEvent?:string; lastAt?:string; caseId?:string; };
export type ActivitySummary = { recognized:number; movable:number; ignored:number; caseEvents:number; systemEvents:number; latestCanonical:FactoryEventType|null; desks:DeskActivity[]; };

const DESKS = [
  ["policy","Policy"],["macro","Macro"],["fundamentals","Fundamentals"],["market_structure","Market Structure"],
  ["commodities","Commodities"],["geo_weather","Geo / Weather"],["skeptic","Skeptic / Red"],["portfolio","Portfolio"]
] as const;

function deskKey(raw: RawLedgerEvent): string | null {
  const payload = raw.payload || {};
  const candidates = [payload.agent_key,payload.agent,payload.desk,payload.specialist,payload.role,raw.event_type];
  const text = candidates.map((v)=>String(v||"").toLowerCase()).join(" ");
  if (text.includes("market") && text.includes("structure")) return "market_structure";
  if (text.includes("geo") || text.includes("weather")) return "geo_weather";
  if (text.includes("fundamental")) return "fundamentals";
  if (text.includes("commodit")) return "commodities";
  if (text.includes("skeptic") || text.includes("red_team") || text.includes("red team")) return "skeptic";
  if (text.includes("portfolio")) return "portfolio";
  if (text.includes("policy")) return "policy";
  if (text.includes("macro")) return "macro";
  return null;
}

export function buildActivitySummary(events: readonly RawLedgerEvent[], nowMs = Date.now()): ActivitySummary {
  const adapted = adaptLedgerEvents(events);
  const deskLatest = new Map<string, RawLedgerEvent>();
  for (const entry of adapted) {
    const key = deskKey(entry.raw);
    if (key && !deskLatest.has(key)) deskLatest.set(key, entry.raw);
  }
  const desks: DeskActivity[] = DESKS.map(([key,label]) => {
    const event = deskLatest.get(key);
    if (!event) return { key,label,state:"IDLE" };
    const at = Date.parse(String(event.created_at||""));
    const age = Number.isFinite(at) ? Math.max(0,(nowMs-at)/1000) : Infinity;
    const type = String(event.event_type||"").toUpperCase();
    const busy = /(START|ASSIGNED|THINK|RUNNING|OPENED)/.test(type) && !/(COMPLETE|FINISH|CLOSED)/.test(type);
    const state:DeskActivityState = busy && age <= 300 ? "BUSY" : age <= 300 ? "RECENT" : "IDLE";
    return { key,label,state,lastEvent:event.event_type,lastAt:event.created_at,caseId:event.case_id };
  });
  const recognized = adapted.filter((x)=>x.recognizedType!==null);
  return {
    recognized:recognized.length,
    movable:adapted.filter((x)=>x.movementEligible).length,
    ignored:adapted.filter((x)=>x.recognizedType===null).length,
    caseEvents:adapted.filter((x)=>Boolean(x.raw.case_id)).length,
    systemEvents:adapted.filter((x)=>!x.raw.case_id).length,
    latestCanonical:recognized[0]?.recognizedType || null,
    desks,
  };
}

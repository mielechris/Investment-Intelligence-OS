export type ThesisIntegrity =
  | "INTACT"
  | "EARLY_BUT_INTACT"
  | "MATERIAL_CHANGE"
  | "THESIS_BROKEN"
  | "UNKNOWN";

export type ThesisMonitorProjectionInput = {
  thesis_status?: string;
  flags?: string[];
  falsifiers_triggered?: string[];
  catalyst_status?: string;
  observed_return_pct?: number | null;
  created_at?: string;
};

const MATERIAL_FLAGS = new Set([
  "CATALYST_MISSED",
  "UPDATE_EVIDENCE_STALE",
  "UPDATE_EVIDENCE_CONFLICT",
  "DRAWDOWN_TRIGGERED",
]);

export function projectThesisIntegrity(
  latest?: ThesisMonitorProjectionInput | null,
): ThesisIntegrity {
  if (!latest) return "UNKNOWN";

  const status = String(latest.thesis_status || "").toUpperCase();
  const flags = (latest.flags || []).map((flag) => String(flag).toUpperCase());

  if (
    status === "THESIS_BROKEN" ||
    flags.includes("FALSIFIER_TRIGGERED") ||
    (latest.falsifiers_triggered || []).length > 0
  ) {
    return "THESIS_BROKEN";
  }

  if (
    status === "REUNDERWRITE_REQUIRED" ||
    flags.some((flag) => MATERIAL_FLAGS.has(flag))
  ) {
    return "MATERIAL_CHANGE";
  }

  if (
    status === "INTACT" &&
    (String(latest.catalyst_status || "UNKNOWN").toUpperCase() === "UNKNOWN" ||
      flags.length > 0)
  ) {
    return "EARLY_BUT_INTACT";
  }

  if (status === "INTACT") return "INTACT";
  return "UNKNOWN";
}

export function thesisIntegrityTone(state: ThesisIntegrity) {
  if (state === "INTACT") return "iios-state-clear";
  if (state === "EARLY_BUT_INTACT") return "iios-state-watch";
  if (state === "MATERIAL_CHANGE" || state === "THESIS_BROKEN") {
    return "iios-state-block";
  }
  return "iios-state-idle";
}

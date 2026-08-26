import { useEffect, useMemo, useState } from "react";

const API = "http://localhost:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type LaneState = {
  label: string;
  total_records: number;
  admitted_records: number;
  latest_record?: HardDataRecord | null;
};

type HardDataRecord = {
  hard_data_id: string;
  lane: string;
  lane_label: string;
  metric: string;
  value_text: string;
  unit?: string | null;
  period?: string | null;
  source_name: string;
  source_url: string;
  source_kind: string;
  admission_status: string;
  observed_at: string;
  gap_requirement?: string | null;
};

type HardDataStatus = {
  case_id: string;
  lanes: Record<string, LaneState>;
  records: HardDataRecord[];
  admitted_evidence_count: number;
};

const LANE_OPTIONS = [
  ["memory_pricing", "Memory Pricing"],
  ["supply_inventory", "Supply / Inventory"],
  ["hyperscaler_demand", "Hyperscaler Demand"],
  ["valuation_positioning", "Valuation / Positioning"],
  ["policy", "Policy"],
] as const;

const SOURCE_OPTIONS = [
  ["official", "Official / government"],
  ["company_ir", "Company investor relations"],
  ["regulated_filing", "Regulated filing"],
  ["exchange", "Exchange"],
  ["market_data", "Market-data provider"],
  ["licensed_data", "Licensed data"],
  ["research", "Research publication"],
  ["manual_observation", "Manual observation · context only"],
] as const;

function HardDataPanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [status, setStatus] = useState<HardDataStatus | null>(null);
  const [lane, setLane] = useState("memory_pricing");
  const [metric, setMetric] = useState("");
  const [valueText, setValueText] = useState("");
  const [unit, setUnit] = useState("");
  const [period, setPeriod] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceKind, setSourceKind] = useState("market_data");
  const [notes, setNotes] = useState("");
  const [verified, setVerified] = useState(false);
  const [permitted, setPermitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Hard data stays segregated until source verification and permitted-use attestations are complete.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => (current === next ? current : next));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const load = async (selectedCaseId: string) => {
    const response = await fetch(`${API}/hard-data/${selectedCaseId}`);
    if (!response.ok) throw new Error(`Hard-data status failed: ${response.status}`);
    setStatus((await response.json()) as HardDataStatus);
  };

  useEffect(() => {
    if (!caseId) {
      setStatus(null);
      return;
    }
    void load(caseId).catch((error) => setMessage(error instanceof Error ? error.message : "Hard-data status unavailable"));
  }, [caseId]);

  const currentLaneLabel = useMemo(
    () => LANE_OPTIONS.find(([key]) => key === lane)?.[1] ?? lane,
    [lane]
  );

  const autoCapture = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Capturing the current public market snapshot into the governed hard-data ledger...");
    try {
      const response = await fetch(`${API}/hard-data/${caseId}/auto-capture`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json() as { records_added?: HardDataRecord[]; quote?: { status?: string } };
      setMessage(`Auto-capture complete: ${data.records_added?.length ?? 0} admitted market record(s).`);
      await load(caseId);
    } catch (error) {
      setMessage(error instanceof Error ? `Auto-capture error: ${error.message}` : "Auto-capture failed");
    } finally {
      setBusy(false);
    }
  };

  const addRecord = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage(`Recording verified ${currentLaneLabel} observation...`);
    try {
      const response = await fetch(`${API}/hard-data/${caseId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lane,
          metric,
          value_text: valueText,
          unit,
          period,
          observed_at: observedAt || undefined,
          source_name: sourceName,
          source_url: sourceUrl,
          source_kind: sourceKind,
          notes,
          verified_against_source: verified,
          permitted_use: permitted,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const record = (await response.json()) as HardDataRecord;
      setMessage(`${record.lane_label}: ${record.metric} recorded as ${record.admission_status}. Future Gap Hunter rounds will see admitted records automatically.`);
      setMetric("");
      setValueText("");
      setUnit("");
      setPeriod("");
      setObservedAt("");
      setSourceName("");
      setSourceUrl("");
      setNotes("");
      setVerified(false);
      setPermitted(false);
      await load(caseId);
    } catch (error) {
      setMessage(error instanceof Error ? `Hard-data error: ${error.message}` : "Hard-data record failed");
    } finally {
      setBusy(false);
    }
  };

  if (!caseId) return null;

  const panel = {
    background: "rgba(7, 11, 17, 0.96)",
    border: "1px solid #28313d",
    borderRadius: "14px",
    padding: "22px",
  } as const;
  const small = {
    color: "#758294",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };
  const input = {
    width: "100%",
    boxSizing: "border-box" as const,
    background: "#0d131b",
    border: "1px solid #303b49",
    color: "#f4f4f4",
    borderRadius: "7px",
    padding: "11px 12px",
    fontSize: "13px",
  };

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={{ ...panel, borderColor: "#365c4b" }}>
        <div style={small}>HARD DATA ACQUISITION · PRIMARY / NUMERIC LAYER</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "18px", alignItems: "start", flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: "7px 0 5px" }}>Feed the unresolved gaps with verified hard evidence</h2>
            <div style={{ color: "#8c99a8", fontSize: "13px", maxWidth: "850px", lineHeight: 1.5 }}>
              Pricing, inventory, orders, valuation and policy records remain source-linked. Verified admitted records are automatically available to the next Gap Hunter round; context-only observations cannot resolve a qualification gap.
            </div>
          </div>
          <button onClick={() => void autoCapture()} disabled={busy} style={{ border: "1px solid #47775b", background: "#10261a", color: "#d4f6df", borderRadius: "8px", padding: "12px 16px", fontWeight: 900 }}>
            {busy ? "WORKING..." : "AUTO CAPTURE PUBLIC MARKET SNAPSHOT"}
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(140px, 1fr))", gap: "9px", marginTop: "17px" }}>
          {LANE_OPTIONS.map(([key, label]) => {
            const laneState = status?.lanes?.[key];
            return (
              <div key={key} style={{ ...panel, padding: "13px", background: "#080d11" }}>
                <div style={{ ...small, letterSpacing: "1px" }}>{label}</div>
                <div style={{ marginTop: "8px", fontSize: "19px", fontWeight: 900 }}>{laneState?.admitted_records ?? 0}</div>
                <div style={{ marginTop: "3px", color: "#81909f", fontSize: "11px" }}>admitted · {laneState?.total_records ?? 0} total</div>
              </div>
            );
          })}
        </div>

        <div style={{ ...panel, marginTop: "15px", padding: "16px", background: "#090d12" }}>
          <div style={small}>ADD VERIFIED HARD DATA</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(220px, 1fr))", gap: "9px", marginTop: "11px" }}>
            <select style={input} value={lane} onChange={(event) => setLane(event.target.value)}>
              {LANE_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <select style={input} value={sourceKind} onChange={(event) => setSourceKind(event.target.value)}>
              {SOURCE_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <input style={input} value={metric} onChange={(event) => setMetric(event.target.value)} placeholder="Metric e.g. HBM3E contract price / inventory days / AI capex" />
            <input style={input} value={valueText} onChange={(event) => setValueText(event.target.value)} placeholder="Verified value or concise primary-source fact" />
            <input style={input} value={unit} onChange={(event) => setUnit(event.target.value)} placeholder="Unit (optional)" />
            <input style={input} value={period} onChange={(event) => setPeriod(event.target.value)} placeholder="Period / quarter (optional)" />
            <input style={input} value={observedAt} onChange={(event) => setObservedAt(event.target.value)} placeholder="Observed timestamp ISO-8601 (blank = now)" />
            <input style={input} value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder="Source name" />
          </div>
          <input style={{ ...input, marginTop: "9px" }} value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https:// source URL" />
          <input style={{ ...input, marginTop: "9px" }} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Notes / interpretation boundary (optional)" />
          <label style={{ display: "block", marginTop: "11px", fontSize: "12px" }}>
            <input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} /> I verified this observation against the cited source.
          </label>
          <label style={{ display: "block", marginTop: "8px", fontSize: "12px" }}>
            <input type="checkbox" checked={permitted} onChange={(event) => setPermitted(event.target.checked)} /> I attest this source/data may be used for IIOS research.
          </label>
          <button
            onClick={() => void addRecord()}
            disabled={busy || metric.trim().length < 2 || valueText.trim().length < 1 || sourceName.trim().length < 2 || !sourceUrl.startsWith("https://") || !verified || !permitted}
            style={{ marginTop: "11px", border: "1px solid #4b735f", background: "#11251b", color: "#d7f3df", borderRadius: "7px", padding: "11px 15px", fontWeight: 900 }}
          >
            ADD TO HARD DATA LEDGER
          </button>
        </div>

        <div style={{ marginTop: "13px", color: "#9ba8b6", fontSize: "12px", lineHeight: 1.5 }}>{message}</div>

        {status && status.records.length > 0 && (
          <div style={{ ...panel, marginTop: "15px", padding: "16px", background: "#080c11" }}>
            <div style={small}>RECENT HARD DATA RECORDS · {status.admitted_evidence_count} ADMITTED TO RESEARCH</div>
            {status.records.slice(0, 10).map((record) => (
              <div key={record.hard_data_id} style={{ borderTop: "1px solid #1e2731", padding: "10px 0", marginTop: "8px", fontSize: "12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                  <strong>{record.lane_label} · {record.metric} = {record.value_text}{record.unit ? ` ${record.unit}` : ""}</strong>
                  <span style={{ color: record.admission_status === "ADMITTED" ? "#69cf94" : "#d7b76a", fontWeight: 800 }}>{record.admission_status}</span>
                </div>
                <div style={{ marginTop: "4px", color: "#8593a2" }}>{record.source_name} · {record.source_kind} · {new Date(record.observed_at).toLocaleString()}</div>
                {record.gap_requirement && <div style={{ marginTop: "4px", color: "#a18fca" }}>Addresses: {record.gap_requirement}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default HardDataPanel;

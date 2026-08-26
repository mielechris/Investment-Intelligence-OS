import { useState } from "react";

const API = "http://127.0.0.1:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

export default function NewCaseLauncher() {
  const [topic, setTopic] = useState("");
  const [ticker, setTicker] = useState("");
  const [direction, setDirection] = useState("LONG");
  const [referencePrice, setReferencePrice] = useState("");
  const [intervalMinutes, setIntervalMinutes] = useState("60");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Create a governed paper/shadow case. Live execution remains disabled.");

  const run = async () => {
    setBusy(true);
    setMessage("Collecting evidence and routing the case through the governed factory…");
    try {
      const response = await fetch(`${API}/factory/run-public`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          ticker,
          direction,
          reference_price: referencePrice.trim() ? Number(referencePrice) : undefined,
          interval_minutes: Number(intervalMinutes),
          auto_watch: true,
          analysis_mode: "llm",
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json() as { factory?: { case?: { case_id?: string } }; ingestion?: { successful_sources?: number } };
      const caseId = data.factory?.case?.case_id;
      if (caseId) {
        window.localStorage.setItem(ACTIVE_CASE_KEY, caseId);
        window.dispatchEvent(new Event("iios-active-case-changed"));
      }
      setMessage(caseId ? `Case ${caseId.slice(-8)} created and placed into AUTO WATCH. ${data.ingestion?.successful_sources ?? 0} public sources responded.` : "Governed case completed, but no case ID was returned.");
    } catch (error) {
      setMessage(error instanceof Error ? `Factory error: ${error.message}` : "Factory request failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="native-drawer native-new-case-drawer">
      <summary>+ New Case</summary>
      <div className="native-drawer-body">
        <div className="native-new-case-grid">
          <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Investment thesis" />
          <input value={ticker} onChange={(event) => setTicker(event.target.value)} placeholder="Ticker e.g. MU.US" />
          <select value={direction} onChange={(event) => setDirection(event.target.value)}><option value="LONG">LONG</option><option value="SHORT">SHORT</option><option value="UNSPECIFIED">WATCH ONLY</option></select>
          <input value={referencePrice} onChange={(event) => setReferencePrice(event.target.value)} placeholder="Reference price optional" inputMode="decimal" />
          <select value={intervalMinutes} onChange={(event) => setIntervalMinutes(event.target.value)}><option value="60">Every 1h</option><option value="240">Every 4h</option><option value="720">Every 12h</option><option value="1440">Daily</option></select>
        </div>
        <div className="native-new-case-actions"><button type="button" onClick={() => void run()} disabled={busy || topic.trim().length < 2}>{busy ? "FACTORY WORKING…" : "RUN FACTORY + AUTO WATCH"}</button><span>{message}</span></div>
      </div>
    </details>
  );
}

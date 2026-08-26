import { useEffect, useState } from "react";

const API = "http://127.0.0.1:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type Status = {
  case_id: string;
  ticker: string;
  suggested_source_url?: string | null;
  latest_snapshot?: {
    report_date?: string;
    call_open_interest?: number;
    put_open_interest?: number;
    put_call_oi_ratio?: number | null;
    positioning_bias?: string;
  } | null;
};

function OptionsPositioningVerificationPanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [ticker, setTicker] = useState("");
  const [reportDate, setReportDate] = useState("");
  const [callOi, setCallOi] = useState("");
  const [putOi, setPutOi] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Use this only if automatic OCC open-interest capture is blocked.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => current === next ? current : next);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!caseId) return;
    void fetch(`${API}/options-positioning-verification/${caseId}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json() as Promise<Status>;
      })
      .then((data) => {
        setTicker(data.ticker || "");
        setSourceUrl(data.suggested_source_url || "");
        if (data.latest_snapshot) {
          setReportDate(data.latest_snapshot.report_date || "");
          setCallOi(data.latest_snapshot.call_open_interest == null ? "" : String(data.latest_snapshot.call_open_interest));
          setPutOi(data.latest_snapshot.put_open_interest == null ? "" : String(data.latest_snapshot.put_open_interest));
          setMessage(
            `Latest OCC snapshot loaded. Put/call OI: ${data.latest_snapshot.put_call_oi_ratio ?? "—"} · ${data.latest_snapshot.positioning_bias || "UNKNOWN"}`
          );
        }
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Options-positioning verification unavailable"));
  }, [caseId]);

  const save = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Saving verified OCC options positioning...");
    try {
      const response = await fetch(`${API}/options-positioning-verification/${caseId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_date: reportDate,
          call_open_interest: callOi,
          put_open_interest: putOi,
          source_url: sourceUrl,
          verified_against_source: verified,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json() as {
        source_grade?: string;
        snapshot?: { put_call_oi_ratio?: number | null; positioning_bias?: string };
      };
      setMessage(
        `Options positioning saved as ${result.source_grade || "OCC_VERIFIED_OPTIONS_POSITIONING"}. ` +
        `Put/call OI: ${result.snapshot?.put_call_oi_ratio ?? "—"} · ${result.snapshot?.positioning_bias || "UNKNOWN"}. ` +
        "Refresh Primary Evidence to see the fact update."
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Options-positioning verification failed");
    } finally {
      setBusy(false);
    }
  };

  if (!caseId) return null;

  const panel = {
    background: "rgba(7, 11, 17, 0.97)",
    border: "1px solid #5f526e",
    borderRadius: "14px",
    padding: "22px",
  } as const;
  const input = {
    background: "#0b1118",
    border: "1px solid #31424d",
    borderRadius: "7px",
    color: "#e8eef5",
    padding: "10px 11px",
    minWidth: 0,
  } as const;
  const small = {
    color: "#9d89b8",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={panel}>
        <div style={small}>OPTIONS POSITIONING · OCC VERIFIED FALLBACK</div>
        <h2 style={{ margin: "8px 0 5px" }}>Verify OCC open interest only when automatic capture is blocked</h2>
        <div style={{ color: "#8f9dab", fontSize: "13px", lineHeight: 1.5, maxWidth: "1000px" }}>
          OCC open interest is clearing-level positioning data from the prior settlement. Put/call open interest is context only: options may represent hedges, spreads, or inventory management. This fallback can satisfy only Options Positioning and cannot authorize a trade.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "160px 1fr 1fr 1fr", gap: "10px", marginTop: "16px" }}>
          <div style={{ ...input, color: "#9fb1c4" }}>Ticker: <strong style={{ color: "#e8eef5" }}>{ticker || "—"}</strong></div>
          <input value={reportDate} onChange={(event) => setReportDate(event.target.value)} placeholder="OCC report date YYYY-MM-DD" style={input} />
          <input value={callOi} onChange={(event) => setCallOi(event.target.value)} placeholder="Total call open interest" inputMode="numeric" style={input} />
          <input value={putOi} onChange={(event) => setPutOi(event.target.value)} placeholder="Total put open interest" inputMode="numeric" style={input} />
        </div>

        <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="Official OCC source URL" style={{ ...input, width: "100%", boxSizing: "border-box", marginTop: "10px" }} />

        <label style={{ display: "flex", gap: "9px", alignItems: "center", marginTop: "13px", color: "#b5c0cb", fontSize: "12px" }}>
          <input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} />
          I verified these call and put open-interest totals against the cited OCC source.
        </label>

        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "13px" }}>
          <button onClick={() => void save()} disabled={busy} style={{ border: "1px solid #69547b", background: "#2b1f38", color: "#d9c1ee", borderRadius: "7px", padding: "10px 14px", fontWeight: 900 }}>
            {busy ? "SAVING..." : "SAVE VERIFIED OPTIONS POSITIONING"}
          </button>
          <span style={{ color: "#9ba8b6", fontSize: "12px" }}>{message}</span>
        </div>
      </div>
    </section>
  );
}

export default OptionsPositioningVerificationPanel;

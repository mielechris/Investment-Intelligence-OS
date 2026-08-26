import { useEffect, useState } from "react";

const API = "http://127.0.0.1:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type Status = {
  case_id: string;
  ticker: string;
  suggested_source_url?: string | null;
  latest_snapshot?: {
    settlement_date?: string;
    current_short?: number;
    previous_short?: number | null;
    avg_daily_volume?: number | null;
    days_to_cover?: number | null;
  } | null;
};

function ShortInterestVerificationPanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [ticker, setTicker] = useState("");
  const [settlementDate, setSettlementDate] = useState("");
  const [currentShort, setCurrentShort] = useState("");
  const [previousShort, setPreviousShort] = useState("");
  const [avgDailyVolume, setAvgDailyVolume] = useState("");
  const [daysToCover, setDaysToCover] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Use this only if automatic Nasdaq short-interest capture is blocked.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => current === next ? current : next);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!caseId) return;
    void fetch(`${API}/short-interest-verification/${caseId}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json() as Promise<Status>;
      })
      .then((data) => {
        setTicker(data.ticker || "");
        setSourceUrl(data.suggested_source_url || "");
        if (data.latest_snapshot) {
          setSettlementDate(data.latest_snapshot.settlement_date || "");
          setCurrentShort(data.latest_snapshot.current_short == null ? "" : String(data.latest_snapshot.current_short));
          setPreviousShort(data.latest_snapshot.previous_short == null ? "" : String(data.latest_snapshot.previous_short));
          setAvgDailyVolume(data.latest_snapshot.avg_daily_volume == null ? "" : String(data.latest_snapshot.avg_daily_volume));
          setDaysToCover(data.latest_snapshot.days_to_cover == null ? "" : String(data.latest_snapshot.days_to_cover));
          setMessage("Latest user-verified Nasdaq short-interest snapshot loaded.");
        }
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Short-interest verification unavailable"));
  }, [caseId]);

  const save = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Saving verified Nasdaq short-interest evidence...");
    try {
      const response = await fetch(`${API}/short-interest-verification/${caseId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          settlement_date: settlementDate,
          current_short: currentShort,
          previous_short: previousShort || null,
          avg_daily_volume: avgDailyVolume || null,
          days_to_cover: daysToCover || null,
          source_url: sourceUrl,
          verified_against_source: verified,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json() as { source_grade?: string; gap_resolution_eligible?: boolean };
      setMessage(
        `Short interest saved as ${result.source_grade || "EXCHANGE_VERIFIED_SHORT_INTEREST"}. ` +
        "Refresh Primary Evidence to see the short-interest fact update."
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Short-interest verification failed");
    } finally {
      setBusy(false);
    }
  };

  if (!caseId) return null;

  const panel = {
    background: "rgba(7, 11, 17, 0.97)",
    border: "1px solid #6a5c2c",
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
    color: "#9b8951",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={panel}>
        <div style={small}>SHORT INTEREST · NASDAQ VERIFIED FALLBACK</div>
        <h2 style={{ margin: "8px 0 5px" }}>Verify exchange short interest only when automatic capture is blocked</h2>
        <div style={{ color: "#8f9dab", fontSize: "13px", lineHeight: 1.5, maxWidth: "980px" }}>
          Nasdaq publishes short interest on a periodic settlement schedule. This fallback can satisfy only the Short Interest fact. It cannot resolve options positioning or authorize a trade.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "160px 1fr 1fr", gap: "10px", marginTop: "16px" }}>
          <div style={{ ...input, color: "#9fb1c4" }}>Ticker: <strong style={{ color: "#e8eef5" }}>{ticker || "—"}</strong></div>
          <input value={settlementDate} onChange={(event) => setSettlementDate(event.target.value)} placeholder="Settlement date YYYY-MM-DD" style={input} />
          <input value={currentShort} onChange={(event) => setCurrentShort(event.target.value)} placeholder="Current shares short" inputMode="numeric" style={input} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10px", marginTop: "10px" }}>
          <input value={previousShort} onChange={(event) => setPreviousShort(event.target.value)} placeholder="Previous shares short (optional)" inputMode="numeric" style={input} />
          <input value={avgDailyVolume} onChange={(event) => setAvgDailyVolume(event.target.value)} placeholder="Avg daily volume (optional)" inputMode="numeric" style={input} />
          <input value={daysToCover} onChange={(event) => setDaysToCover(event.target.value)} placeholder="Days to cover (optional)" inputMode="decimal" style={input} />
        </div>
        <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="Official Nasdaq short-interest source URL" style={{ ...input, width: "100%", boxSizing: "border-box", marginTop: "10px" }} />

        <label style={{ display: "flex", gap: "9px", alignItems: "center", marginTop: "13px", color: "#b5c0cb", fontSize: "12px" }}>
          <input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} />
          I verified these short-interest values against the cited Nasdaq source.
        </label>

        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "13px" }}>
          <button onClick={() => void save()} disabled={busy} style={{ border: "1px solid #806725", background: "#3b2d0d", color: "#f4d987", borderRadius: "7px", padding: "10px 14px", fontWeight: 900 }}>
            {busy ? "SAVING..." : "SAVE VERIFIED SHORT INTEREST"}
          </button>
          <span style={{ color: "#9ba8b6", fontSize: "12px" }}>{message}</span>
        </div>
      </div>
    </section>
  );
}

export default ShortInterestVerificationPanel;

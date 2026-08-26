import { useEffect, useMemo, useState } from "react";

const API = "http://localhost:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type Position = {
  ticker: string;
  weight_pct: string;
  sector: string;
  factors: string;
};

type Snapshot = {
  portfolio_snapshot_id: string;
  candidate_ticker: string;
  candidate_sector: string;
  candidate_factors: string[];
  position_count: number;
  weight_sum_pct: number;
  positions: Array<{
    ticker: string;
    weight_pct: number;
    sector: string;
    factors: string[];
  }>;
  overlap: {
    exact_ticker_weight_pct: number;
    same_sector_weight_pct: number;
    factor_overlap_weight_pct: number;
    combined_overlap_weight_pct: number;
    concentration_level: string;
    overlapping_positions: Array<{
      ticker: string;
      weight_pct: number;
      same_ticker: boolean;
      same_sector: boolean;
      shared_factors: string[];
    }>;
  };
  as_of: string;
};

type Status = {
  case_id: string;
  candidate_ticker: string;
  snapshot?: Snapshot | null;
};

const emptyPosition = (): Position => ({ ticker: "", weight_pct: "", sector: "", factors: "" });

function PortfolioContextPanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [candidateTicker, setCandidateTicker] = useState("");
  const [candidateSector, setCandidateSector] = useState("");
  const [candidateFactors, setCandidateFactors] = useState("");
  const [positions, setPositions] = useState<Position[]>([emptyPosition(), emptyPosition(), emptyPosition()]);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("No portfolio snapshot yet. Portfolio overlap remains OPEN until governed holdings are supplied.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => current === next ? current : next);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const load = async (selectedCaseId: string) => {
    const response = await fetch(`${API}/portfolio-context/${selectedCaseId}`);
    if (!response.ok) throw new Error(`Portfolio context failed: ${response.status}`);
    const data = await response.json() as Status;
    setCandidateTicker(data.candidate_ticker ?? "");
    if (data.snapshot) {
      setSnapshot(data.snapshot);
      setCandidateSector(data.snapshot.candidate_sector ?? "");
      setCandidateFactors((data.snapshot.candidate_factors ?? []).join(", "));
      setPositions((data.snapshot.positions ?? []).map((row) => ({
        ticker: row.ticker,
        weight_pct: String(row.weight_pct),
        sector: row.sector ?? "",
        factors: (row.factors ?? []).join(", "),
      })));
      setMessage(`Governed portfolio snapshot loaded · ${data.snapshot.position_count} positions · ${data.snapshot.weight_sum_pct}% total weight.`);
    } else {
      setSnapshot(null);
    }
  };

  useEffect(() => {
    if (!caseId) return;
    void load(caseId).catch((error) => setMessage(error instanceof Error ? error.message : "Portfolio context unavailable"));
  }, [caseId]);

  const weightTotal = useMemo(
    () => positions.reduce((sum, row) => sum + (Number(row.weight_pct) || 0), 0),
    [positions]
  );

  const updatePosition = (index: number, key: keyof Position, value: string) => {
    setPositions((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row));
  };

  const save = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Writing governed holdings snapshot and computing overlap...");
    try {
      const clean = positions
        .filter((row) => row.ticker.trim())
        .map((row) => ({
          ticker: row.ticker.trim().toUpperCase(),
          weight_pct: Number(row.weight_pct),
          sector: row.sector.trim(),
          factors: row.factors.split(",").map((item) => item.trim()).filter(Boolean),
        }));
      const response = await fetch(`${API}/portfolio-context/${caseId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_sector: candidateSector.trim(),
          candidate_factors: candidateFactors.split(",").map((item) => item.trim()).filter(Boolean),
          positions: clean,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json() as { snapshot: Snapshot };
      setSnapshot(result.snapshot);
      setMessage(`Portfolio snapshot saved. Combined candidate overlap: ${result.snapshot.overlap.combined_overlap_weight_pct.toFixed(1)}% · ${result.snapshot.overlap.concentration_level}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Portfolio snapshot failed");
    } finally {
      setBusy(false);
    }
  };

  if (!caseId) return null;

  const panel = {
    background: "rgba(7, 11, 17, 0.97)",
    border: "1px solid #4a5f7c",
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
    color: "#778698",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={panel}>
        <div style={small}>PORTFOLIO CONTROL · GOVERNED HOLDINGS / FACTOR OVERLAP</div>
        <h2 style={{ margin: "8px 0 5px" }}>Tell the Factory what the portfolio already owns</h2>
        <div style={{ color: "#8f9dab", fontSize: "13px", lineHeight: 1.5, maxWidth: "980px" }}>
          Portfolio overlap is first-party risk evidence. It does not create a BUY signal; it tells the Portfolio Context desk whether a new position duplicates ticker, sector, or factor exposure already in the book. Weights must total about 100%.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "180px 1fr 1fr", gap: "10px", marginTop: "16px" }}>
          <div style={{ ...input, color: "#9fb1c4" }}>Candidate: <strong style={{ color: "#e8eef5" }}>{candidateTicker || "—"}</strong></div>
          <input value={candidateSector} onChange={(event) => setCandidateSector(event.target.value)} placeholder="Candidate sector e.g. Semiconductors" style={input} />
          <input value={candidateFactors} onChange={(event) => setCandidateFactors(event.target.value)} placeholder="Candidate factors e.g. AI, Memory, Cyclical" style={input} />
        </div>

        <div style={{ marginTop: "16px", display: "grid", gap: "8px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "0.8fr 0.7fr 1.2fr 1.5fr 40px", gap: "8px", ...small }}>
            <span>Ticker</span><span>Weight %</span><span>Sector</span><span>Factors</span><span />
          </div>
          {positions.map((row, index) => (
            <div key={index} style={{ display: "grid", gridTemplateColumns: "0.8fr 0.7fr 1.2fr 1.5fr 40px", gap: "8px" }}>
              <input value={row.ticker} onChange={(event) => updatePosition(index, "ticker", event.target.value)} placeholder="NVDA" style={input} />
              <input value={row.weight_pct} onChange={(event) => updatePosition(index, "weight_pct", event.target.value)} placeholder="25" inputMode="decimal" style={input} />
              <input value={row.sector} onChange={(event) => updatePosition(index, "sector", event.target.value)} placeholder="Semiconductors" style={input} />
              <input value={row.factors} onChange={(event) => updatePosition(index, "factors", event.target.value)} placeholder="AI, Growth, Semiconductors" style={input} />
              <button onClick={() => setPositions((current) => current.filter((_, rowIndex) => rowIndex !== index))} style={{ ...input, cursor: "pointer" }}>×</button>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "13px" }}>
          <button onClick={() => setPositions((current) => [...current, emptyPosition()])} style={{ border: "1px solid #40556b", background: "#101923", color: "#dbe5ef", borderRadius: "7px", padding: "10px 13px", fontWeight: 800 }}>ADD POSITION</button>
          <button onClick={() => void save()} disabled={busy} style={{ border: "1px solid #5574a0", background: "#172943", color: "#e3efff", borderRadius: "7px", padding: "10px 14px", fontWeight: 900 }}>{busy ? "SAVING..." : "SAVE GOVERNED PORTFOLIO SNAPSHOT"}</button>
          <span style={{ color: weightTotal >= 99 && weightTotal <= 101 ? "#67cf95" : "#d7b665", fontSize: "12px" }}>Weight total: {weightTotal.toFixed(1)}%</span>
        </div>

        <div style={{ marginTop: "12px", color: "#9ba8b6", fontSize: "12px", lineHeight: 1.5 }}>{message}</div>

        {snapshot ? (
          <div style={{ marginTop: "16px", display: "grid", gridTemplateColumns: "repeat(4, minmax(140px, 1fr))", gap: "10px" }}>
            {[
              ["Exact ticker", snapshot.overlap.exact_ticker_weight_pct],
              ["Same sector", snapshot.overlap.same_sector_weight_pct],
              ["Factor overlap", snapshot.overlap.factor_overlap_weight_pct],
              ["Combined overlap", snapshot.overlap.combined_overlap_weight_pct],
            ].map(([label, value]) => (
              <div key={String(label)} style={{ background: "#080d12", border: "1px solid #2f3d4b", borderRadius: "10px", padding: "14px", textAlign: "center" }}>
                <div style={small}>{label}</div>
                <div style={{ fontSize: "24px", fontWeight: 900, marginTop: "7px" }}>{Number(value).toFixed(1)}%</div>
              </div>
            ))}
            <div style={{ gridColumn: "1 / -1", color: "#9aa8b8", fontSize: "12px", textAlign: "center" }}>
              Concentration: <strong style={{ color: snapshot.overlap.concentration_level === "HIGH" ? "#ff7b89" : snapshot.overlap.concentration_level === "MODERATE" ? "#d7b665" : "#67cf95" }}>{snapshot.overlap.concentration_level}</strong> · As of {new Date(snapshot.as_of).toLocaleString()}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

export default PortfolioContextPanel;

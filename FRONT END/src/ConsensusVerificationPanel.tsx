import { useEffect, useState } from "react";

const API = "http://localhost:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type Status = {
  case_id: string;
  ticker: string;
  suggested_source_url?: string | null;
  latest_snapshot?: {
    fiscal_year: number;
    revenue_consensus: number;
    eps_consensus: number;
    source_url: string;
    observed_at: string;
  } | null;
};

function ConsensusVerificationPanel() {
  const [caseId, setCaseId] = useState<string | null>(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [ticker, setTicker] = useState("");
  const [fiscalYear, setFiscalYear] = useState(String(new Date().getFullYear()));
  const [revenueB, setRevenueB] = useState("");
  const [eps, setEps] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Use this only if automatic consensus capture is blocked. Verify the values against the cited public source first.");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => current === next ? current : next);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!caseId) return;
    void fetch(`${API}/consensus-verification/${caseId}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Consensus verification status failed: ${response.status}`);
        return response.json() as Promise<Status>;
      })
      .then((data) => {
        setTicker(data.ticker ?? "");
        if (data.suggested_source_url && !sourceUrl) setSourceUrl(data.suggested_source_url);
        if (data.latest_snapshot) {
          setFiscalYear(String(data.latest_snapshot.fiscal_year));
          setRevenueB(String(data.latest_snapshot.revenue_consensus / 1_000_000_000));
          setEps(String(data.latest_snapshot.eps_consensus));
          setSourceUrl(data.latest_snapshot.source_url);
          setMessage("A user-verified governed consensus snapshot already exists for this case. Saving again supersedes the practical current value used by the evidence card.");
        }
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Consensus verification unavailable"));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const save = async () => {
    if (!caseId) return;
    setBusy(true);
    setMessage("Recording user-verified governed consensus...");
    try {
      const response = await fetch(`${API}/consensus-verification/${caseId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fiscal_year: Number(fiscalYear),
          revenue_consensus_billion: Number(revenueB),
          eps_consensus: Number(eps),
          source_url: sourceUrl.trim(),
          source_name: "User-verified public analyst consensus",
          verified_against_source: verified,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json() as { source_grade?: string; gap_resolution_eligible?: boolean };
      setMessage(`Consensus saved as ${result.source_grade ?? "GOVERNED_CONSENSUS"}. Refresh Primary Evidence to see the consensus fact update.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Consensus save failed");
    } finally {
      setBusy(false);
    }
  };

  if (!caseId) return null;

  const panel = {
    background: "rgba(7, 11, 17, 0.97)",
    border: "1px solid #61573a",
    borderRadius: "14px",
    padding: "22px",
  } as const;
  const input = {
    background: "#0b1118",
    border: "1px solid #3a4653",
    borderRadius: "7px",
    color: "#e8eef5",
    padding: "10px 11px",
    minWidth: 0,
  } as const;
  const small = {
    color: "#8d8265",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  return (
    <section style={{ margin: "0 28px 28px", color: "#f2f5f8", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <div style={panel}>
        <div style={small}>ANALYST CONSENSUS · VERIFIED FALLBACK</div>
        <h2 style={{ margin: "8px 0 5px" }}>Verify consensus only when automatic capture is blocked</h2>
        <div style={{ color: "#8f9dab", fontSize: "13px", lineHeight: 1.5, maxWidth: "1000px" }}>
          Consensus is aggregated market data, not an SEC/company fact. This fallback can satisfy only Revenue / EPS consensus. It cannot resolve short interest, options, or authorize a trade.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "160px 160px 1fr 1fr", gap: "10px", marginTop: "16px" }}>
          <div style={{ ...input, color: "#9fb1c4" }}>Ticker: <strong style={{ color: "#e8eef5" }}>{ticker || "—"}</strong></div>
          <input value={fiscalYear} onChange={(event) => setFiscalYear(event.target.value)} placeholder="Fiscal year" inputMode="numeric" style={input} />
          <input value={revenueB} onChange={(event) => setRevenueB(event.target.value)} placeholder="Revenue consensus ($B), e.g. 129.7" inputMode="decimal" style={input} />
          <input value={eps} onChange={(event) => setEps(event.target.value)} placeholder="EPS consensus, e.g. 73.36" inputMode="decimal" style={input} />
        </div>

        <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="Public forecast source URL" style={{ ...input, width: "100%", boxSizing: "border-box", marginTop: "10px" }} />

        <label style={{ display: "flex", gap: "8px", alignItems: "center", marginTop: "12px", color: "#b8c2cc", fontSize: "12px" }}>
          <input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} />
          I verified the revenue and EPS consensus values against the cited public source.
        </label>

        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "13px" }}>
          <button onClick={() => void save()} disabled={busy || !verified} style={{ border: "1px solid #7e6c36", background: "#302713", color: "#f0db9a", borderRadius: "7px", padding: "10px 14px", fontWeight: 900, cursor: verified ? "pointer" : "not-allowed" }}>
            {busy ? "SAVING..." : "SAVE VERIFIED CONSENSUS"}
          </button>
          <span style={{ color: "#9ba8b6", fontSize: "12px", lineHeight: 1.5 }}>{message}</span>
        </div>
      </div>
    </section>
  );
}

export default ConsensusVerificationPanel;

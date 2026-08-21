import { useEffect, useState } from "react";

type Status = "idle" | "working" | "complete";
type Agent = { name: string; room: string; status: Status };
type AgentResult = { agent: string; headline: string; view: string; confidence: number; disposition: string; floor_comment: string };
type CommitteeResult = { headline: string; summary: string; agreement: string; dissent: string; confidence: number; disposition: string; floor_comment: string };

const API = "http://localhost:8000";
const initialTopics = {
	Policy: "U.S. policy and technology stocks",
	Macro: "Federal Reserve rates and the stock market",
	Skeptic: "The market rally will continue because rates are falling",
	Committee: "U.S. policy, interest rates, and technology stocks",
};

function App() {
	const [agents, setAgents] = useState<Agent[]>([]);
	const [connected, setConnected] = useState(false);
	const [topics, setTopics] = useState(initialTopics);
	const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
	const [committeeResult, setCommitteeResult] = useState<CommitteeResult | null>(null);
	const [running, setRunning] = useState<string | null>(null);
	const [committeeRunning, setCommitteeRunning] = useState(false);

	useEffect(() => {
		fetch(`${API}/agents`).then(r => r.json()).then(d => { setAgents(d.agents); setConnected(true); }).catch(() => setConnected(false));
	}, []);

	const status = (name: string, value: Status) => setAgents(a => a.map(x => x.name === name ? { ...x, status: value } : x));
	const runAgent = async (name: string, endpoint: string) => {
		setRunning(name); setAgentResult(null); setCommitteeResult(null); status(name, "working");
		try { const r = await fetch(API + endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic: topics[name as keyof typeof topics] }) }); if (!r.ok) throw Error(); setAgentResult(await r.json()); status(name, "complete"); setConnected(true); } catch { status(name, "idle"); setConnected(false); } finally { setRunning(null); }
	};
	const runCommittee = async () => {
		setCommitteeRunning(true); setAgentResult(null); setCommitteeResult(null); setAgents(a => a.map(x => ({ ...x, status: "working" })));
		try { const r = await fetch(`${API}/committee/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic: topics.Committee }) }); if (!r.ok) throw Error(); setCommitteeResult(await r.json()); setAgents(a => a.map(x => ({ ...x, status: "complete" }))); setConnected(true); } catch { setAgents(a => a.map(x => ({ ...x, status: "idle" }))); setConnected(false); } finally { setCommitteeRunning(false); }
	};
	const input = (key: keyof typeof topics) => <input value={topics[key]} onChange={e => setTopics(t => ({ ...t, [key]: e.target.value }))} style={styles.input} />;
	const disabled = !!running || committeeRunning;
	const cards = [{ key: "Policy" as const, room: "Policy Floor", description: "Government, regulation, trade, courts, and statements that ruin everybody’s afternoon.", endpoint: "/agents/policy/run" }, { key: "Macro" as const, room: "Macro Desk", description: "Rates, inflation, liquidity, growth, and several ways the Fed can ruin brunch.", endpoint: "/agents/macro/run" }, { key: "Skeptic" as const, room: "Red Team", description: "Confirmation bias enters confidently. The Skeptic asks to see identification.", endpoint: "/agents/skeptic/run" }];
	return <main style={styles.page}>
		<header style={styles.header}><div><small>INVESTMENT INTELLIGENCE OS</small><h1>THE INTELLIGENCE FLOOR</h1></div><div style={{ textAlign: "right" }}><small style={{ color: connected ? "#59c68c" : "#ff6379" }}>BACKEND {connected ? "CONNECTED" : "OFFLINE"}</small><b style={styles.paper}>PAPER MODE</b></div></header>
		<div style={styles.agentGrid}>{agents.map(a => <section key={a.name} style={{ ...styles.card, borderColor: a.status === "working" ? "#d9a441" : a.status === "complete" ? "#4fa879" : "#27303a" }}><small>{a.room.toUpperCase()}</small><div style={styles.icon}>◉</div><h2>{a.name}</h2><small style={{ color: a.status === "complete" ? "#59c68c" : a.status === "working" ? "#e4b754" : "#7c8794" }}>{a.status.toUpperCase()}</small></section>)}</div>
		<div style={styles.grid}>{cards.map(c => <section key={c.key} style={styles.panel}><small>{c.room.toUpperCase()}</small><h2>{c.key} {c.key === "Skeptic" ? "" : "Analyst"}</h2><p>{c.description}</p>{input(c.key)}<button disabled={disabled} onClick={() => runAgent(c.key, c.endpoint)} style={c.key === "Skeptic" ? styles.redButton : styles.button}>RUN {c.key.toUpperCase()} {c.key !== "Skeptic" && "ANALYST"}</button></section>)}</div>
		<section style={styles.committee}><small>INVESTMENT COMMITTEE</small><h2>Send It Upstairs</h2><p>One topic. Three specialist reviews. One committee decision. Dissent remains on the record because apparently adults can disagree.</p>{input("Committee")}<button disabled={disabled} onClick={runCommittee} style={styles.committeeButton}>{committeeRunning ? "COMMITTEE IN SESSION..." : "CONVENE COMMITTEE"}</button></section>
		{agentResult && <section style={styles.result}><small>{agentResult.agent.toUpperCase()} // COMPLETE</small><h2>{agentResult.headline}</h2><p>{agentResult.view}</p><p><b>Disposition:</b> {agentResult.disposition}　<b>Confidence:</b> {Math.round(agentResult.confidence * 100)}%</p><em>“{agentResult.floor_comment}”</em></section>}
		{committeeResult && <section style={styles.result}><small>COMMITTEE DECISION // COMPLETE</small><h2>{committeeResult.headline}</h2><p>{committeeResult.summary}</p><div style={styles.split}><div><b>AGREEMENT</b><p>{committeeResult.agreement}</p></div><div><b>DISSENT</b><p>{committeeResult.dissent}</p></div></div><p><b>Disposition:</b> {committeeResult.disposition}　<b>Confidence:</b> {Math.round(committeeResult.confidence * 100)}%</p><em>Floor note: “{committeeResult.floor_comment}”</em></section>}
	</main>;
}

const styles = { page: { minHeight: "100vh", background: "radial-gradient(circle at top, #18212f 0%, #090b10 45%, #040506 100%)", color: "#f4f4f4", fontFamily: "Arial, Helvetica, sans-serif", padding: 32 }, header: { display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #28313d", paddingBottom: 20, marginBottom: 32 }, agentGrid: { display: "grid", gridTemplateColumns: "repeat(3, minmax(220px, 1fr))", gap: 18, marginBottom: 30 }, grid: { display: "grid", gridTemplateColumns: "repeat(3, minmax(260px, 1fr))", gap: 20, marginBottom: 24 }, card: { background: "linear-gradient(145deg, #11161d, #0a0d12)", border: "1px solid #27303a", borderRadius: 12, padding: 22, minHeight: 190 }, panel: { border: "1px solid #26303b", background: "#090d12", borderRadius: 12, padding: 24 }, committee: { border: "1px solid #38506c", background: "#0d1621", borderRadius: 12, padding: 28, marginBottom: 24 }, result: { border: "1px solid #4c78a0", background: "#0b121b", borderRadius: 12, padding: 28, marginBottom: 24 }, input: { width: "100%", boxSizing: "border-box" as const, marginTop: 12, padding: 14, borderRadius: 7, border: "1px solid #303b49", background: "#11161d", color: "#fff", fontSize: 15 }, button: { marginTop: 14, background: "#d9a441", color: "#090909", border: 0, borderRadius: 7, padding: "13px 20px", fontWeight: 800 }, redButton: { marginTop: 14, background: "#b24b62", color: "#fff", border: 0, borderRadius: 7, padding: "13px 20px", fontWeight: 800 }, committeeButton: { marginTop: 16, background: "#5e9ed0", color: "#071018", border: 0, borderRadius: 7, padding: "14px 24px", fontWeight: 900 }, paper: { display: "block", marginTop: 8, border: "1px solid #8b1e2d", background: "#26080d", color: "#ff6379", padding: "10px 16px", borderRadius: 6, letterSpacing: 2 }, icon: { marginTop: 25, width: 52, height: 52, display: "grid", placeItems: "center", background: "#171e27", border: "1px solid #303b49", borderRadius: 10, fontSize: 25 }, split: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 } };
export default App;

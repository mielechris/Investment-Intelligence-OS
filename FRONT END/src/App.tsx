import { useEffect, useState } from "react";

type AgentStatus = "idle" | "working" | "complete";

type Agent = { name: string; room: string; status: AgentStatus };
type AgentResult = { agent: string; status: string; topic: string; headline: string; view: string; confidence: number; disposition: string; floor_comment: string };
type CommitteeResult = { topic: string; status: string; headline: string; summary: string; agreement: string; dissent: string; confidence: number; disposition: string; floor_comment: string };
type RiskResult = { room: string; status: string; topic: string; decision: string; allowed_notional: number; triggered_rules: string[]; confidence_received: number; committee_disposition: string; floor_comment: string; paper_mode: boolean };

function App() {
	const [agents, setAgents] = useState<Agent[]>([]);
	const [connected, setConnected] = useState(false);
	const [policyTopic, setPolicyTopic] = useState("U.S. policy and technology stocks");
	const [macroTopic, setMacroTopic] = useState("Federal Reserve rates and the stock market");
	const [skepticTopic, setSkepticTopic] = useState("The market rally will continue because rates are falling");
	const [committeeTopic, setCommitteeTopic] = useState("U.S. policy, interest rates, and technology stocks");
	const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
	const [committeeResult, setCommitteeResult] = useState<CommitteeResult | null>(null);
	const [riskResult, setRiskResult] = useState<RiskResult | null>(null);
	const [runningAgent, setRunningAgent] = useState<string | null>(null);
	const [committeeRunning, setCommitteeRunning] = useState(false);

	useEffect(() => {
		fetch("http://localhost:8000/agents").then((response) => response.json()).then((data) => { setAgents(data.agents); setConnected(true); }).catch(() => setConnected(false));
	}, []);

	const updateAgentStatus = (agentName: string, status: AgentStatus) => setAgents((current) => current.map((agent) => agent.name === agentName ? { ...agent, status } : agent));

	const runAgent = async (agentName: string, endpoint: string, topic: string) => {
		setRunningAgent(agentName); setAgentResult(null); setCommitteeResult(null); setRiskResult(null); updateAgentStatus(agentName, "working");
		try {
			const response = await fetch(`http://localhost:8000${endpoint}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic }) });
			if (!response.ok) throw new Error("Agent request failed");
			setAgentResult(await response.json()); updateAgentStatus(agentName, "complete"); setConnected(true);
		} catch { updateAgentStatus(agentName, "idle"); setConnected(false); } finally { setRunningAgent(null); }
	};

	const runCommittee = async () => {
		setCommitteeRunning(true); setAgentResult(null); setCommitteeResult(null); setRiskResult(null); setAgents((current) => current.map((agent) => ({ ...agent, status: "working" })));
		try {
			const committeeResponse = await fetch("http://localhost:8000/committee/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic: committeeTopic }) });
			if (!committeeResponse.ok) throw new Error("Committee request failed");
			const committeeData: CommitteeResult = await committeeResponse.json(); setCommitteeResult(committeeData);
			setAgents((current) => current.map((agent) => ({ ...agent, status: "complete" })));
			const riskResponse = await fetch("http://localhost:8000/risk/evaluate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic: committeeData.topic, disposition: committeeData.disposition, confidence: committeeData.confidence }) });
			if (!riskResponse.ok) throw new Error("Risk request failed");
			setRiskResult(await riskResponse.json()); setConnected(true);
		} catch { setConnected(false); } finally { setCommitteeRunning(false); }
	};

	const inputStyle = { width: "100%", boxSizing: "border-box" as const, marginTop: "12px", padding: "14px", borderRadius: "7px", border: "1px solid #303b49", background: "#11161d", color: "#ffffff", fontSize: "15px" };
	const panelStyle = { background: "#090d12", border: "1px solid #26303b", borderRadius: "12px", padding: "24px" };
	const buttonStyle = { marginTop: "14px", padding: "12px 16px", borderRadius: "6px", border: "1px solid #526579", background: "#182432", color: "#fff", cursor: "pointer", fontWeight: 700 };

	const agentCard = (agent: Agent) => <section key={agent.name} style={{ background: "#0a0d12", border: agent.status === "working" ? "1px solid #d9a441" : agent.status === "complete" ? "1px solid #4fa879" : "1px solid #27303a", borderRadius: "12px", padding: "22px" }}><div style={{ color: "#748091", fontSize: "11px", letterSpacing: "2px" }}>{agent.room.toUpperCase()}</div><h2>{agent.name}</h2><strong style={{ color: agent.status === "complete" ? "#59c68c" : agent.status === "working" ? "#e4b754" : "#7c8794" }}>{agent.status.toUpperCase()}</strong></section>;
	const agentPanel = (title: string, value: string, setValue: (value: string) => void, name: string, endpoint: string) => <section style={panelStyle}><h2>{title}</h2><input value={value} onChange={(event) => setValue(event.target.value)} style={inputStyle} /><button style={buttonStyle} onClick={() => runAgent(name, endpoint, value)} disabled={runningAgent !== null}>{`RUN ${title.toUpperCase()}`}</button></section>;

	return <div style={{ minHeight: "100vh", background: "radial-gradient(circle at top, #18212f 0%, #090b10 45%, #040506 100%)", color: "#f4f4f4", fontFamily: "Arial, Helvetica, sans-serif", padding: "32px" }}>
		<header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #28313d", paddingBottom: "20px", marginBottom: "32px" }}><div><div style={{ color: "#7e8998", fontSize: "12px", letterSpacing: "4px" }}>INVESTMENT INTELLIGENCE OS</div><h1 style={{ margin: "8px 0 0", fontSize: "34px" }}>THE INTELLIGENCE FLOOR</h1></div><div style={{ textAlign: "right" }}><div style={{ marginBottom: "8px", color: connected ? "#59c68c" : "#ff6379", fontSize: "11px", letterSpacing: "2px" }}>BACKEND {connected ? "CONNECTED" : "OFFLINE"}</div><div style={{ border: "1px solid #8b1e2d", background: "#26080d", color: "#ff6379", padding: "10px 16px", borderRadius: "6px", fontWeight: 700, letterSpacing: "2px", fontSize: "12px" }}>PAPER MODE</div></div></header>
		<div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(220px, 1fr))", gap: "18px", marginBottom: "30px" }}>{agents.map(agentCard)}</div>
		<div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(260px, 1fr))", gap: "20px", marginBottom: "24px" }}>{agentPanel("Policy Analyst", policyTopic, setPolicyTopic, "Policy Analyst", "/agents/policy/run")}{agentPanel("Macro Analyst", macroTopic, setMacroTopic, "Macro Analyst", "/agents/macro/run")}{agentPanel("Skeptic", skepticTopic, setSkepticTopic, "Skeptic", "/agents/skeptic/run")}</div>
		<section style={{ ...panelStyle, border: "1px solid #38506c", marginBottom: "24px" }}><div style={{ color: "#6da9dd" }}>INVESTMENT COMMITTEE</div><h2>Send It Upstairs</h2><input value={committeeTopic} onChange={(event) => setCommitteeTopic(event.target.value)} style={inputStyle} /><button style={buttonStyle} onClick={runCommittee} disabled={committeeRunning}>{committeeRunning ? "COMMITTEE IN SESSION..." : "CONVENE COMMITTEE"}</button></section>
		{agentResult && <section style={{ ...panelStyle, border: "1px solid #315d48", marginBottom: "24px" }}><h2>{agentResult.headline}</h2><p>{agentResult.view}</p><p><strong>Disposition:</strong> {agentResult.disposition}</p><p><strong>Confidence:</strong> {Math.round(agentResult.confidence * 100)}%</p></section>}
		{committeeResult && <section style={{ ...panelStyle, border: "1px solid #4c78a0", marginBottom: "24px" }}><div style={{ color: "#78b9eb" }}>COMMITTEE DECISION // COMPLETE</div><h2>{committeeResult.headline}</h2><p>{committeeResult.summary}</p><p><strong>Agreement:</strong> {committeeResult.agreement}</p><p><strong>Dissent:</strong> {committeeResult.dissent}</p><p><strong>Disposition:</strong> {committeeResult.disposition}</p><p><strong>Confidence:</strong> {Math.round(committeeResult.confidence * 100)}%</p></section>}
		{riskResult && <section style={{ border: riskResult.decision === "VETOED" ? "1px solid #a73b4c" : "1px solid #b38b3e", background: riskResult.decision === "VETOED" ? "#190a0e" : "#17130a", borderRadius: "12px", padding: "28px" }}><div style={{ color: riskResult.decision === "VETOED" ? "#ff6379" : "#e6bd5c", letterSpacing: "4px", fontSize: "11px" }}>RISK INSPECTION // COMPLETE</div><h2>{riskResult.decision === "VETOED" ? "Risk Veto" : "Watch Only"}</h2><p><strong>Decision:</strong> {riskResult.decision}</p><p><strong>Allowed Notional:</strong> ${riskResult.allowed_notional}</p><p><strong>Committee Disposition:</strong> {riskResult.committee_disposition}</p><p><strong>Confidence Received:</strong> {Math.round(riskResult.confidence_received * 100)}%</p><strong>Triggered Rules:</strong><ul>{riskResult.triggered_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul><p style={{ color: "#ff8293", fontStyle: "italic" }}>“{riskResult.floor_comment}”</p></section>}
	</div>;
}

export default App;

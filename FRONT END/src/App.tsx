import { useEffect, useState } from "react";

type AgentStatus = "idle" | "working" | "complete";

type Agent = {
	name: string;
	room: string;
	status: AgentStatus;
};

type AgentResult = {
	agent: string;
	status: string;
	topic: string;
	headline: string;
	view: string;
	confidence: number;
	disposition: string;
	floor_comment: string;
};

function App() {
	const [agents, setAgents] = useState<Agent[]>([]);
	const [connected, setConnected] = useState(false);
	const [policyTopic, setPolicyTopic] = useState("U.S. policy and technology stocks");
	const [macroTopic, setMacroTopic] = useState("Federal Reserve rates and the stock market");
	const [skepticTopic, setSkepticTopic] = useState("The market rally will continue because rates are falling");
	const [result, setResult] = useState<AgentResult | null>(null);
	const [runningAgent, setRunningAgent] = useState<string | null>(null);

	useEffect(() => {
		fetch("http://localhost:8000/agents")
			.then((response) => response.json())
			.then((data) => { setAgents(data.agents); setConnected(true); })
			.catch(() => setConnected(false));
	}, []);

	const updateAgentStatus = (agentName: string, status: AgentStatus) => {
		setAgents((current) => current.map((agent) => agent.name === agentName ? { ...agent, status } : agent));
	};

	const runAgent = async (agentName: string, endpoint: string, topic: string) => {
		setRunningAgent(agentName);
		setResult(null);
		updateAgentStatus(agentName, "working");
		try {
			const response = await fetch(`http://localhost:8000${endpoint}`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ topic }),
			});
			if (!response.ok) throw new Error("Agent request failed");
			const data: AgentResult = await response.json();
			setResult(data);
			updateAgentStatus(agentName, "complete");
			setConnected(true);
		} catch {
			updateAgentStatus(agentName, "idle");
			setConnected(false);
		} finally {
			setRunningAgent(null);
		}
	};

	const inputStyle = { width: "100%", boxSizing: "border-box" as const, marginTop: "12px", padding: "14px", borderRadius: "7px", border: "1px solid #303b49", background: "#11161d", color: "#ffffff", fontSize: "15px" };
	const buttonStyle = { marginTop: "14px", background: "#d9a441", color: "#090909", border: 0, borderRadius: "7px", padding: "13px 20px", fontWeight: 800, cursor: runningAgent !== null ? "wait" : "pointer" };

	const desks = [
		{ label: "POLICY FLOOR", name: "Policy Analyst", description: "Government action, regulation, trade, courts, and the occasional statement that ruins everybody’s afternoon.", value: policyTopic, setValue: setPolicyTopic, endpoint: "/agents/policy/run", button: "RUN POLICY ANALYST" },
		{ label: "MACRO DESK", name: "Macro Analyst", description: "Rates, inflation, liquidity, growth, and several ways the Federal Reserve can ruin brunch.", value: macroTopic, setValue: setMacroTopic, endpoint: "/agents/macro/run", button: "RUN MACRO ANALYST" },
		{ label: "RED TEAM", name: "Skeptic", description: "Confirmation bias enters confidently. The Skeptic asks to see identification.", value: skepticTopic, setValue: setSkepticTopic, endpoint: "/agents/skeptic/run", button: "RUN SKEPTIC" },
	];

	return <div style={{ minHeight: "100vh", background: "radial-gradient(circle at top, #18212f 0%, #090b10 45%, #040506 100%)", color: "#f4f4f4", fontFamily: "Arial, Helvetica, sans-serif", padding: "32px" }}>
		<header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #28313d", paddingBottom: "20px", marginBottom: "32px" }}>
			<div><div style={{ color: "#7e8998", fontSize: "12px", letterSpacing: "4px" }}>INVESTMENT INTELLIGENCE OS</div><h1 style={{ margin: "8px 0 0", fontSize: "34px" }}>THE INTELLIGENCE FLOOR</h1></div>
			<div style={{ textAlign: "right" }}><div style={{ marginBottom: "8px", color: connected ? "#59c68c" : "#ff6379", fontSize: "11px", letterSpacing: "2px" }}>BACKEND {connected ? "CONNECTED" : "OFFLINE"}</div><div style={{ border: "1px solid #8b1e2d", background: "#26080d", color: "#ff6379", padding: "10px 16px", borderRadius: "6px", fontWeight: 700, letterSpacing: "2px", fontSize: "12px" }}>PAPER MODE</div></div>
		</header>
		<div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(220px, 1fr))", gap: "18px", marginBottom: "30px" }}>{agents.map((agent) => <section key={agent.name} style={{ background: "linear-gradient(145deg, #11161d, #0a0d12)", border: agent.status === "working" ? "1px solid #d9a441" : agent.status === "complete" ? "1px solid #4fa879" : "1px solid #27303a", borderRadius: "12px", padding: "22px", minHeight: "210px", boxShadow: agent.status === "working" ? "0 0 30px rgba(217,164,65,.18)" : "none" }}><div style={{ color: "#748091", fontSize: "11px", letterSpacing: "2px", marginBottom: "30px" }}>{agent.room.toUpperCase()}</div><div style={{ width: "52px", height: "52px", borderRadius: "10px", display: "grid", placeItems: "center", background: "#171e27", border: "1px solid #303b49", fontSize: "25px", marginBottom: "18px" }}>◉</div><h2>{agent.name}</h2><div style={{ fontSize: "11px", letterSpacing: "2px", color: agent.status === "complete" ? "#59c68c" : agent.status === "working" ? "#e4b754" : "#7c8794" }}>{agent.status.toUpperCase()}</div></section>)}</div>
		<div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(260px, 1fr))", gap: "20px", marginBottom: "20px" }}>{desks.map((desk) => <section key={desk.name} style={{ border: desk.name === "Skeptic" ? "1px solid #4b2530" : "1px solid #26303b", background: desk.name === "Skeptic" ? "#10090c" : "#090d12", borderRadius: "12px", padding: "24px" }}><div style={{ color: "#788494", fontSize: "11px", letterSpacing: "3px", marginBottom: "10px" }}>{desk.label}</div><h2>{desk.name}</h2><p style={{ color: "#9fa8b4" }}>{desk.description}</p><input value={desk.value} onChange={(event) => desk.setValue(event.target.value)} style={inputStyle} /><button onClick={() => runAgent(desk.name, desk.endpoint, desk.value)} disabled={runningAgent !== null} style={{ ...buttonStyle, background: runningAgent === desk.name ? "#6c5a34" : desk.name === "Skeptic" ? "#b24b62" : "#d9a441", color: desk.name === "Skeptic" ? "#ffffff" : "#090909" }}>{runningAgent === desk.name ? `${desk.label} WORKING...` : desk.button}</button></section>)}</div>
		{result && <section style={{ border: "1px solid #315d48", background: "#0b1511", borderRadius: "12px", padding: "24px" }}><div style={{ color: "#59c68c", fontSize: "11px", letterSpacing: "3px" }}>{result.agent.toUpperCase()} // COMPLETE</div><h2>{result.headline}</h2><div style={{ color: "#d8dee6", lineHeight: 1.7, marginBottom: "20px" }}>{result.view}</div><div style={{ display: "flex", gap: "24px", flexWrap: "wrap", color: "#9fa8b4" }}><div><strong style={{ color: "#ffffff" }}>Disposition:</strong> {result.disposition}</div><div><strong style={{ color: "#ffffff" }}>Confidence:</strong> {Math.round(result.confidence * 100)}%</div></div><div style={{ marginTop: "20px", borderTop: "1px solid #244232", paddingTop: "16px", color: "#69c994", fontStyle: "italic" }}>Floor note: “{result.floor_comment}”</div></section>}
	</div>;
}

export default App;

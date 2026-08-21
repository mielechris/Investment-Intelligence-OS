import { FormEvent, useEffect, useState } from "react";

type Agent = { name: string; room: string; status: string };
type Result = {
	agent: string;
	status: string;
	topic: string;
	headline: string;
	view: string;
	confidence: number;
	disposition: string;
	floor_comment: string;
};

const API = "http://localhost:8000";

export default function App() {
	const [agents, setAgents] = useState<Agent[]>([]);
	const [topic, setTopic] = useState("");
	const [result, setResult] = useState<Result | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState("");

	useEffect(() => {
		fetch(`${API}/agents`)
			.then((response) => {
				if (!response.ok) throw new Error("Backend unavailable");
				return response.json();
			})
			.then((data) => setAgents(data.agents))
			.catch(() => setError("Unable to connect to the IIOS backend."));
	}, []);

	async function runAgent(event: FormEvent) {
		event.preventDefault();
		if (!topic.trim()) return;
		setLoading(true);
		setError("");
		try {
			const response = await fetch(`${API}/agents/policy/run`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ topic: topic.trim() }),
			});
			if (!response.ok) throw new Error("Request failed");
			setResult(await response.json());
		} catch {
			setError("The policy agent could not be reached. Is the backend running?");
		} finally {
			setLoading(false);
		}
	}

	return (
		<main className="app-shell">
			<style>{`
				* { box-sizing: border-box; } body { margin: 0; background: #09111d; color: #e8eef7; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
				.app-shell { min-height: 100vh; max-width: 1220px; margin: auto; padding: 34px 42px; }
				header { display: flex; align-items: flex-start; justify-content: space-between; border-bottom: 1px solid #213044; padding-bottom: 28px; }
				.eyebrow { color: #6da4d8; font-size: 11px; letter-spacing: .18em; font-weight: 700; text-transform: uppercase; }
				h1 { font-size: 31px; letter-spacing: -.04em; margin: 8px 0 5px; } .subtle, .muted { color: #8495aa; font-size: 14px; }
				.live { color: #7ee2ab; border: 1px solid #275b48; background: #102a27; padding: 8px 12px; border-radius: 20px; font-size: 12px; }
				.live:before { content: "●"; margin-right: 7px; }
				.grid { display: grid; grid-template-columns: 1.45fr .8fr; gap: 24px; margin-top: 28px; }
				.panel { background: #101b2a; border: 1px solid #213249; border-radius: 12px; padding: 25px; box-shadow: 0 12px 30px #02071133; }
				.panel h2 { font-size: 16px; margin: 0 0 5px; } .label { color: #7890a9; text-transform: uppercase; letter-spacing: .12em; font-size: 10px; font-weight: 700; }
				form { display: flex; gap: 10px; margin-top: 22px; } input { flex: 1; min-width: 0; background: #0a1422; border: 1px solid #30445e; border-radius: 7px; padding: 13px 14px; color: white; outline: none; font-size: 14px; } input:focus { border-color: #65a9e6; }
				button { border: 0; border-radius: 7px; padding: 0 19px; background: #5e9ed4; color: #07111d; font-weight: 800; cursor: pointer; } button:disabled { opacity: .55; cursor: wait; }
				.result { margin-top: 25px; border-top: 1px solid #26374d; padding-top: 23px; } .result-top { display:flex; justify-content:space-between; gap: 15px; } .result h3 { margin: 7px 0 10px; font-size: 21px; }
				.badge { color: #f6c56b; background: #3a2e19; border: 1px solid #775d2d; padding: 6px 10px; height: fit-content; border-radius: 5px; font-size: 11px; font-weight: 800; letter-spacing: .08em; }
				.view { line-height: 1.7; color: #b9c8d9; font-size: 14px; } .metrics { display:flex; gap: 35px; margin-top: 20px; } .metric strong { display:block; font-size: 20px; margin-top: 5px; }
				.comment { margin-top: 22px; padding: 13px 15px; border-left: 2px solid #5e9ed4; background: #0b1625; color: #9eafc2; font-size: 13px; }
				.agent { display:flex; align-items:center; gap: 12px; padding: 16px 0; border-bottom: 1px solid #213044; } .agent:last-child { border:0; padding-bottom: 0; } .avatar { background:#183352; color:#79b5e9; width:34px; height:34px; border-radius:50%; display:grid; place-items:center; font-weight:800; } .agent-info { flex:1; } .agent-name { font-size: 14px; font-weight: 700; } .room { color:#73889f; font-size:12px; margin-top:4px; } .status { color:#7ee2ab; font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
				.error { color: #f19b91; font-size: 13px; margin-top: 15px; } @media (max-width: 760px) { .app-shell { padding: 25px 18px; } .grid { grid-template-columns: 1fr; } header { gap: 15px; } form { flex-direction:column; } button { height: 44px; } }
			`}</style>
			<header>
				<div><div className="eyebrow">Investment Intelligence OS</div><h1>Operations Floor</h1><div className="subtle">Governed analysis for decisions that matter.</div></div>
				<div className="live">SYSTEM ONLINE</div>
			</header>
			<section className="grid">
				<div className="panel">
					<div className="label">Policy desk</div><h2>Ask the Policy Analyst</h2><div className="subtle">Submit a topic to start a governed review.</div>
					<form onSubmit={runAgent}><input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. Federal Reserve rate decision" /><button disabled={loading}>{loading ? "RUNNING…" : "RUN ANALYSIS"}</button></form>
					{error && <div className="error">{error}</div>}
					{result && <div className="result"><div className="result-top"><div><div className="label">{result.agent} · {result.status}</div><h3>{result.headline}</h3></div><div className="badge">{result.disposition}</div></div><p className="view">{result.view}</p><div className="metrics"><div className="metric"><div className="label">Confidence</div><strong>{Math.round(result.confidence * 100)}%</strong></div><div className="metric"><div className="label">Topic</div><strong style={{fontSize: 14, maxWidth: 250}}>{result.topic}</strong></div></div><div className="comment">“{result.floor_comment}”</div></div>}
				</div>
				<div className="panel"><div className="label">Active agents</div><h2>Floor roster</h2><div className="subtle">Live agent availability</div>{agents.map((agent) => <div className="agent" key={agent.name}><div className="avatar">{agent.name.charAt(0)}</div><div className="agent-info"><div className="agent-name">{agent.name}</div><div className="room">{agent.room}</div></div><div className="status">{agent.status}</div></div>)}</div>
			</section>
		</main>
	);
}

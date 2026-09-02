type Upgrade = { name: string; status: string; description: string; value: string; risk: string };

const UPGRADES: Upgrade[] = [
  { name: "Additional primary evidence lanes", status: "AVAILABLE", description: "More governed research coverage.", value: "Higher evidence breadth", risk: "Owner approval required" },
  { name: "Filing intelligence", status: "PROPOSED", description: "Structured filing review on the wall.", value: "Faster document triage", risk: "Evidence required" },
  { name: "Voice and ambient audio", status: "UNDER CONSTRUCTION", description: "Optional presentation layer only.", value: "Room presence", risk: "Sound remains off by default" },
  { name: "Historical decision theater", status: "INSTALLED", description: "Replay receipts without treating history as live.", value: "Decision memory", risk: "Read-only" },
  { name: "Owner-approved provider experiments", status: "POLICY BLOCKED", description: "Future governed experimentation registry.", value: "Research options", risk: "No automatic connection" },
];

export default function ExpansionWing() {
  return <section className="wall-expansion"><header><span>EXPANSION WING</span><h2>Future rooms, no new authority</h2><p>These are visual roadmap entries only. This wall cannot activate a provider, portfolio, or capability.</p></header><div>{UPGRADES.map((upgrade) => <article key={upgrade.name}><small>{upgrade.status}</small><h3>{upgrade.name}</h3><p>{upgrade.description}</p><dl><dt>Expected value</dt><dd>{upgrade.value}</dd><dt>Risk / approval</dt><dd>{upgrade.risk}</dd></dl><button disabled>Registry only</button></article>)}</div></section>;
}
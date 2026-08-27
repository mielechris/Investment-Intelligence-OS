import { useEffect, useState } from "react";
import "./FamilyModelBrains.css";

const API =
  import.meta.env.VITE_IIOS_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8002";

type BrainState = "WORKING" | "RECENT" | "BLOCKED" | "ARMED" | "OFFLINE";

type Brain = {
  key: "gpt" | "grok" | "gemini";
  alias: string;
  provider: string;
  role: string;
  state: BrainState;
  configured: boolean;
  last_event?: string | null;
  last_event_at?: string | null;
  candidate_count?: number | null;
  execution_satisfied?: boolean | null;
};

type BrainTelemetry = {
  generated_at: string;
  providers: Brain[];
  model_context_present: boolean;
  provider_errors?: Record<string, unknown>;
  read_only: boolean;
  broker_connected: boolean;
  live_execution: boolean;
};

async function loadBrains(): Promise<BrainTelemetry> {
  const response = await fetch(`${API}/family-network/model-brains`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error((await response.text()) || `Brain telemetry failed ${response.status}`);
  }
  return response.json() as Promise<BrainTelemetry>;
}

function shortEvent(value?: string | null): string {
  if (!value) return "NO RECENT EVENT";
  return value.replaceAll("_", " ");
}

export default function FamilyModelBrains() {
  const [telemetry, setTelemetry] = useState<BrainTelemetry | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      try {
        const next = await loadBrains();
        if (disposed) return;
        setTelemetry(next);
        setConnected(true);
      } catch {
        if (disposed) return;
        setConnected(false);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const providers = telemetry?.providers ?? [
    {
      key: "gpt" as const,
      alias: "The House Brain",
      provider: "OpenAI GPT",
      role: "8 desks + Committee",
      state: "OFFLINE" as const,
      configured: false,
    },
    {
      key: "grok" as const,
      alias: "The Wire",
      provider: "xAI Grok",
      role: "X + Web catalyst intelligence",
      state: "OFFLINE" as const,
      configured: false,
    },
    {
      key: "gemini" as const,
      alias: "The Books",
      provider: "Google Gemini",
      role: "Grounded source research",
      state: "OFFLINE" as const,
      configured: false,
    },
  ];

  return (
    <section className={`fmb-shell ${connected ? "connected" : "offline"}`} aria-label="Family Network model brains">
      <div className="fmb-label">
        <span>THE FAMILY NETWORK</span>
        <strong>THREE BRAINS</strong>
      </div>
      <div className="fmb-grid">
        {providers.map((brain) => {
          const state = connected ? brain.state : "OFFLINE";
          return (
            <article className={`fmb-brain ${brain.key} state-${state.toLowerCase()}`} key={brain.key}>
              <div className="fmb-brain-head">
                <i />
                <span>{brain.provider}</span>
                <b>{state}</b>
              </div>
              <strong>{brain.alias}</strong>
              <p>{brain.role}</p>
              <small>
                {brain.candidate_count != null ? `${brain.candidate_count} CANDIDATES · ` : ""}
                {shortEvent(brain.last_event)}
              </small>
            </article>
          );
        })}
      </div>
      <div className="fmb-locks">
        <span>LEDGER-BOUND</span>
        <span>READ ONLY</span>
        <span>BROKER FALSE</span>
        <span>LIVE FALSE</span>
      </div>
    </section>
  );
}

import { useCallback, useEffect, useState } from "react";

const API = "http://localhost:8000";

type WatchObligation = {
  requirement?: string;
  lane?: string;
  fact_key?: string;
  state?: string;
};

type PaperCapitalStatus = {
  case_id: string;
  stage: string;

  research: {
    stage?: string;
    qualified_buy_candidate: boolean;
    unmet_requirements: string[];
  };

  thesis: {
    status?: string;
    invalidated?: boolean;
    breached_rules: string[];
    watching_rules: string[];
  };

  capital: {
    decision?: string;
    current_price?: number;
    upside_reference?: number;
    downside_reference?: number;
    reward_risk?: number;
    minimum_reward_risk?: number;
    maximum_qualifying_entry?: number;
    failed_hard_checks: string[];
  };

  watch_obligations: WatchObligation[];

  permissions: {
    qualified_research: boolean;
    thesis_valid: boolean;
    capital_approved: boolean;
    position_sizing_ready: boolean;
    paper_authorization_ready: boolean;
    paper_order_permission: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };

  paper_mode: boolean;
};

function money(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return "—";

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function ratio(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

function stageLabel(stage?: string): string {
  return String(stage || "UNKNOWN").replaceAll("_", " ");
}

function statusTone(
  passed: boolean,
  watching = false,
): string {
  if (passed) return "#59c68c";
  if (watching) return "#e6bd5c";
  return "#ff6379";
}

export default function PaperCapitalControlPanel({
  caseId,
}: {
  caseId: string | null;
}) {
  const [status, setStatus] =
    useState<PaperCapitalStatus | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    if (!caseId) {
      setStatus(null);
      setError(null);
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(
        `${API}/paper-capital/${caseId}/status`,
      );

      if (!response.ok) {
        const text = await response.text();
        throw new Error(
          text || `HTTP ${response.status}`,
        );
      }

      const data =
        (await response.json()) as PaperCapitalStatus;

      setStatus(data);
      setError(null);
    } catch (err) {
      setStatus(null);
      setError(
        err instanceof Error
          ? err.message
          : "Capital Control unavailable",
      );
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void loadStatus();

    const timer = window.setInterval(() => {
      void loadStatus();
    }, 15000);

    return () =>
      window.clearInterval(timer);
  }, [loadStatus]);

  const panel = {
    background: "rgba(7, 11, 17, 0.94)",
    border: "1px solid #344354",
    borderRadius: "14px",
    padding: "22px",
    marginBottom: "22px",
  } as const;

  const label = {
    color: "#758294",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  if (!caseId) {
    return (
      <section style={panel}>
        <div style={label}>
          CAPITAL CONTROL ROOM
        </div>

        <h2 style={{ margin: "7px 0 8px" }}>
          Governed Capital Chain
        </h2>

        <div style={{ color: "#748091" }}>
          Select an active case to inspect
          qualification, thesis validity, entry
          economics, authorization, and execution
          locks.
        </div>
      </section>
    );
  }

  if (loading && !status) {
    return (
      <section style={panel}>
        <div style={label}>
          CAPITAL CONTROL ROOM
        </div>

        <h2 style={{ margin: "7px 0" }}>
          Loading governed capital state…
        </h2>
      </section>
    );
  }

  if (error || !status) {
    return (
      <section
        style={{
          ...panel,
          borderColor: "#743441",
        }}
      >
        <div style={label}>
          CAPITAL CONTROL ROOM
        </div>

        <h2 style={{ margin: "7px 0" }}>
          Capital state unavailable
        </h2>

        <div
          style={{
            color: "#ff8b9b",
            marginTop: "8px",
          }}
        >
          {error || "No governed state returned."}
        </div>
      </section>
    );
  }

  const p = status.permissions;
  const capital = status.capital;

  const entryGap =
    capital.current_price !== undefined &&
    capital.maximum_qualifying_entry !== undefined
      ? capital.current_price -
        capital.maximum_qualifying_entry
      : null;

  const stages = [
    {
      name: "Research",
      value: p.qualified_research
        ? "QUALIFIED"
        : "BLOCKED",
      passed: p.qualified_research,
    },
    {
      name: "Thesis",
      value: status.thesis.invalidated
        ? "INVALIDATED"
        : stageLabel(status.thesis.status),
      passed: p.thesis_valid,
      watching:
        status.thesis.status ===
        "ACTIVE_WITH_WATCHES",
    },
    {
      name: "Entry",
      value:
        capital.decision === "APPROVED"
          ? "APPROVED"
          : stageLabel(capital.decision),
      passed: p.capital_approved,
      watching:
        capital.decision === "WAIT_FOR_ENTRY",
    },
    {
      name: "Sizing",
      value: p.position_sizing_ready
        ? "ELIGIBLE"
        : "LOCKED",
      passed: p.position_sizing_ready,
    },
    {
      name: "Authorization",
      value: p.paper_authorization_ready
        ? "READY"
        : "LOCKED",
      passed: p.paper_authorization_ready,
    },
    {
      name: "Paper Execution",
      value: p.paper_order_permission
        ? "AUTHORIZED"
        : "LOCKED",
      passed: p.paper_order_permission,
    },
  ];

  return (
    <section
      style={{
        ...panel,
        borderColor:
          capital.decision === "WAIT_FOR_ENTRY"
            ? "#80692d"
            : "#344354",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "20px",
          alignItems: "start",
          flexWrap: "wrap",
        }}
      >
        <div>
          <div style={label}>
            CAPITAL CONTROL ROOM
          </div>

          <h2
            style={{
              margin: "7px 0 5px",
              fontSize: "25px",
              color: "#f2f5f8",
              letterSpacing: "-0.4px",
            }}
          >
            Governed Capital Chain
          </h2>

          <div
            style={{
              color:
                capital.decision ===
                "WAIT_FOR_ENTRY"
                  ? "#e6bd5c"
                  : "#9ca9b8",
              fontWeight: 800,
              letterSpacing: "1px",
            }}
          >
            {stageLabel(status.stage)}
          </div>
        </div>

        <div
          style={{
            textAlign: "right",
            border: "1px solid #473d21",
            background: "#181409",
            borderRadius: "8px",
            padding: "11px 14px",
          }}
        >
          <div style={label}>
            CAPITAL AUTHORITY
          </div>

          <div
            style={{
              marginTop: "5px",
              color: "#ff6379",
              fontWeight: 900,
            }}
          >
            LOCKED
          </div>

          <div
            style={{
              color: "#837c69",
              fontSize: "11px",
              marginTop: "3px",
            }}
          >
            Paper mode only
          </div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(6, minmax(135px, 1fr))",
          gap: "9px",
          marginTop: "20px",
        }}
      >
        {stages.map((step) => (
          <div
            key={step.name}
            style={{
              border: `1px solid ${statusTone(
                step.passed,
                step.watching,
              )}`,
              borderRadius: "9px",
              padding: "13px",
              minHeight: "72px",
              background: "#080d13",
            }}
          >
            <div style={label}>
              {step.name}
            </div>

            <div
              style={{
                marginTop: "9px",
                color: statusTone(
                  step.passed,
                  step.watching,
                ),
                fontWeight: 900,
                fontSize: "12px",
              }}
            >
              {step.value}
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(5, minmax(150px, 1fr))",
          gap: "10px",
          marginTop: "18px",
        }}
      >
        <Metric
          label="Current Price"
          value={money(
            capital.current_price,
          )}
        />

        <Metric
          label="Max Entry"
          value={money(
            capital.maximum_qualifying_entry,
          )}
        />

        <Metric
          label="Reward / Risk"
          value={`${ratio(
            capital.reward_risk,
          )}x`}
        />

        <Metric
          label="Required R/R"
          value={`${ratio(
            capital.minimum_reward_risk,
          )}x`}
        />

        <Metric
          label="Entry Gap"
          value={
            entryGap !== null
              ? money(entryGap)
              : "—"
          }
        />
      </div>

      {capital.decision ===
        "WAIT_FOR_ENTRY" &&
        entryGap !== null &&
        entryGap > 0 && (
          <div
            style={{
              marginTop: "14px",
              border:
                "1px solid #5d4c24",
              background: "#171207",
              borderRadius: "8px",
              padding: "13px 15px",
              color: "#d9bd72",
              fontSize: "13px",
            }}
          >
            Entry gate is waiting. Under the
            current governed scenario model, the
            candidate needs approximately{" "}
            <strong>
              {money(entryGap)}
            </strong>{" "}
            of additional price improvement to
            reach the maximum qualifying entry.
          </div>
        )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "1fr 1fr",
          gap: "16px",
          marginTop: "18px",
        }}
      >
        <div
          style={{
            border: "1px solid #293440",
            borderRadius: "9px",
            padding: "14px",
            background: "#080c11",
          }}
        >
          <div style={label}>
            THESIS INVALIDATION
          </div>

          <div
            style={{
              marginTop: "8px",
              color: p.thesis_valid
                ? "#59c68c"
                : "#ff6379",
              fontWeight: 900,
            }}
          >
            {status.thesis.invalidated
              ? "INVALIDATED"
              : stageLabel(
                  status.thesis.status,
                )}
          </div>

          <div
            style={{
              color: "#8c99a8",
              fontSize: "12px",
              marginTop: "9px",
              lineHeight: 1.5,
            }}
          >
            Breached rules:{" "}
            {status.thesis.breached_rules
              .length
              ? status.thesis.breached_rules.join(
                  ", ",
                )
              : "None"}
          </div>
        </div>

        <div
          style={{
            border: "1px solid #293440",
            borderRadius: "9px",
            padding: "14px",
            background: "#080c11",
          }}
        >
          <div style={label}>
            WATCH OBLIGATIONS
          </div>

          {status.watch_obligations
            .length ? (
            <div
              style={{
                display: "grid",
                gap: "7px",
                marginTop: "9px",
              }}
            >
              {status.watch_obligations.map(
                (row, index) => (
                  <div
                    key={`${row.lane}-${row.fact_key}-${index}`}
                    style={{
                      color: "#d3b967",
                      fontSize: "12px",
                    }}
                  >
                    👀{" "}
                    {row.lane || "unknown"} /{" "}
                    {row.fact_key ||
                      "unknown"}{" "}
                    ·{" "}
                    {row.state ||
                      "WATCHING"}
                  </div>
                ),
              )}
            </div>
          ) : (
            <div
              style={{
                color: "#59c68c",
                marginTop: "9px",
                fontSize: "12px",
              }}
            >
              No governed watch obligations.
            </div>
          )}
        </div>
      </div>

      <div
        style={{
          marginTop: "16px",
          color: "#697687",
          fontSize: "11px",
          lineHeight: 1.5,
        }}
      >
        Read-only control surface. This panel
        cannot create an authorization, consume a
        token, submit a paper order, or enable
        live execution.
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div
      style={{
        border: "1px solid #293440",
        borderRadius: "9px",
        padding: "13px",
        background: "#080c11",
      }}
    >
      <div
        style={{
          color: "#758294",
          fontSize: "9px",
          letterSpacing: "1.6px",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>

      <div
        style={{
          marginTop: "7px",
          fontSize: "18px",
          fontWeight: 900,
        }}
      >
        {value}
      </div>
    </div>
  );
}

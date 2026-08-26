import { useEffect, useState } from "react";

const API = "http://localhost:8002";

type Room = {
  key: string;
  label: string;
  count: number;
  activity_count?: number;
};

type FactoryCase = {
  case_id: string;
  ticker?: string | null;
  topic?: string;
  stage: string;
  active_room?: string | null;
  latest_event?: string | null;
  latest_event_at?: string | null;
  committee?: string | null;
  committee_confidence?: number | null;
  risk?: string | null;
  qualified: boolean;
  capital?: string | null;
  sizing?: string | null;
  paper_execution?: string | null;
  live_execution: boolean;
};

type FactoryRoomStatus = {
  generated_at: string;
  activity?: {
    window_seconds: number;
    recent_event_count: number;
    agent_completions: number;
    committee_completions: number;
    risk_completions: number;
    latest_event?: {
      event_type?: string;
      case_id?: string;
      created_at?: string;
      room?: string;
    } | null;
  };
  rooms: Room[];
  cases: FactoryCase[];
  portfolio: {
    nav?: number | null;
    cash?: number | null;
    positions?: number | null;
    return_pct?: number | null;
    drawdown_pct?: number | null;
  };
  validation: {
    cases?: number | null;
    case_target: number;
    paper_orders?: number | null;
    paper_order_target: number;
    snapshots?: number | null;
    snapshot_target: number;
    postmortems?: number | null;
    postmortem_target: number;
    grok_pairs?: number | null;
    grok_target: number;
    structural_ready: boolean;
    empirical_ready: boolean;
    freeze_blockers: string[];
  };
  safety: {
    violations?: number | null;
    all_invariants: boolean;
    live_execution: boolean;
  };
};

function pct(n?: number | null) {
  if (n === undefined || n === null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function progress(
  value?: number | null,
  target = 1
) {
  const n = Number(value || 0);
  return Math.max(
    0,
    Math.min(
      100,
      (n / target) * 100
    )
  );
}

function stageTone(stage: string) {
  if (stage === "PAPER_PORTFOLIO") return "#63e6a5";
  if (
    stage === "AUTHORIZATION" ||
    stage === "POSITION_SIZING"
  ) return "#7fd5ff";
  if (stage === "CAPITAL" || stage === "QUALIFIED") {
    return "#e8c96b";
  }
  if (stage === "RISK") return "#ff8c73";
  if (stage === "COMMITTEE") return "#c9a8ff";
  return "#91a4ba";
}

export default function FactoryRoom() {
  const [data, setData] =
    useState<FactoryRoomStatus | null>(null);

  const [online, setOnline] =
    useState(false);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const response = await fetch(
          `${API}/factory-room/status`
        );

        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        const payload =
          (await response.json()) as FactoryRoomStatus;

        if (active) {
          setData(payload);
          setOnline(true);
        }
      } catch {
        if (active) {
          setOnline(false);
        }
      }
    };

    void load();

    const timer = window.setInterval(
      () => void load(),
      5000
    );

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const panel = {
    background:
      "linear-gradient(180deg, rgba(10,15,23,.96), rgba(5,8,12,.96))",
    border:
      "1px solid rgba(99, 142, 184, .22)",
    borderRadius: "16px",
    boxShadow:
      "0 18px 60px rgba(0,0,0,.32)",
  } as const;

  return (
    <section
      style={{
        ...panel,
        padding: "22px",
        marginBottom: "22px",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "end",
          gap: "20px",
          marginBottom: "20px",
        }}
      >
        <div>
          <div
            style={{
              color: "#68809a",
              fontSize: "10px",
              letterSpacing: "3px",
              fontWeight: 800,
            }}
          >
            LIVE OPERATIONS FLOOR
          </div>

          <h2
            style={{
              margin: "6px 0 3px",
              fontSize: "27px",
            }}
          >
            THE FACTORY ROOM
          </h2>

          <div
            style={{
              color: "#728398",
              fontSize: "12px",
            }}
          >
            Candidates physically move through the governed
            research and paper-capital chain.
          </div>
        </div>

        <div
          style={{
            textAlign: "right",
          }}
        >
          <div
            style={{
              color: online
                ? "#63e6a5"
                : "#ff6d7c",
              fontWeight: 900,
              fontSize: "11px",
              letterSpacing: "2px",
            }}
          >
            {online
              ? "FACTORY LIVE"
              : "FACTORY DATA OFFLINE"}
          </div>

          <div
            style={{
              color: "#77879a",
              fontSize: "11px",
              marginTop: "5px",
            }}
          >
            PAPER / SHADOW · LIVE CAPITAL LOCKED
          </div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(4, minmax(140px, 1fr))",
          gap: "9px",
          marginBottom: "12px",
        }}
      >
        {[
          [
            "EVENTS · 5M",
            data?.activity?.recent_event_count || 0,
          ],
          [
            "DESKS COMPLETE · 5M",
            data?.activity?.agent_completions || 0,
          ],
          [
            "COMMITTEES · 5M",
            data?.activity?.committee_completions || 0,
          ],
          [
            "RISK PASSES · 5M",
            data?.activity?.risk_completions || 0,
          ],
        ].map(([label, value]) => (
          <div
            key={String(label)}
            style={{
              padding: "10px 12px",
              border: "1px solid #263441",
              borderRadius: "9px",
              background: "rgba(9,15,22,.85)",
            }}
          >
            <div
              style={{
                color: "#63788e",
                fontSize: "8px",
                letterSpacing: "1.4px",
              }}
            >
              {label}
            </div>

            <div
              style={{
                marginTop: "4px",
                color: Number(value) > 0
                  ? "#63e6a5"
                  : "#58687a",
                fontSize: "20px",
                fontWeight: 900,
              }}
            >
              {value}
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(7, minmax(135px, 1fr))",
          gap: "9px",
          marginBottom: "20px",
          overflowX: "auto",
        }}
      >
        {(data?.rooms || []).map(
          (room, index) => (
            <div
              key={room.key}
              style={{
                minWidth: "135px",
                padding: "15px 13px",
                borderRadius: "10px",
                border:
                  "1px solid #283646",
                background:
                  "rgba(14, 22, 32, .8)",
                position: "relative",
              }}
            >
              <div
                style={{
                  color: "#5d7188",
                  fontSize: "9px",
                  letterSpacing: "1.5px",
                }}
              >
                ROOM {index + 1}
              </div>

              <div
                style={{
                  marginTop: "8px",
                  fontSize: "12px",
                  fontWeight: 800,
                }}
              >
                {room.label}
              </div>

              <div
                style={{
                  marginTop: "13px",
                  display: "flex",
                  alignItems: "baseline",
                  gap: "8px",
                }}
              >
                <span
                  style={{
                    fontSize: "27px",
                    fontWeight: 900,
                    color:
                      room.count > 0
                        ? "#b9dcff"
                        : "#455363",
                  }}
                >
                  {room.count}
                </span>

                <span
                  style={{
                    color:
                      (room.activity_count || 0) > 0
                        ? "#63e6a5"
                        : "#465565",
                    fontSize: "10px",
                    fontWeight: 900,
                    letterSpacing: "1px",
                  }}
                >
                  LIVE +{room.activity_count || 0}
                </span>
              </div>
            </div>
          )
        )}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "1.45fr .75fr",
          gap: "14px",
        }}
      >
        <div
          style={{
            border:
              "1px solid #202c38",
            borderRadius: "12px",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "12px 14px",
              background: "#0a1017",
              color: "#71849a",
              fontSize: "10px",
              letterSpacing: "2px",
              fontWeight: 800,
            }}
          >
            LIVE CASE CONVEYOR
          </div>

          <div
            style={{
              maxHeight: "325px",
              overflowY: "auto",
            }}
          >
            {(data?.cases || [])
              .slice()
              .reverse()
              .slice(0, 20)
              .map((row) => (
                <div
                  key={row.case_id}
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      "80px 145px 1fr 115px",
                    gap: "10px",
                    alignItems: "center",
                    padding: "11px 14px",
                    borderTop:
                      "1px solid #19232d",
                    fontSize: "11px",
                  }}
                >
                  <div
                    style={{
                      fontWeight: 900,
                      color: "#dce8f4",
                    }}
                  >
                    {row.ticker || "—"}
                  </div>

                  <div
                    style={{
                      color: stageTone(
                        row.stage
                      ),
                      fontWeight: 800,
                      fontSize: "10px",
                      letterSpacing: ".5px",
                    }}
                  >
                    {(row.active_room || row.stage).replaceAll(
                      "_",
                      " "
                    )}
                    {row.active_room ? " • LIVE" : ""}
                  </div>

                  <div
                    style={{
                      color: "#8392a3",
                      overflow: "hidden",
                      textOverflow:
                        "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row.topic || row.case_id}
                  </div>

                  <div
                    style={{
                      color:
                        row.risk ===
                        "VETOED"
                          ? "#ff8775"
                          : "#8aa0b6",
                      textAlign: "right",
                    }}
                  >
                    {row.committee || "—"}
                    {" / "}
                    {row.risk || "—"}
                  </div>
                </div>
              ))}

            {!data?.cases?.length && (
              <div
                style={{
                  padding: "22px",
                  color: "#657688",
                }}
              >
                Waiting for live cases.
              </div>
            )}
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gap: "10px",
          }}
        >
          <div
            style={{
              padding: "15px",
              border:
                "1px solid #263441",
              borderRadius: "12px",
              background:
                "rgba(10,16,23,.85)",
            }}
          >
            <div
              style={{
                color: "#6f8399",
                fontSize: "9px",
                letterSpacing: "2px",
              }}
            >
              PAPER PORTFOLIO
            </div>

            <div
              style={{
                marginTop: "8px",
                fontSize: "24px",
                fontWeight: 900,
              }}
            >
              $
              {Number(
                data?.portfolio.nav || 0
              ).toLocaleString(
                undefined,
                {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                }
              )}
            </div>

            <div
              style={{
                marginTop: "6px",
                color: "#8192a5",
                fontSize: "11px",
              }}
            >
              Cash $
              {Number(
                data?.portfolio.cash || 0
              ).toLocaleString()}
              {" · "}
              {data?.portfolio.positions || 0}
              {" positions · "}
              {pct(
                data?.portfolio.return_pct
              )}
            </div>
          </div>

          <div
            style={{
              padding: "15px",
              border:
                "1px solid #263441",
              borderRadius: "12px",
              background:
                "rgba(10,16,23,.85)",
            }}
          >
            <div
              style={{
                color: "#6f8399",
                fontSize: "9px",
                letterSpacing: "2px",
                marginBottom: "11px",
              }}
            >
              VALIDATION PROGRESS
            </div>

            {[
              [
                "Cases",
                data?.validation.cases,
                data?.validation.case_target,
              ],
              [
                "Paper orders",
                data?.validation.paper_orders,
                data?.validation.paper_order_target,
              ],
              [
                "Snapshots",
                data?.validation.snapshots,
                data?.validation.snapshot_target,
              ],
              [
                "Postmortems",
                data?.validation.postmortems,
                data?.validation.postmortem_target,
              ],
              [
                "Grok A/B",
                data?.validation.grok_pairs,
                data?.validation.grok_target,
              ],
            ].map(
              ([label, value, target]) => (
                <div
                  key={String(label)}
                  style={{
                    marginBottom: "9px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent:
                        "space-between",
                      color: "#8494a6",
                      fontSize: "10px",
                      marginBottom: "4px",
                    }}
                  >
                    <span>{label}</span>
                    <span>
                      {Number(value || 0)}
                      /
                      {Number(target || 0)}
                    </span>
                  </div>

                  <div
                    style={{
                      height: "5px",
                      background: "#18222c",
                      borderRadius: "5px",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        width:
                          `${progress(
                            Number(value || 0),
                            Number(target || 1)
                          )}%`,
                        height: "100%",
                        background:
                          "linear-gradient(90deg,#31628d,#68b4df)",
                      }}
                    />
                  </div>
                </div>
              )
            )}
          </div>

          <div
            style={{
              padding: "14px",
              border:
                data?.safety
                  .all_invariants
                  ? "1px solid #28533e"
                  : "1px solid #6c2731",
              borderRadius: "12px",
              background:
                data?.safety
                  .all_invariants
                  ? "rgba(10,39,28,.58)"
                  : "rgba(55,12,19,.58)",
              fontSize: "11px",
            }}
          >
            <strong>
              SAFETY{" "}
              {data?.safety
                .all_invariants
                ? "GREEN"
                : "CHECK"}
            </strong>
            <div
              style={{
                marginTop: "5px",
                color: "#8696a6",
              }}
            >
              Violations:{" "}
              {data?.safety
                .violations ?? "—"}
              {" · "}
              Live execution: FALSE
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

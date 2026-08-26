import {
  useEffect,
  useState,
} from "react";

import PrimaryEvidencePanel
  from "./PrimaryEvidencePanel";


const API =
  "http://localhost:8002";

const ACTIVE_CASE_KEY =
  "iios.activeCaseId";


type Profile = {
  case_id: string;
  ticker?: string | null;
  company?: string | null;
  sector_profile?: string | null;
  is_micron: boolean;
};


type EvidenceStatus = {
  mode: string;
  record_count?: number;
  lane_counts?: Record<
    string,
    number
  >;
  profile: Profile;
};


export default function CaseAwarePrimaryEvidencePanel() {
  const [
    caseId,
    setCaseId,
  ] = useState<string | null>(
    () =>
      window.localStorage.getItem(
        ACTIVE_CASE_KEY
      )
  );

  const [
    profile,
    setProfile,
  ] = useState<Profile | null>(
    null
  );

  const [
    evidence,
    setEvidence,
  ] = useState<EvidenceStatus | null>(
    null
  );

  const [
    busy,
    setBusy,
  ] = useState(false);

  const [
    message,
    setMessage,
  ] = useState(
    "Generic evidence uses company, market, policy, operating, external, and governed portfolio lanes."
  );


  useEffect(() => {
    const timer =
      window.setInterval(
        () => {
          const next =
            window.localStorage.getItem(
              ACTIVE_CASE_KEY
            );

          setCaseId(
            current =>
              current === next
                ? current
                : next
          );
        },
        1000
      );

    return () =>
      window.clearInterval(timer);
  }, []);


  const load = async (
    selected: string
  ) => {
    const [
      pResponse,
      eResponse,
    ] = await Promise.all([
      fetch(
        `${API}/factory-genericization/${selected}/profile`
      ),
      fetch(
        `${API}/factory-genericization/${selected}/evidence`
      ),
    ]);

    if (!pResponse.ok) {
      throw new Error(
        `Case profile failed: ${pResponse.status}`
      );
    }

    if (!eResponse.ok) {
      throw new Error(
        `Evidence status failed: ${eResponse.status}`
      );
    }

    const profileData =
      await pResponse.json();

    const evidenceData =
      await eResponse.json();

    setProfile(
      profileData as Profile
    );

    setEvidence(
      evidenceData as EvidenceStatus
    );
  };


  useEffect(() => {
    if (!caseId) {
      setProfile(null);
      setEvidence(null);
      return;
    }

    void load(caseId).catch(
      error =>
        setMessage(
          error instanceof Error
            ? error.message
            : "Case-aware evidence unavailable"
        )
    );
  }, [caseId]);


  if (!caseId) {
    return null;
  }


  if (
    profile?.is_micron
  ) {
    return (
      <PrimaryEvidencePanel />
    );
  }


  const capture = async () => {
    if (!caseId) return;

    setBusy(true);

    setMessage(
      "Capturing generic company, market, operating, policy, external and portfolio evidence..."
    );

    try {
      const response =
        await fetch(
          `${API}/generic-primary-evidence/${caseId}/capture`,
          {
            method: "POST",
          }
        );

      if (!response.ok) {
        throw new Error(
          await response.text()
        );
      }

      const result = (
        await response.json()
      ) as {
        records_seen_or_added?: number;
        failure_count?: number;
      };

      setMessage(
        `Capture complete: ${
          result.records_seen_or_added ?? 0
        } record(s); ${
          result.failure_count ?? 0
        } provider issue(s).`
      );

      await load(caseId);

    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Generic evidence capture failed"
      );

    } finally {
      setBusy(false);
    }
  };


  const lanes =
    evidence?.lane_counts
    || {};

  const cards = [
    [
      "Company Financials",
      "generic_company_financials",
    ],
    [
      "Market / Valuation",
      "generic_market_context",
    ],
    [
      "Operating KPIs",
      "generic_operating_context",
    ],
    [
      "Policy / Regulation",
      "generic_policy_context",
    ],
    [
      "Independent Context",
      "generic_external_context",
    ],
    [
      "Portfolio Context",
      "generic_portfolio_context",
    ],
  ];


  return (
    <section
      style={{
        margin:
          "0 28px 28px",
        color:
          "#f2f5f8",
        fontFamily:
          "Inter, ui-sans-serif, system-ui, sans-serif",
      }}
    >
      <div
        style={{
          background:
            "rgba(7,11,17,.97)",
          border:
            "1px solid #315867",
          borderRadius:
            "14px",
          padding:
            "22px",
        }}
      >
        <div
          style={{
            color:
              "#6d8795",
            fontSize:
              "10px",
            letterSpacing:
              "2px",
          }}
        >
          GENERIC PRIMARY EVIDENCE · CASE AWARE
        </div>

        <div
          style={{
            display:
              "flex",
            justifyContent:
              "space-between",
            gap:
              "18px",
            alignItems:
              "start",
            flexWrap:
              "wrap",
          }}
        >
          <div>
            <h2
              style={{
                margin:
                  "8px 0 5px",
              }}
            >
              {profile?.company
                || profile?.ticker
                || "Public Company"}{" "}
              Evidence Room
            </h2>

            <div
              style={{
                color:
                  "#8f9dab",
                fontSize:
                  "13px",
              }}
            >
              Ticker{" "}
              {profile?.ticker
                || "—"}{" "}
              ·{" "}
              {profile?.sector_profile
                || "GENERIC_PUBLIC_COMPANY"}
            </div>
          </div>

          <button
            onClick={
              () =>
                void capture()
            }
            disabled={
              busy
            }
            style={{
              border:
                "1px solid #397789",
              background:
                "#0b2630",
              color:
                "#d9f4f7",
              borderRadius:
                "8px",
              padding:
                "12px 16px",
              fontWeight:
                900,
            }}
          >
            {busy
              ? "CAPTURING..."
              : "AUTO CAPTURE CASE EVIDENCE"}
          </button>
        </div>

        <div
          style={{
            marginTop:
              "14px",
            color:
              "#94a2b1",
            fontSize:
              "12px",
          }}
        >
          {message}
        </div>

        <div
          style={{
            display:
              "grid",
            gridTemplateColumns:
              "repeat(3, minmax(170px,1fr))",
            gap:
              "10px",
            marginTop:
              "17px",
          }}
        >
          {cards.map(
            ([
              label,
              key,
            ]) => (
              <div
                key={
                  key
                }
                style={{
                  border:
                    "1px solid #273746",
                  borderRadius:
                    "10px",
                  padding:
                    "15px",
                  background:
                    "#080d12",
                }}
              >
                <div
                  style={{
                    color:
                      "#708397",
                    fontSize:
                      "9px",
                    letterSpacing:
                      "1.4px",
                  }}
                >
                  {label}
                </div>

                <div
                  style={{
                    marginTop:
                      "7px",
                    fontSize:
                      "24px",
                    fontWeight:
                      900,
                    color:
                      Number(
                        lanes[
                          key
                        ]
                        || 0
                      ) > 0
                        ? "#67cf95"
                        : "#667586",
                  }}
                >
                  {lanes[
                    key
                  ] || 0}
                </div>
              </div>
            )
          )}
        </div>

        <div
          style={{
            marginTop:
              "15px",
            color:
              "#778698",
            fontSize:
              "11px",
          }}
        >
          Records:{" "}
          <strong>
            {evidence?.record_count
              ?? 0}
          </strong>
          {" · "}
          PAPER / SHADOW ONLY
          {" · "}
          LIVE EXECUTION FALSE
        </div>
      </div>
    </section>
  );
}

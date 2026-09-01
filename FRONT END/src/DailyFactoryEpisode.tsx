import { useEffect, useMemo, useState } from "react";
import { telemetryUrl } from "./telemetryEndpoint";
import "./DailyFactoryEpisode.css";
import "./Batch9OTruthSeal.css";

type JsonObject = Record<string, unknown>;
type Layer = { availability?: string; payload?: JsonObject | null };
type LivingSnapshot = {
  generated_at?: string;
  validation?: {
    layers?: {
      factory_telemetry?: Layer;
      market_validation?: Layer;
      shadow_strategy?: Layer;
      outcome_learning?: Layer;
    };
  };
  safety?: {
    backend_access?: string;
    backend_write_permission?: boolean;
    trade_execution_permission?: boolean;
    live_execution?: boolean;
  };
};

type EpisodeRow = JsonObject;
type Episode = {
  schema_version?: string;
  generated_at?: string;
  episode_session_id?: string | null;
  status?: string;
  title?: string;
  source_freshness?: JsonObject;
  scoreboard?: {
    validation?: JsonObject;
    paper?: JsonObject;
    best_call_count?: number;
    save_count?: number;
    dumb_call_count?: number;
    validation_miss_count?: number;
    validation_miss_detail_count?: number;
    learning_outcome_count?: number;
  };
  best_calls?: EpisodeRow[];
  saves?: EpisodeRow[];
  dumb_calls?: EpisodeRow[];
  misses?: EpisodeRow[];
  learning_misses?: EpisodeRow[];
  what_we_learned?: JsonObject;
  tomorrow_focus?: EpisodeRow[];
  story?: Array<{ speaker?: string; line?: string; basis?: string }>;
  safety?: JsonObject;
};

const BEST = new Set(["PAPER_ENTRY_FAVORABLE", "WATCH_VALIDATED_BY_UPSIDE"]);
const SAVES = new Set(["NO_TRADE_AVOIDED_DOWNSIDE"]);
const DUMB = new Set([
  "PAPER_ENTRY_ADVERSE",
  "WATCH_FALSE_POSITIVE_OR_REVERSAL",
  "NO_TRADE_FOREGONE_UPSIDE",
]);
const LEARNING_MISS = new Set(["FACTORY_MISS_WITH_UPSIDE"]);

function record(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function rows(value: unknown): EpisodeRow[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is EpisodeRow =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

function text(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function money(value: unknown): string {
  const n = numberValue(value);
  return n === null
    ? "—"
    : n.toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      });
}

function percent(value: unknown, decimals = 1): string {
  const n = numberValue(value);
  return n === null ? "—" : `${n.toFixed(decimals)}%`;
}

function sessionIdFromLiving(snapshot: LivingSnapshot): string | null {
  const layers = snapshot.validation?.layers;
  const scorecard = record(layers?.market_validation?.payload);
  const learning = record(layers?.outcome_learning?.payload);
  const input = record(scorecard.input);
  for (const candidate of [scorecard.session_id, input.session_id, learning.latest_session_id]) {
    const value = text(candidate, "");
    if (value) return value;
  }
  return null;
}

function sortReturn(row: EpisodeRow): number {
  return numberValue(row.relative_return_pct) ?? numberValue(row.forward_return_pct) ?? 0;
}

function compactOutcome(row: EpisodeRow): EpisodeRow {
  return {
    ticker: text(row.ticker, "NO TICKER").toUpperCase(),
    case_id: row.case_id,
    candidate_id: row.candidate_id,
    opportunity_id: row.opportunity_id,
    session_id: row.session_id,
    decision_quality: row.decision_quality ?? row.decision_quality_label,
    market_outcome: row.market_outcome ?? row.market_outcome_label,
    final_disposition: row.final_disposition,
    longest_available_horizon: row.longest_available_horizon,
    forward_return_pct: row.forward_return_pct,
    benchmark_return_pct: row.benchmark_return_pct,
    relative_return_pct: row.relative_return_pct,
    benchmark_source: row.benchmark_source,
    measured_at: row.measured_at,
  };
}

function aggregateMissCount(metrics: JsonObject, detailCount: number): number {
  for (const key of [
    "eventual_opportunity_miss_count",
    "opportunity_miss_count",
    "missed_opportunity_count",
    "miss_count",
  ]) {
    const explicit = numberValue(metrics[key]);
    if (explicit !== null) return Math.max(detailCount, Math.max(0, Math.round(explicit)));
  }
  const benchmark = numberValue(metrics.benchmark_opportunity_count ?? metrics.opportunity_count) ?? 0;
  const detected =
    numberValue(
      metrics.eventual_detected_count ??
        metrics.radar_detected_count ??
        metrics.detected_count,
    ) ?? 0;
  return Math.max(detailCount, Math.max(0, Math.round(benchmark - detected)));
}

function buildDraft(snapshot: LivingSnapshot): Episode {
  const layers = snapshot.validation?.layers;
  const telemetry = record(layers?.factory_telemetry?.payload);
  const scorecard = record(layers?.market_validation?.payload);
  const shadow = record(layers?.shadow_strategy?.payload);
  const learning = record(layers?.outcome_learning?.payload);
  const metrics = record(scorecard.metrics);
  const paper = record(telemetry.paper_fund);
  const sessionId = sessionIdFromLiving(snapshot);
  const allOutcomes = rows(learning.recent_outcomes);
  const matchingOutcomes = sessionId
    ? allOutcomes.filter((row) => text(row.session_id, "") === sessionId)
    : allOutcomes;
  const outcomes = matchingOutcomes.map(compactOutcome);
  const best = outcomes
    .filter((row) => BEST.has(text(row.decision_quality, "")))
    .sort((a, b) => sortReturn(b) - sortReturn(a));
  const saves = outcomes
    .filter((row) => SAVES.has(text(row.decision_quality, "")))
    .sort((a, b) => sortReturn(a) - sortReturn(b));
  const dumb = outcomes
    .filter((row) => DUMB.has(text(row.decision_quality, "")))
    .sort((a, b) => Math.abs(sortReturn(b)) - Math.abs(sortReturn(a)));
  const learningMisses = outcomes
    .filter((row) => LEARNING_MISS.has(text(row.decision_quality, "")))
    .sort((a, b) => sortReturn(b) - sortReturn(a));

  const misses = rows(scorecard.opportunities)
    .filter((row) => (row.eventually_detected ?? row.detected) !== true)
    .map((row) => ({
      ticker: text(row.ticker, "NO TICKER").toUpperCase(),
      opportunity_id: row.opportunity_id,
      move_pct: row.move_pct,
      importance: row.importance,
      source: row.source,
      miss_reason: row.miss_reason ?? "NOT_DETECTED_IN_VALIDATION_WINDOW",
      case_id: row.case_id,
    }))
    .sort(
      (a, b) =>
        Math.abs(numberValue(b.move_pct) ?? 0) -
        Math.abs(numberValue(a.move_pct) ?? 0),
    );

  const benchmarkCount = numberValue(metrics.benchmark_opportunity_count ?? metrics.opportunity_count) ?? 0;
  const detectedCount =
    numberValue(
      metrics.eventual_detected_count ??
        metrics.radar_detected_count ??
        metrics.detected_count,
    ) ?? 0;
  const promotedCount =
    numberValue(
      metrics.eventual_promotion_count ??
        metrics.promotion_count ??
        metrics.promoted_count,
    ) ?? 0;
  const detectionRate = metrics.eventual_detection_rate_pct ?? metrics.detection_rate_pct;
  const missRate = metrics.eventual_opportunity_miss_rate_pct ?? metrics.opportunity_miss_rate_pct;
  const aggregateMiss = aggregateMissCount(metrics, misses.length);

  const qualityCounts: Record<string, number> = {};
  for (const row of outcomes) {
    const key = text(row.decision_quality, "UNKNOWN");
    qualityCounts[key] = (qualityCounts[key] ?? 0) + 1;
  }

  const focus: EpisodeRow[] = [];
  if (aggregateMiss > 0) {
    focus.push({
      priority: "RADAR_MISS_REVIEW",
      why: `9H reports ${aggregateMiss} aggregate validation miss(es), with ${misses.length} detailed miss row(s) exposed; miss rate ${percent(missRate)}.`,
      action: "REVIEW_MISSES_BEFORE_ANY_THRESHOLD_CHANGE",
      authority: "HUMAN_REVIEW_ONLY",
    });
  }
  for (const recommendation of rows(shadow.recommendations).slice(0, 3)) {
    focus.push({
      priority: recommendation.type ?? "SHADOW_REVIEW",
      why: recommendation.reason ?? "9I produced a persisted advisory recommendation.",
      action: recommendation.action ?? "HUMAN_REVIEW_ONLY",
      scenario_id: recommendation.scenario_id,
      authority: "ADVISORY_ONLY",
    });
  }
  if (!focus.length) {
    focus.push({
      priority: "HOLD_GOVERNED_BASELINE",
      why: "No persisted miss or shadow condition currently demands a change.",
      action: "KEEP_CURRENT_GOVERNED_CONFIGURATION",
      authority: "NO_CHANGE",
    });
  }

  const story: Episode["story"] = [
    {
      speaker: "MAX",
      line: `Factory close: ${benchmarkCount} benchmark opportunities, ${detectedCount} detected, ${aggregateMiss} missed by the aggregate 9H metric. Detailed miss records exposed: ${misses.length}.`,
      basis: "Current persisted 9H aggregate validation metrics plus any detailed miss rows exposed by the scorecard.",
    },
  ];
  if (best[0]) {
    story.push({
      speaker: "MAX",
      line: `Best measured call so far: ${text(best[0].ticker)} · ${text(best[0].decision_quality)} · ${percent(best[0].forward_return_pct)} forward. Nice. Nobody gets a statue.`,
      basis: "Current persisted 9J decision quality and forward return.",
    });
  }
  if (saves[0]) {
    story.push({
      speaker: "SKEPTIC",
      line: `Save file: ${text(saves[0].ticker)} · ${text(saves[0].decision_quality)} · ${percent(saves[0].forward_return_pct)}. Sometimes the best trade is the one we did not screw up.`,
      basis: "Current persisted 9J NO_TRADE_AVOIDED_DOWNSIDE label.",
    });
  }
  if (dumb[0]) {
    story.push({
      speaker: "SKEPTIC",
      line: `Dumb-call file: ${text(dumb[0].ticker)} · ${text(dumb[0].decision_quality)}. Put it under glass and learn from the damn thing.`,
      basis: "Current persisted adverse/foregone-upside 9J label.",
    });
  }
  if (numberValue(paper.nav) !== null) {
    story.push({
      speaker: "PORTFOLIO",
      line: `Paper book snapshot: NAV ${money(paper.nav)}, total P&L ${money(paper.total_pnl)}. Paper is measurement, not a permission slip for real capital.`,
      basis: "Current persisted 9G governed paper snapshot.",
    });
  }

  return {
    schema_version: "batch9o-daily-factory-episode-v1",
    generated_at: snapshot.generated_at,
    episode_session_id: sessionId,
    status: "LIVE_DRAFT",
    title: `IIOS Daily Factory Episode · ${sessionId ?? "SESSION WARM-UP"}`,
    source_freshness: {
      scorecard_generated_at: scorecard.generated_at,
      shadow_generated_at: shadow.generated_at,
      learning_generated_at: learning.generated_at,
      telemetry_generated_at: telemetry.generated_at,
      learning_session_match: Boolean(sessionId && matchingOutcomes.length),
    },
    scoreboard: {
      validation: {
        benchmark_opportunity_count: benchmarkCount,
        detected_count: detectedCount,
        promoted_count: promotedCount,
        detection_rate_pct: detectionRate,
        opportunity_miss_rate_pct: missRate,
        aggregate_miss_count: aggregateMiss,
      },
      paper,
      best_call_count: best.length,
      save_count: saves.length,
      dumb_call_count: dumb.length,
      validation_miss_count: aggregateMiss,
      validation_miss_detail_count: misses.length,
      learning_outcome_count: outcomes.length,
    },
    best_calls: best,
    saves,
    dumb_calls: dumb,
    misses,
    learning_misses: learningMisses,
    what_we_learned: {
      decision_quality_counts: qualityCounts,
      learning_status: learning.status,
      outcome_count: learning.outcome_count,
      mature_5d_count: learning.mature_5d_count,
      shadow_status: shadow.status,
      shadow_complete_session_count: shadow.complete_session_count,
    },
    tomorrow_focus: focus.slice(0, 5),
    story,
    safety: {
      report_only: true,
      source_mode: "PERSISTED_9G_9H_9I_9J_READ_ONLY",
      direct_ledger_access: false,
      auto_apply_threshold_changes: false,
      agent_weight_change_authority: false,
      capital_authority: false,
      trade_execution_permission: false,
      live_execution: false,
    },
  };
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function EpisodeMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="dfe-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </div>
  );
}

function OutcomeList({
  title,
  subtitle,
  rows: list,
  empty,
  count,
}: {
  title: string;
  subtitle: string;
  rows: EpisodeRow[];
  empty: string;
  count?: number;
}) {
  return (
    <article className="dfe-list-card">
      <header>
        <div>
          <span>{subtitle}</span>
          <h4>{title}</h4>
        </div>
        <strong>{count ?? list.length}</strong>
      </header>
      <div className="dfe-rows">
        {list.slice(0, 6).map((row, index) => (
          <div key={`${text(row.ticker)}:${text(row.case_id, String(index))}`}>
            <strong>{text(row.ticker, "NO TICKER")}</strong>
            <span>{text(row.decision_quality, text(row.miss_reason, "PERSISTED"))}</span>
            <em>
              {row.forward_return_pct !== undefined
                ? percent(row.forward_return_pct)
                : percent(row.move_pct)}
            </em>
          </div>
        ))}
        {!list.length ? <p>{empty}</p> : null}
      </div>
    </article>
  );
}

function normalizedMissCount(episode: Episode): number {
  const validation = record(episode.scoreboard?.validation);
  const detail = episode.misses?.length ?? 0;
  const reported = episode.scoreboard?.validation_miss_count ?? 0;
  const metricAggregate = numberValue(validation.aggregate_miss_count);
  const benchmark = numberValue(validation.benchmark_opportunity_count) ?? 0;
  const detected = numberValue(validation.detected_count) ?? 0;
  return Math.max(
    detail,
    reported,
    metricAggregate ?? 0,
    Math.max(0, Math.round(benchmark - detected)),
  );
}

function normalizeStory(episode: Episode): Episode["story"] {
  const validation = record(episode.scoreboard?.validation);
  const benchmark = numberValue(validation.benchmark_opportunity_count) ?? 0;
  const detected = numberValue(validation.detected_count) ?? 0;
  const aggregate = normalizedMissCount(episode);
  const detail = episode.misses?.length ?? 0;
  const rest = (episode.story ?? []).filter(
    (line, index) => !(index === 0 && text(line.speaker, "").toUpperCase() === "MAX"),
  );
  return [
    {
      speaker: "MAX",
      line: `Factory close: ${benchmark} benchmark opportunities, ${detected} detected, ${aggregate} missed by the aggregate 9H metric. Detailed miss records exposed: ${detail}.`,
      basis: "9H persisted aggregate validation metrics plus any detailed miss rows exposed by the scorecard.",
    },
    ...rest,
  ];
}

export default function DailyFactoryEpisode() {
  const [living, setLiving] = useState<LivingSnapshot | null>(null);
  const [persisted, setPersisted] = useState<Episode | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let timer: number | null = null;
    let controller: AbortController | null = null;
    const refresh = async () => {
      controller = new AbortController();
      try {
        const nextLiving = await fetchJson<LivingSnapshot>(
          telemetryUrl("/living/overview"),
          controller.signal,
        );
        let nextPersisted: Episode | null = null;
        try {
          nextPersisted = await fetchJson<Episode>(
            `/daily_factory_episode.json?ts=${Date.now()}`,
            controller.signal,
          );
        } catch {
          nextPersisted = null;
        }
        if (disposed) return;
        setLiving(nextLiving);
        setPersisted(nextPersisted);
        setError(null);
      } catch (reason) {
        if (
          disposed ||
          (reason instanceof DOMException && reason.name === "AbortError")
        ) {
          return;
        }
        setError(
          reason instanceof Error
            ? reason.message
            : "Daily episode source unavailable",
        );
      } finally {
        if (!disposed) timer = window.setTimeout(() => void refresh(), 15_000);
      }
    };
    void refresh();
    return () => {
      disposed = true;
      controller?.abort();
      if (timer !== null) window.clearTimeout(timer);
    };
  }, []);

  const draft = useMemo(() => (living ? buildDraft(living) : null), [living]);
  const episode = useMemo(() => {
    if (!draft) return persisted;
    const persistedStatus = text(persisted?.status, "");
    const sameSession = Boolean(
      persisted?.episode_session_id &&
        persisted.episode_session_id === draft.episode_session_id,
    );
    if (persisted && sameSession && persistedStatus.startsWith("FINAL")) {
      return persisted;
    }
    return draft;
  }, [draft, persisted]);

  if (!episode) {
    return (
      <section className="dfe-shell dfe-waiting">
        <span>BATCH 9O · DAILY FACTORY EPISODE</span>
        <h2>
          {error
            ? "EPISODE SOURCE WARM-UP"
            : "ASSEMBLING TODAY'S PERSISTED FACTORY STORY"}
        </h2>
        <p>
          {error ??
            "No episode claim is rendered until 9G/9H/9I/9J state exists."}
        </p>
      </section>
    );
  }

  const validation = record(episode.scoreboard?.validation);
  const paper = record(episode.scoreboard?.paper);
  const learned = record(episode.what_we_learned);
  const qualityCounts = record(learned.decision_quality_counts);
  const final = text(episode.status).startsWith("FINAL");
  const sourceFreshness = record(episode.source_freshness);
  const missCount = normalizedMissCount(episode);
  const missDetailCount = episode.misses?.length ?? 0;
  const story = normalizeStory(episode);

  return (
    <section className="dfe-shell">
      <div className="dfe-hero">
        <div>
          <span>BATCH 9O · DAILY FACTORY EPISODE</span>
          <h2>{episode.title ?? "IIOS Daily Factory Episode"}</h2>
          <p>
            Best calls, saves, misses, dumb calls, governed paper performance,
            what the factory learned, and tomorrow's focus — all derived from
            persisted IIOS evidence.
          </p>
        </div>
        <div className={`dfe-status ${final ? "is-final" : "is-draft"}`}>
          <strong>{text(episode.status, "WARM-UP").replaceAll("_", " ")}</strong>
          <span>
            {final ? "PERSISTED END-OF-DAY ARTIFACT" : "LIVE READ-ONLY DRAFT"}
          </span>
          <em>LIVE EXECUTION FALSE</em>
        </div>
      </div>

      <div className="dfe-contract">
        <span>SOURCES · 9G + 9H + 9I + 9J PERSISTED DATA</span>
        <span>
          LEARNING SESSION MATCH · {text(sourceFreshness.learning_session_match, "FALSE")}
        </span>
        <span>REPORT ONLY · NO THRESHOLD / WEIGHT / CAPITAL AUTHORITY</span>
      </div>

      <div className="dfe-scoreboard">
        <EpisodeMetric
          label="Benchmark opportunities"
          value={text(validation.benchmark_opportunity_count, "0")}
        />
        <EpisodeMetric
          label="Detected"
          value={text(validation.detected_count, "0")}
          detail={percent(validation.detection_rate_pct)}
        />
        <EpisodeMetric
          label="Validation misses"
          value={String(missCount)}
          detail={`${percent(validation.opportunity_miss_rate_pct)} · ${missDetailCount} detailed`}
        />
        <EpisodeMetric
          label="Paper NAV"
          value={money(paper.nav)}
          detail={`P&L ${money(paper.total_pnl)}`}
        />
        <EpisodeMetric
          label="Paper positions"
          value={text(paper.position_count, "0")}
          detail={`Drawdown ${percent(paper.current_drawdown_pct)}`}
        />
        <EpisodeMetric
          label="9J outcomes"
          value={text(episode.scoreboard?.learning_outcome_count, "0")}
          detail={`${text(learned.mature_5d_count, "0")} mature 5d`}
        />
      </div>

      <div className="dfe-story">
        <div className="dfe-section-heading">
          <div>
            <span>THE FACTORY CLOSE</span>
            <h3>Today's episode</h3>
          </div>
          <strong>{final ? "FINAL CUT" : "LIVE CUT"}</strong>
        </div>
        <div className="dfe-story-lines">
          {(story ?? []).map((line, index) => (
            <div key={`${line.speaker ?? "FACTORY"}:${index}`}>
              <strong>{line.speaker ?? "FACTORY"}</strong>
              <p>“{line.line ?? "Persisted event available."}”</p>
              <small>{line.basis ?? "Persisted IIOS source."}</small>
            </div>
          ))}
        </div>
      </div>

      <div className="dfe-four-grid">
        <OutcomeList
          title="Best Calls"
          subtitle="9J FAVORABLE DECISIONS"
          rows={episode.best_calls ?? []}
          empty="No favorable persisted decision-quality label for this session yet."
        />
        <OutcomeList
          title="Saves"
          subtitle="NO-TRADE DOWNSIDE AVOIDED"
          rows={episode.saves ?? []}
          empty="No persisted NO_TRADE_AVOIDED_DOWNSIDE save yet."
        />
        <OutcomeList
          title="Dumb Calls"
          subtitle="ADVERSE / FOREGONE UPSIDE"
          rows={episode.dumb_calls ?? []}
          empty="No persisted adverse or foregone-upside label to put under glass."
        />
        <OutcomeList
          title="Misses"
          subtitle="9H VALIDATION"
          rows={episode.misses ?? []}
          count={missCount}
          empty={
            missCount > 0
              ? `${missCount} aggregate miss(es) reported by 9H; detailed miss records are not exposed in the current scorecard.`
              : "No persisted validation miss in the current episode."
          }
        />
      </div>

      <div className="dfe-bottom-grid">
        <article className="dfe-learning-card">
          <div className="dfe-section-heading">
            <div>
              <span>WHAT WE LEARNED</span>
              <h3>Decision-quality memory</h3>
            </div>
            <strong>{text(learned.learning_status, "WARM-UP")}</strong>
          </div>
          <div className="dfe-quality-grid">
            {Object.entries(qualityCounts).map(([label, count]) => (
              <div key={label}>
                <span>{label.replaceAll("_", " ")}</span>
                <strong>{text(count, "0")}</strong>
              </div>
            ))}
            {!Object.keys(qualityCounts).length ? (
              <p>WARM-UP — no current-session 9J quality labels.</p>
            ) : null}
          </div>
          <footer>
            9I · {text(learned.shadow_status, "WARM-UP")} ·{" "}
            {text(learned.shadow_complete_session_count, "0")} complete session(s)
          </footer>
        </article>

        <article className="dfe-focus-card">
          <div className="dfe-section-heading">
            <div>
              <span>TOMORROW'S FOCUS</span>
              <h3>Advisory only</h3>
            </div>
            <strong>HUMAN APPROVAL REQUIRED</strong>
          </div>
          <div className="dfe-focus-list">
            {(episode.tomorrow_focus ?? []).map((row, index) => (
              <div key={`${text(row.priority)}:${index}`}>
                <strong>{text(row.priority).replaceAll("_", " ")}</strong>
                <p>{text(row.why, "Persisted evidence requires review.")}</p>
                <span>
                  {text(row.action, "HUMAN_REVIEW_ONLY")} ·{" "}
                  {text(row.authority, "ADVISORY_ONLY")}
                </span>
              </div>
            ))}
          </div>
        </article>
      </div>

      <div className="dfe-safety">
        <strong>EPISODE INTEGRITY</strong>
        <span>REPORT ONLY</span>
        <span>AUTO-APPLY THRESHOLDS FALSE</span>
        <span>AGENT WEIGHT CHANGE FALSE</span>
        <span>TRADE EXECUTION FALSE</span>
        <span>LIVE CAPITAL FALSE</span>
      </div>
      {error ? (
        <div className="dfe-warning">LATEST REFRESH WARNING · {error}</div>
      ) : null}
    </section>
  );
}

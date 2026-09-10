// Pinned configuration identities; backend tests enforce exact source-registry equality.
export const deniedCapabilities = ['provider_requests', 'credential_access', 'paid_model_requests', 'paper_order',
  'broker', 'live_execution', 'operational_ledger_write', 'promotion', 'scheduler_authority', 'publisher_authority'];
export type CoverageRow = {
  id: string; name: string; component_type: string; operational_state: string; readiness: string;
  evidence_classifications: Record<string, number>; authority: Record<string, false>;
  source_cycle_id: string; generation_id: string; last_verified_at: string; freshness: string; phase: string;
  bindings: { record_id: string; source_store: string; record_type: string; payload_hash: string;
    classification: string; event_time: string | null; observation_time: string | null; publication_time: string | null }[];
  binding_count: number; binding_set_hash: string; activity_counts: { retained_records: number | null; current_invocations: null };
  last_activity: string | null; incident_state: string; limitation: string;
  [key: string]: unknown;
};
export type FactoryView = {
  schema: string; session: string; generation_id: string; source_cycle_id: string; published_at: string; phase: string;
  catalog_hash: string; content_hash: string; rooms: CoverageRow[]; agents: CoverageRow[]; governance: CoverageRow[];
  routes: CoverageRow[]; history: CoverageRow[]; subsystems: CoverageRow[]; day_trading: CoverageRow;
  permanent_production: string; limitation: string;
  universes: {capture_id:string; count:number; capture_time:string; source_classes:string[]}[];
};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const hash = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const token = (v: unknown) => typeof v === 'string' && /^[A-Za-z0-9_.:-]{1,180}$/.test(v);
const count = (v: unknown) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
const nullableCount = (v: unknown) => v === null || count(v);
const time = (v: unknown) => typeof v === 'string' && /(?:Z|\+00:00)$/.test(v) && Number.isFinite(Date.parse(v));
const classes = ['REPLAY','HISTORICAL','SIMULATED','NARRATIVE','LIVE_VERIFIED','UNAVAILABLE','STALE','FAILED_CLOSED','DELAYED','CACHED'];
const locked = (v: unknown) => object(v) && Object.keys(v).length === deniedCapabilities.length
  && deniedCapabilities.every(k => v[k] === false);
export function validFactory(value: unknown, session: string, generation: unknown, cycle: unknown, phase: string): value is FactoryView {
  if (!object(value)) return false;
  const x = value;
  if (x.schema !== 'iios-full-factory-shadow-coverage-v1' || x.session !== session || x.generation_id !== generation
    || !hash(generation) || !hash(cycle) || x.source_cycle_id !== cycle || x.phase !== phase || !time(x.published_at)
    || !hash(x.catalog_hash) || !hash(x.content_hash) || x.permanent_production !== 'YELLOW_NOT_ASSESSED_BY_SHADOW'
    || x.limitation !== 'CONFIGURATION_IDENTITIES_ARE_NOT_ACTIVITY_OR_LIVE_READINESS'
    || !Array.isArray(x.universes) || !x.universes.every(u => object(u) && hash(u.capture_id) && count(u.count)
      && time(u.capture_time) && Array.isArray(u.source_classes) && u.source_classes.every(token))
    || new Set(x.universes.map(u => u.capture_id)).size !== x.universes.length) return false;
  function row(v: unknown, id: string, name: string, type: string): v is CoverageRow {
    if (!object(v) || v.id !== id || v.name !== name || v.component_type !== type || !locked(v.authority)
      || v.source_cycle_id !== cycle || v.generation_id !== generation || v.phase !== phase || v.last_verified_at !== x.published_at
      || v.freshness !== 'CAPTURE_BOUND_NOT_MARKET_FRESHNESS' || !token(v.limitation) || v.incident_state !== 'UNKNOWN'
      || !['OBSERVATION_ONLY','SUPPRESSED','DISABLED','UNAVAILABLE'].includes(String(v.operational_state))
      || !['RETAINED_READ_ONLY','UNAVAILABLE'].includes(String(v.readiness))
      || !object(v.evidence_classifications) || !Object.entries(v.evidence_classifications).every(([k,n]) => classes.includes(k) && count(n))
      || !count(v.binding_count) || !hash(v.binding_set_hash) || !Array.isArray(v.bindings)
      || v.bindings.length !== Math.min(Number(v.binding_count),20)
      || new Set(v.bindings.map(b => object(b) ? b.record_id : null)).size !== v.bindings.length
      || !v.bindings.every(b => object(b) && hash(b.record_id) && token(b.source_store) && token(b.record_type)
        && hash(b.payload_hash) && classes.includes(String(b.classification))
        && ['event_time','observation_time','publication_time'].every(k => b[k] === null || time(b[k])))
      || !(v.last_activity === null || time(v.last_activity)) || !object(v.activity_counts)
      || v.activity_counts.current_invocations !== null
      || v.activity_counts.retained_records !== (v.binding_count === 0 ? null : v.binding_count)
      || Object.values(v.evidence_classifications).reduce<number>((a,n) => a+Number(n),0) !== v.binding_count
      || (v.readiness === 'UNAVAILABLE') !== (v.binding_count === 0)) return false;
    return true;
  }
  const groups = [ ['rooms', factoryCatalog.rooms, 'PRODUCT_ROOM'], ['agents', factoryCatalog.agents, 'SPECIALIST'],
    ['routes', factoryCatalog.routes, 'ROUTING_STATUS'], ['history', factoryCatalog.history, 'HISTORY_MEMORY'],
    ['subsystems', factoryCatalog.subsystems, 'SUBSYSTEM'], ['governance', [
      ['independent_skeptic','Independent Skeptic / Red Team'], ['committee','Investment Committee'], ['risk','Deterministic Risk Inspection']], 'GOVERNANCE'] ] as const;
  for (const [key, catalog, type] of groups) {
    const rows = x[key];
    if (!Array.isArray(rows) || rows.length !== catalog.length
      || !catalog.every(([id,name],i) => row(rows[i], id,name,type))) return false;
  }
  const rows = x.rooms as CoverageRow[];
  if (!rows.every(r => r.operational_state === 'OBSERVATION_ONLY' && nullableCount(r.candidate_count) && nullableCount(r.case_count)
    && (r.binding_count !== 0 || (r.candidate_count === null && r.case_count === null))
    && token(r.product_classification) && token(r.exposure) && token(r.benchmark)
    && r.universe_coverage === 'UNAVAILABLE_NO_ROOM_MEMBERSHIP_BINDING'
    && JSON.stringify(r.configured_evidence_routes) === JSON.stringify(['AUTHORIZED_MARKET_EVIDENCE','PRIMARY_VERIFICATION'])
    && r.evidence_availability === r.readiness)) return false;
  if (![...(x.agents as CoverageRow[]), ...(x.governance as CoverageRow[])].every(r => r.operational_state === 'SUPPRESSED'
    && typeof r.configured_role === 'string' && r.configured_role.length < 120 && nullableCount(r.completed_result_count)
    && (r.binding_count !== 0 || r.completed_result_count === null)
    && ['UNKNOWN','DISABLED'].includes(String(r.model_route_status)) && token(r.suppression_reason))) return false;
  if (!(x.routes as CoverageRow[]).every(r => r.configured === 'UNKNOWN' && r.credential_presence === 'UNKNOWN'
    && r.enabled === false && r.connection === 'NOT_ATTEMPTED_THIS_SHADOW' && r.operational_state === 'DISABLED'
    && r.request_count === 0 && r.credit_cost_count === null && r.authoritative_truth_source === false
    && Array.isArray(r.permitted_capabilities) && r.permitted_capabilities.length === 0
    && r.rate_budget_state === 'LOCKED_ZERO_ALLOWANCE' && r.activity_scope === 'THIS_DENY_ONLY_SHADOW_NOT_HOST_HISTORY'
    && r.last_verified_state === 'DENY_ONLY_POLICY_NOT_EXTERNAL_CONFIGURATION')) return false;
  const d = x.day_trading;
  if (!row(d,'day_trading','Day Trading','DAY_TRADING') || d.operational_state !== 'OBSERVATION_ONLY'
    || d.order_allowance !== 0 || d.broker_connection !== false || d.paper_authority !== false || d.live_authority !== false
    || d.kill_switch !== 'LOCKED_FAIL_CLOSED' || d.paper_scope !== 'RETAINED_L7_SNAPSHOT_NOT_LIVE_ACCOUNT' || !object(d.paper)) return false;
  return ['nav','cash'].every(k => d.paper && object(d.paper) && (d.paper[k] === null
    || (typeof d.paper[k] === 'string' && /^\d+(?:\.\d+)?$/.test(d.paper[k] as string)))) && nullableCount(d.paper.positions)
    && (d.binding_count !== 0 || Object.values(d.paper).every(v => v === null));
}
export const factoryCatalog = {
  "rooms": [
    [
      "us_large_cap_equities",
      "U.S. Large-Cap Equities"
    ],
    [
      "us_mid_cap_equities",
      "U.S. Mid-Cap Equities"
    ],
    [
      "us_small_cap_equities",
      "U.S. Small-Cap Equities"
    ],
    [
      "international_developed_equities",
      "International Developed Equities"
    ],
    [
      "emerging_market_equities",
      "Emerging-Market Equities"
    ],
    [
      "sector_thematic_etfs",
      "Sector and Thematic ETFs"
    ],
    [
      "broad_factor_etfs",
      "Broad-Market and Factor ETFs"
    ],
    [
      "treasury_bills_cash",
      "U.S. Treasury Bills and Cash Equivalents"
    ],
    [
      "treasury_notes_bonds",
      "U.S. Treasury Notes and Bonds"
    ],
    [
      "treasury_etf_duration_proxies",
      "Treasury ETFs and Duration Proxies"
    ],
    [
      "investment_grade_corporate_bonds",
      "Investment-Grade Corporate Bonds"
    ],
    [
      "high_yield_corporate_bonds",
      "High-Yield Corporate Bonds"
    ],
    [
      "municipal_bonds_etfs",
      "Municipal Bonds and Municipal ETFs"
    ],
    [
      "listed_equity_etf_options",
      "Listed Equity and ETF Options"
    ],
    [
      "index_options",
      "Index Options"
    ],
    [
      "commodity_etf_etc_proxies",
      "Commodity ETFs and ETC Proxies"
    ],
    [
      "commodity_futures_references",
      "Commodity Futures References"
    ],
    [
      "fx_spot_references",
      "Foreign-Exchange Spot References"
    ],
    [
      "currency_etfs_fx_proxies",
      "Currency ETFs and FX Proxies"
    ],
    [
      "crypto_spot_references",
      "Crypto Spot References"
    ],
    [
      "crypto_etfs_listed_proxies",
      "Crypto ETFs and Listed Proxies"
    ],
    [
      "reits_listed_real_estate",
      "REITs and Listed Real-Estate Securities"
    ],
    [
      "preferred_income_securities",
      "Preferred Stock and Income Securities"
    ],
    [
      "money_market_ultra_short",
      "Money-Market and Ultra-Short-Duration Products"
    ]
  ],
  "agents": [
    [
      "policy",
      "Policy Analyst"
    ],
    [
      "macro",
      "Macro & Rates Analyst"
    ],
    [
      "fundamentals",
      "Fundamentals Analyst"
    ],
    [
      "market_structure",
      "Market Structure Analyst"
    ],
    [
      "commodities",
      "Commodities & Supply Chain Analyst"
    ],
    [
      "geo_weather",
      "Geopolitics & Weather Analyst"
    ],
    [
      "skeptic",
      "Skeptic / Red Team"
    ],
    [
      "portfolio",
      "Portfolio Context Analyst"
    ]
  ],
  "routes": [
    [
      "bigdata",
      "Bigdata.com"
    ],
    [
      "financial_datasets",
      "Financial Datasets"
    ],
    [
      "alpha_vantage",
      "Alpha Vantage"
    ],
    [
      "alpaca_data",
      "Alpaca market data"
    ],
    [
      "alpaca_paper",
      "Alpaca paper brokerage"
    ],
    [
      "openai",
      "OpenAI"
    ],
    [
      "gemini",
      "Gemini"
    ],
    [
      "grok",
      "Grok"
    ],
    [
      "mcp",
      "MCP tool routing"
    ],
    [
      "vercel",
      "Vercel presentation/deployment"
    ]
  ],
  "subsystems": [
    [
      "9A",
      "Cadence / orchestration"
    ],
    [
      "9B",
      "Governed research"
    ],
    [
      "9E",
      "High-speed market radar"
    ],
    [
      "9G",
      "Telemetry / Factory Watch"
    ],
    [
      "9H",
      "Independent validation"
    ],
    [
      "9I",
      "Counterfactual / shadow research"
    ],
    [
      "9J",
      "Outcomes / judgment"
    ]
  ],
  "history": [
    [
      "l7",
      "L7 paper-account history"
    ],
    [
      "l8",
      "L8 historical cases"
    ],
    [
      "agent_results",
      "Agent results"
    ],
    [
      "committee_decisions",
      "Committee decisions"
    ],
    [
      "opportunities",
      "Opportunity candidates"
    ],
    [
      "pattern_reviews",
      "Historical-pattern reviews"
    ],
    [
      "measurements_9h",
      "9H measurements"
    ],
    [
      "counterfactual_9i",
      "9I counterfactual research"
    ],
    [
      "outcomes_9j",
      "9J outcomes / judgment review"
    ],
    [
      "pattern_library",
      "Pattern Library"
    ],
    [
      "jesse_bank",
      "Jesse Judgment Bank"
    ],
    [
      "price_archive",
      "Price archive"
    ],
    [
      "event_archive",
      "Event reconstruction"
    ],
    [
      "macro_archive",
      "Macro archives"
    ]
  ]
} as const;

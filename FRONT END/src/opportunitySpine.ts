// Read-only source contract. No fetch, activation, UI/artwork changes or legacy fallback.
export const opportunityFlags = ['broker_connected', 'paper_order_permission', 'trade_execution_permission',
  'live_execution', 'ledger_write_authority'] as const;
const stageNames = ['ALPHA_VANTAGE', 'YAHOO', 'FINANCIAL_DATASETS', 'BIGDATA', 'MASSIVE', 'ALPACA',
  'policy', 'macro', 'fundamentals', 'market_structure', 'commodities', 'geo_weather', 'skeptic', 'portfolio',
  'OpenAI', 'Grok', 'Gemini', 'committee', 'risk'];
const modelNames = stageNames.slice(6, 17);
const statuses = ['REQUIRED', 'OPTIONAL', 'NOT_RUN', 'PASS', 'FAILED', 'BLOCKED', 'UNAVAILABLE'];
type Stage = { status: string; decision: string | null };
export type OpportunityView = {
  schema: string; source_commit: string; scope: string; session_parent: string;
  backend_identity: string; frontend_identity: string; scanner_mode: string; status: string;
  authority: Record<string, false>; alpha_status: string; scan_count: number; case_count: number;
  case_decisions: string[]; yahoo_states: string[]; provider_stages: Record<string, Stage>[];
  model_disagreement: Record<string, Stage>[]; signals_detected: number; candidate_count: number;
  freshness: string; armed: false;
};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, expected: readonly string[]) =>
  Object.keys(v).sort().join('|') === [...expected].sort().join('|');
const hash = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const count = (v: unknown, max: number) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= max;
export function canonicalOpportunity(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalOpportunity).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonicalOpportunity(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}
export async function opportunityHash(value: unknown): Promise<string> {
  const text = canonicalOpportunity(value).replace(/[\u007f-\uffff]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
  const bytes = new TextEncoder().encode(text + '\n');
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
}
function stages(v: unknown, names: string[]): boolean {
  return object(v) && keys(v, names) && Object.values(v).every(s => object(s) && keys(s, ['status', 'decision']) &&
    typeof s.status === 'string' && statuses.includes(s.status) &&
    (s.decision === null || typeof s.decision === 'string' && ['WATCH', 'NO_TRADE', 'APPROVE', 'VETO', 'ALLOW'].includes(s.decision)));
}
export async function admitOpportunity(value: unknown, expected: {
  projection: string; source: string; session: string; backend: string; frontend: string;
}): Promise<OpportunityView> {
  if (!object(value) || !keys(value, ['schema', 'source_commit', 'scope', 'session_parent', 'backend_identity',
    'frontend_identity', 'scanner_mode', 'status', 'authority', 'alpha_status', 'scan_count', 'case_count',
    'case_decisions', 'yahoo_states', 'provider_stages', 'model_disagreement', 'signals_detected', 'candidate_count', 'freshness', 'armed']))
    throw Error('OPPORTUNITY_SCHEMA');
  if (![expected.projection, expected.session, expected.backend, expected.frontend].every(hash) ||
    !/^[a-f0-9]{40}$/.test(expected.source) || value.source_commit !== expected.source || value.session_parent !== expected.session ||
    value.backend_identity !== expected.backend || value.frontend_identity !== expected.frontend ||
    await opportunityHash(value) !== expected.projection) throw Error('OPPORTUNITY_IDENTITY');
  if (value.schema !== 'iios-opportunity-northstar-v1' || value.scope !== 'OFFLINE_TEST' || value.armed !== false ||
    !object(value.authority) || !keys(value.authority, opportunityFlags) || Object.values(value.authority).some(x => x !== false))
    throw Error('OPPORTUNITY_AUTHORITY');
  const maximum = value.scanner_mode === 'BASELINE_ONLY' ? 3 : value.scanner_mode === 'FULL_OPPORTUNITY_RADAR' ? 79 : 0;
  if (!maximum || !['GREEN', 'YELLOW', 'RED'].includes(String(value.status)) || !['PASS', 'FAILED'].includes(String(value.alpha_status)) ||
    !count(value.scan_count, maximum) || !count(value.case_count, maximum * 2) || !count(value.candidate_count, maximum * 5) ||
    !count(value.signals_detected, maximum * 517) || !['WITHIN_AGE_BOUND', 'UNVERIFIED'].includes(String(value.freshness)))
    throw Error('OPPORTUNITY_COUNTS');
  if (!Array.isArray(value.case_decisions) || value.case_decisions.length !== value.case_count ||
    !value.case_decisions.every(x => ['WATCH', 'NO_TRADE', 'EVIDENCE_BLOCK', 'PAPER_REVIEW_ONLY'].includes(x)) ||
    !Array.isArray(value.yahoo_states) || value.yahoo_states.length !== value.scan_count ||
    !value.yahoo_states.every(x => ['PASS', 'FAILED', 'UNAVAILABLE'].includes(x)) ||
    !Array.isArray(value.provider_stages) || value.provider_stages.length !== value.case_count ||
    !value.provider_stages.every(x => stages(x, stageNames)) ||
    !Array.isArray(value.model_disagreement) || value.model_disagreement.length !== value.case_count ||
    !value.model_disagreement.every(x => stages(x, modelNames))) throw Error('OPPORTUNITY_STAGE');
  if (value.status === 'GREEN' && (value.alpha_status !== 'PASS' || value.scan_count !== maximum ||
    value.freshness !== 'WITHIN_AGE_BOUND' || value.yahoo_states.some(x => x !== 'PASS') || value.case_decisions.includes('EVIDENCE_BLOCK')))
    throw Error('OPPORTUNITY_FALSE_GREEN');
  return structuredClone(value) as OpportunityView;
}

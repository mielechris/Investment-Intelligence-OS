// Explicit offline unit fixture. Never imported by a production module.
import { factoryCatalog, deniedCapabilities } from './truthSpineFactoryView.ts';
import type { CoverageRow, FactoryView } from './truthSpineFactoryView.ts';
export function factoryFixture(phase = 'OPENING_OBSERVATION'): FactoryView {
  const row = (id: string, name: string, type: string): CoverageRow => ({ id,name,component_type:type,
    operational_state:'UNAVAILABLE',readiness:'UNAVAILABLE',evidence_classifications:{},
    authority:Object.fromEntries(deniedCapabilities.map(k => [k,false as const])),source_cycle_id:'d'.repeat(64),
    generation_id:'a'.repeat(64),last_verified_at:'2026-09-10T13:30:00.000Z',freshness:'CAPTURE_BOUND_NOT_MARKET_FRESHNESS',phase,
    bindings:[],binding_count:0,binding_set_hash:'b'.repeat(64),activity_counts:{retained_records:null,current_invocations:null},
    last_activity:null,incident_state:'UNKNOWN',limitation:'NO_INDIVIDUALLY_BOUND_GOVERNED_RECORD' });
  return { schema:'iios-full-factory-shadow-coverage-v1',session:'unit-session',generation_id:'a'.repeat(64),
    source_cycle_id:'d'.repeat(64),published_at:'2026-09-10T13:30:00.000Z',phase,catalog_hash:'b'.repeat(64),content_hash:'c'.repeat(64),
    universes:[517,518].map((count,i) => ({capture_id:String(i).repeat(64),count,capture_time:'2026-09-09T20:00:00Z',source_classes:['HISTORICAL']})),
    permanent_production:'YELLOW_NOT_ASSESSED_BY_SHADOW',limitation:'CONFIGURATION_IDENTITIES_ARE_NOT_ACTIVITY_OR_LIVE_READINESS',
    rooms:factoryCatalog.rooms.map(([id,name]) => ({...row(id,name,'PRODUCT_ROOM'),operational_state:'OBSERVATION_ONLY',
      product_classification:'EQUITY_ETF',exposure:'DIRECT',benchmark:'SP500',universe_coverage:'UNAVAILABLE_NO_ROOM_MEMBERSHIP_BINDING',
      configured_evidence_routes:['AUTHORIZED_MARKET_EVIDENCE','PRIMARY_VERIFICATION'],evidence_availability:'UNAVAILABLE',candidate_count:null,case_count:null})),
    agents:factoryCatalog.agents.map(([id,name]) => ({...row(id,name,'SPECIALIST'),operational_state:'SUPPRESSED',configured_role:name,
      completed_result_count:null,model_route_status:'UNKNOWN',suppression_reason:'DENY_ONLY_SHADOW_NO_MODEL_INVOCATION'})),
    governance:[['independent_skeptic','Independent Skeptic / Red Team'],['committee','Investment Committee'],['risk','Deterministic Risk Inspection']].map(([id,name]) => ({
      ...row(id,name,'GOVERNANCE'),operational_state:'SUPPRESSED',configured_role:name,completed_result_count:null,model_route_status:'DISABLED',suppression_reason:'READ_ONLY_NO_NEW_DECISIONS'})),
    routes:factoryCatalog.routes.map(([id,name]) => ({...row(id,name,'ROUTING_STATUS'),configured:'UNKNOWN',credential_presence:'UNKNOWN',enabled:false,
      connection:'NOT_ATTEMPTED_THIS_SHADOW',operational_state:'DISABLED',permitted_capabilities:[],request_count:0,credit_cost_count:null,
      authoritative_truth_source:false,rate_budget_state:'LOCKED_ZERO_ALLOWANCE',activity_scope:'THIS_DENY_ONLY_SHADOW_NOT_HOST_HISTORY',
      last_verified_state:'DENY_ONLY_POLICY_NOT_EXTERNAL_CONFIGURATION'})),
    history:factoryCatalog.history.map(([id,name]) => row(id,name,'HISTORY_MEMORY')),
    subsystems:factoryCatalog.subsystems.map(([id,name]) => row(id,name,'SUBSYSTEM')),
    day_trading:{...row('day_trading','Day Trading','DAY_TRADING'),operational_state:'OBSERVATION_ONLY',order_allowance:0,broker_connection:false,
      paper_authority:false,live_authority:false,kill_switch:'LOCKED_FAIL_CLOSED',paper_scope:'RETAINED_L7_SNAPSHOT_NOT_LIVE_ACCOUNT',paper:{nav:null,cash:null,positions:null}} };
}

"""Source-only joins into governed factory stages; no models, ledgers or orders."""
from copy import deepcopy

from alpha_market_baseline import require
from opportunity_spine_contract import receipt, verify, STATES, authority
from provider_gateway_contract import content_hash

AGENTS = ('policy', 'macro', 'fundamentals', 'market_structure', 'commodities',
          'geo_weather', 'skeptic', 'portfolio')
MODELS = ('OpenAI', 'Grok', 'Gemini')
PROVIDERS = ('ALPHA_VANTAGE', 'YAHOO', 'FINANCIAL_DATASETS', 'BIGDATA', 'MASSIVE', 'ALPACA')
REQUIREMENTS = {'ALPHA_VANTAGE': 'REQUIRED', 'YAHOO': 'OPTIONAL',
                'FINANCIAL_DATASETS': 'REQUIRED', 'BIGDATA': 'REQUIRED',
                'MASSIVE': 'OPTIONAL', 'ALPACA': 'OPTIONAL'}
PURPOSES = {'ALPHA_VANTAGE': 'QUANTITATIVE_BASELINE_AND_SPECIALIST', 'YAHOO': 'INDEPENDENT_DISCOVERY',
            'FINANCIAL_DATASETS': 'CORPORATE_EVIDENCE', 'BIGDATA': 'CATALYST_EARNINGS_VALUATION_RISK',
            'MASSIVE': 'BASIC_HISTORICAL_END_OF_DAY_REFERENCE', 'ALPACA': 'QUALIFIED_READ_ONLY_TAPE'}


def routing(candidate, expected, *, parents, candidate_id, source):
    data = verify(candidate, expected, kind='candidates', parents=parents, source=source)
    chosen = [r for r in data['rows'] if r['candidate_id'] == candidate_id and r['case_selected'] is True]
    require(len(chosen) == 1, 'CASE_NOT_SELECTED')
    case = content_hash([expected, candidate_id])
    return receipt('routing', {'case_id': case, 'candidate_id': candidate_id, 'symbol': chosen[0]['symbol'],
                   'policy': 'opportunity-routing-v1', 'stages': {
                       p: {'requirement': REQUIREMENTS[p], 'status': 'NOT_RUN', 'purpose': PURPOSES[p],
                           'maximum_proposed_requests': 1, 'cost': None,
                           'qualification_required': True, 'retention_policy_required': p == 'BIGDATA'} for p in PROVIDERS}},
                   {'candidates': expected}, source=source)


def adjudicate(route, route_hash, *, route_parents, stages, expected, source):
    """Stage receipt admission, not a substitute for the existing evidence owners.

    Caller supplies independent accepted hashes. Every stage binds the exact case,
    requirement plan and all previous stage hashes. Missing stages remain NOT_RUN.
    Deterministic Risk has veto precedence over every model and Committee conclusion.
    """
    plan = verify(route, route_hash, kind='routing', parents=route_parents, source=source)
    require(plan['policy'] == 'opportunity-routing-v1' and set(plan['stages']) == set(PROVIDERS), 'ROUTING_POLICY')
    require(all(plan['stages'][p]['requirement'] == REQUIREMENTS[p] and plan['stages'][p]['status'] == 'NOT_RUN'
                for p in PROVIDERS), 'ROUTING_SUBSTITUTION')
    order = list(PROVIDERS)+list(AGENTS)+list(MODELS)+['committee', 'risk']
    require(set(stages) == set(expected) and set(stages) <= set(order), 'STAGE_SET')
    parents = {'routing': route_hash}
    outputs, retained = {}, {}
    blocked = False
    for name in order:
        if name not in stages:
            outputs[name] = {'status': 'NOT_RUN', 'decision': None}
            continue
        d = verify(stages[name], expected[name], kind=name, parents=parents, source=source)
        require(set(d) == {'case_id', 'status', 'decision', 'evidence_admitted', 'deterministic'}, 'STAGE_SCHEMA')
        require(d['case_id'] == plan['case_id'] and d['status'] in STATES, 'CASE_STAGE')
        require(d['decision'] in (None, 'WATCH', 'NO_TRADE', 'APPROVE', 'VETO', 'ALLOW'), 'DECISION_ENUM')
        require(type(d['evidence_admitted']) is bool and type(d['deterministic']) is bool, 'STAGE_BOOLEAN')
        if name in PROVIDERS and d['status'] == 'PASS':
            require(d['evidence_admitted'] is True, 'PROVIDER_NOT_ADMITTED')
        if name not in PROVIDERS:
            require(d['evidence_admitted'] is False, 'MODEL_CANNOT_ESTABLISH_EVIDENCE_TRUTH')
        if name == 'risk':
            require(d['deterministic'] is True and d['decision'] in ('VETO', 'ALLOW', None), 'DETERMINISTIC_RISK_REQUIRED')
        outputs[name] = {'status': d['status'], 'decision': d['decision']}
        retained[name] = deepcopy(stages[name])
        parents[name] = expected[name]
    blocked = any(outputs[p]['status'] != 'PASS' for p in PROVIDERS if REQUIREMENTS[p] == 'REQUIRED')
    agents_complete = all(outputs[a]['status'] == 'PASS' for a in AGENTS)
    committee = outputs['committee']; risk = outputs['risk']
    if blocked:
        decision = 'EVIDENCE_BLOCK'
    elif not agents_complete or committee['status'] != 'PASS':
        decision = 'WATCH'
    elif risk['status'] == 'PASS' and risk['decision'] == 'VETO':
        decision = 'NO_TRADE'
    elif committee['decision'] in ('WATCH', 'NO_TRADE'):
        decision = committee['decision']
    elif risk['status'] != 'PASS' or risk['decision'] != 'ALLOW':
        decision = 'NO_TRADE'
    else:
        decision = 'PAPER_REVIEW_ONLY'
    disagreements = {k: v for k, v in outputs.items() if k in AGENTS+MODELS}
    return receipt('case', {'case_id': plan['case_id'], 'symbol': plan['symbol'], 'routing': deepcopy(route),
                   'stages': outputs, 'stage_receipts': retained, 'disagreement': disagreements,
                   'decision': decision, 'evidence_block': blocked, 'risk_veto': risk['decision'] == 'VETO',
                   'outcome_eligible': not blocked and agents_complete and committee['status'] == 'PASS' and risk['status'] == 'PASS',
                   'decision_only_no_order': True}, parents, source=source)


def capacity(plan, *, yahoo_recorded_requests, enrichment_requests_per_case=6):
    require(yahoo_recorded_requests is None or type(yahoo_recorded_requests) is int and yahoo_recorded_requests >= 0,
            'YAHOO_RECORDED_USAGE')
    require(enrichment_requests_per_case == 6, 'ROUTING_CAPACITY_PIN')
    scans = len(plan['scans'])
    return {'scans': scans, 'symbols_per_scan': 517, 'batch_sizes': [100]*5+[17],
            'alpha_per_scan': 6, 'alpha_collection_requests': scans*6, 'alpha_preflight': 1,
            'alpha_proposed_total': scans*6+1, 'alpha_credential_access_upper_bound': scans*6+1,
            'alpha_maximum_response_bytes': 1_000_000, 'alpha_timeout_seconds': 20,
            'alpha_response_byte_upper_bound': (scans*6+1)*1_000_000,
            'maximum_starts_per_rolling_minute': 3, 'documented_account_rate_ceiling': 150,
            'yahoo_recorded_requests': yahoo_recorded_requests, 'additional_yahoo_requests': 0,
            'max_promotions_per_scan': 5, 'max_cases_per_scan': 2,
            'max_promotions_session_upper_bound': scans*5, 'max_cases_session_upper_bound': scans*2,
            'duplicate_cooldown_hours': 12, 'enrichment_proposed_requests_per_case': 6,
            'enrichment_proposed_session_upper_bound': scans*2*6,
            'model_calls_proposed_per_case': 12, 'model_calls_session_upper_bound': scans*2*12,
            'model_plan': {'eight_agents_including_skeptic': 8, 'committee': 1,
                           'OpenAI_coordination': 1, 'Grok_challenger': 1, 'Gemini_challenger': 1, 'risk': 0},
            'enrichment_credential_access_upper_bound_per_case': 7,
            'monetary_cost': None, 'usage_unit_cost': None, 'allowance_released': False,
            'ambiguous_consumption': 'RESERVATION_RETAINED_NO_RETRY', 'authority': authority()}


def scan_receipt(signals, signals_hash, candidates, candidates_hash, yahoo, *,
                 signal_parents, candidate_parents, schedule_hash, source):
    s = verify(signals, signals_hash, kind='signals', parents=signal_parents, source=source)
    c = verify(candidates, candidates_hash, kind='candidates', parents=candidate_parents, source=source)
    require(signal_parents['schedule'] == schedule_hash and candidate_parents['signals'] == signals_hash,
            'SCAN_SIGNAL_CANDIDATE_PARENTS')
    require(s['scan'] == c['scan'] and len(s['rows']) == 517 and
            len({r['symbol'] for r in s['rows']}) == 517, 'SCAN_COVERAGE')
    require(all(r['freshness'] == 'WITHIN_AGE_BOUND' for r in s['rows']), 'SCAN_FRESHNESS')
    require(len(c['rows']) <= 5 and sum(r['case_selected'] for r in c['rows']) <= 2, 'SCAN_LIMITS')
    require(set(r['symbol'] for r in c['rows']) <= set(r['symbol'] for r in s['rows']), 'CANDIDATE_COVERAGE')
    from opportunity_spine_signals import compare_yahoo
    reconciled = compare_yahoo([r['symbol'] for r in s['rows'] if r['detected']], yahoo['receipt'], yahoo['parent'],
                               scan=s['scan'], scan_parent=signals_hash, source=source)
    require(yahoo == reconciled, 'YAHOO_COMPARISON_SUBSTITUTION')
    return receipt('scan', {'scan': s['scan'], 'alpha_status': 'PASS', 'yahoo_status': yahoo['status'],
                   'signal_parent': signals_hash, 'candidate_parent': candidates_hash,
                   'signals': deepcopy(signals), 'candidates': deepcopy(candidates), 'yahoo': deepcopy(yahoo)},
                   {'schedule': schedule_hash}, source=source)


def final_session(collection, collection_hash, *, schedule_hash, scans, scan_hashes, cases, case_hashes,
                  source, backend_identity, frontend_identity):
    """Join complete retained sanitized receipts, never merely dangling stage hashes."""
    collected = verify(collection, collection_hash, kind='collection', parents={'schedule': schedule_hash}, source=source)
    require(set(scans) == set(scan_hashes) and set(cases) == set(case_hashes), 'FINAL_SET')
    import re
    require(all(re.fullmatch('[0-9a-f]{64}', h) for h in (backend_identity, frontend_identity)), 'PROJECTION_IDENTITY')
    failed = collected['status'] != 'PASS'
    warnings = []
    for key, doc in scans.items():
        d = verify(doc, scan_hashes[key], kind='scan', parents={'schedule': schedule_hash}, source=source)
        require(str(d['scan']) == key, 'SCAN_IDENTITY')
        require(set(d) == {'scan', 'alpha_status', 'yahoo_status', 'signal_parent', 'candidate_parent', 'signals', 'candidates', 'yahoo'}, 'SCAN_SUMMARY_SCHEMA')
        rebuilt = scan_receipt(d['signals'], d['signal_parent'], d['candidates'], d['candidate_parent'], d['yahoo'],
                               signal_parents=d['signals']['parents'], candidate_parents=d['candidates']['parents'],
                               schedule_hash=schedule_hash, source=source)
        require(rebuilt == doc, 'SCAN_RECONSTRUCTION')
        failed |= d['alpha_status'] != 'PASS'
        if d['yahoo_status'] != 'PASS':
            warnings.append('YAHOO_'+key+'_UNAVAILABLE')
    count = 79 if collected['mode'] == 'FULL_OPPORTUNITY_RADAR' else 3
    if set(scans) != {str(i) for i in range(count)}:
        failed = True
    selected = {r['candidate_id'] for scan in scans.values() for r in scan['data']['candidates']['data']['rows'] if r['case_selected']}
    candidate_parents = {r['candidate_id']: scan['data']['candidate_parent'] for scan in scans.values()
                         for r in scan['data']['candidates']['data']['rows'] if r['case_selected']}
    represented = set()
    for key, doc in cases.items():
        d = verify(doc, case_hashes[key], kind='case', parents=doc['parents'], source=source)
        require(d['case_id'] == key, 'CASE_IDENTITY')
        route = d['routing']
        candidate_id = route['data']['candidate_id']
        require(candidate_id in selected and candidate_id not in represented, 'CASE_CANDIDATE_BINDING')
        require(route['parents'] == {'candidates': candidate_parents[candidate_id]}, 'ROUTING_CANDIDATE_PARENT')
        represented.add(candidate_id)
        rebuilt = adjudicate(route, content_hash(route), route_parents=route['parents'],
                             stages=d['stage_receipts'], expected={k:content_hash(v) for k,v in d['stage_receipts'].items()}, source=source)
        require(rebuilt == doc, 'CASE_RECONSTRUCTION')
        if d['evidence_block']:
            warnings.append('CASE_EVIDENCE_BLOCK')
    if selected != represented:
        warnings.append('SELECTED_CASE_NOT_RUN')
    status = 'RED' if failed else 'YELLOW' if warnings else 'GREEN'
    data = {'mode': collected['mode'], 'status': status, 'classification_scope': 'OFFLINE_FACTORY_CONTRACT',
            'collection': deepcopy(collection), 'scan_receipts': deepcopy(scans), 'case_receipts': deepcopy(cases),
            'warnings': warnings, 'runtime_readiness': 'UNQUALIFIED', 'operational_readiness': 'UNARMED',
            'backend_identity': backend_identity, 'frontend_identity': frontend_identity}
    return receipt('session', data, {'collection': collection_hash, 'schedule': schedule_hash,
                   **{'scan:'+k: h for k, h in scan_hashes.items()},
                   **{'case:'+k: h for k, h in case_hashes.items()}}, source=source)


def projection(session, expected, *, parents, source, backend_identity, frontend_identity):
    data = verify(session, expected, kind='session', parents=parents, source=source)
    require(data['backend_identity'] == backend_identity and data['frontend_identity'] == frontend_identity, 'BACKEND_FRONTEND_IDENTITY')
    return {'schema': 'iios-opportunity-northstar-v1', 'source_commit': source, 'scope': 'OFFLINE_TEST',
            'session_parent': expected, 'backend_identity': backend_identity, 'frontend_identity': frontend_identity,
            'scanner_mode': data['mode'], 'status': data['status'], 'authority': authority(),
            'alpha_status': data['collection']['data']['status'],
            'scan_count': len(data['scan_receipts']), 'case_count': len(data['case_receipts']),
            'case_decisions': [d['data']['decision'] for d in data['case_receipts'].values()],
            'yahoo_states': [d['data']['yahoo_status'] for d in data['scan_receipts'].values()],
            'provider_stages': [d['data']['stages'] for d in data['case_receipts'].values()],
            'model_disagreement': [d['data']['disagreement'] for d in data['case_receipts'].values()],
            'signals_detected': sum(sum(r['detected'] for r in d['data']['signals']['data']['rows']) for d in data['scan_receipts'].values()),
            'candidate_count': sum(len(d['data']['candidates']['data']['rows']) for d in data['scan_receipts'].values()),
            'freshness': 'WITHIN_AGE_BOUND' if data['collection']['data']['status'] == 'PASS' else 'UNVERIFIED',
            'armed': False}

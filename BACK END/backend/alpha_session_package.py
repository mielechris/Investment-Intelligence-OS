"""Offline package bindings; no filesystem, credentials, budget release or execution.

Documents here are planning evidence references. Independently pinned hashes
prove identity, not the truth of entitlement claims or actual runtime files.
"""
import re
from decimal import localcontext

from alpha_session_contract import instant, require
from alpha_session_integration import SCOPE, verify_session_plan
from deployment_contract import PYTHON_VERSION
from provider_gateway_contract import content_hash, locked_authority, pin, safe_document
from provider_gateway_live_contract import CLAIMS, amount

SCHEMA = 'iios-alpha-bound-package-candidate-v1'
COMMON = {'schema', 'scope', 'source_commit', 'session', 'plan_parent', 'valid_from', 'expires_at'}
ACCOUNT = {'account_identity', 'tier_identity', 'provider', 'endpoint', 'feed', 'symbols',
           'claim_parents', 'cost_unit', 'maximum_request_cost', 'available_unreserved',
           'rate_per_minute', 'overage_enabled', 'automatic_top_up', 'ambiguous_billing'}
RUNTIME = {'runtime_manifest_sha256', 'interpreter_sha256', 'platform_manifest_sha256',
           'python_version', 'system', 'architecture'}
ALLOWANCE = {'account_parent', 'runtime_parent', 'account_identity', 'cost_unit',
             'maximum_requests', 'maximum_cost', 'enrichment_requests', 'released'}


def sha(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def label(value):
    return type(value) is str and re.fullmatch('[A-Za-z0-9_.:-]{1,80}', value) is not None


def money(value):
    require(type(value) is str and len(value) <= 24, 'PACKAGE_AMOUNT')
    return amount(value)


def bound_package(plan, account, runtime, allowance, *, input_pins, contract, calendar,
                  universe, spine_session, expected, now, source_commit, observation=None):
    require(type(input_pins) is dict and set(input_pins) == {'plan', 'account', 'runtime', 'allowance'},
            'PACKAGE_PINS')
    plan = verify_session_plan(plan, input_pins['plan'], contract, calendar, universe, spine_session,
                               expected=expected, now=now, source_commit=source_commit, observation=observation)
    from alpha_short_observation import PLAN_SCHEMA as SHORT_SCHEMA, PACKAGE_SCHEMA as SHORT_PACKAGE
    # Version discrimination precedes budget arithmetic. Never infer a mode from a count.
    short = plan['schema'] == SHORT_SCHEMA
    maximum_requests = 3 if short else 475
    for name, document, fields in (('account', account, ACCOUNT), ('runtime', runtime, RUNTIME),
                                    ('allowance', allowance, ALLOWANCE)):
        safe_document(document)
        pin(document, input_pins[name])
        require(type(document) is dict and set(document) == COMMON | fields, 'PACKAGE_DOCUMENT_SCHEMA')
        require(document['schema'] == f'iios-alpha-{name}-candidate-v1' and
                document['scope'] == SCOPE, 'PACKAGE_DOCUMENT_SCOPE')
        require(document['source_commit'] == source_commit and document['session'] == plan['session'] and
                document['plan_parent'] == input_pins['plan'], 'PACKAGE_DOCUMENT_BINDING')
        start, end = instant(document['valid_from']), instant(document['expires_at'])
        require(start <= now < end and start <= instant(plan['rows'][0]['valid_from']) and
                end >= instant(plan['finalization_deadline']), 'PACKAGE_DOCUMENT_WINDOW')

    require(label(account['account_identity']) and label(account['tier_identity']), 'PACKAGE_ACCOUNT_IDENTITY')
    require(account['provider'] == 'ALPHA_VANTAGE' and account['endpoint'] == 'REALTIME_BULK_QUOTES' and
            account['feed'] == 'real_time', 'PACKAGE_ACCOUNT_ROUTE')
    required_symbols = list(dict.fromkeys(s for row in plan['rows'] for s in row['symbols']))
    require(type(account['symbols']) is list and account['symbols'] == required_symbols, 'PACKAGE_ACCOUNT_SYMBOLS')
    claims = account['claim_parents']
    require(type(claims) is dict and set(claims) == set(CLAIMS) and all(sha(p) for p in claims.values()),
            'PACKAGE_ACCOUNT_CLAIMS')
    require(label(account['cost_unit']), 'PACKAGE_COST_UNIT')
    require(type(account['rate_per_minute']) is int and
            account['rate_per_minute'] >= plan['maximum_starts_per_rolling_minute'], 'PACKAGE_ACCOUNT_RATE')
    require(account['overage_enabled'] is False and account['automatic_top_up'] is False and
            account['ambiguous_billing'] == 'RESERVE_MAXIMUM_NO_RETRY', 'PACKAGE_BILLING_POLICY')

    require(all(sha(runtime[key]) for key in ('runtime_manifest_sha256', 'interpreter_sha256',
                                             'platform_manifest_sha256')), 'PACKAGE_RUNTIME_PINS')
    require(runtime['python_version'] == PYTHON_VERSION and runtime['system'] == 'Darwin' and
            runtime['architecture'] == 'arm64', 'PACKAGE_RUNTIME_TARGET')
    require(allowance['account_parent'] == input_pins['account'] and
            allowance['runtime_parent'] == input_pins['runtime'] and
            allowance['account_identity'] == account['account_identity'], 'PACKAGE_ALLOWANCE_PARENTS')
    require(type(allowance['maximum_requests']) is int and allowance['maximum_requests'] == maximum_requests and
            type(allowance['enrichment_requests']) is int and allowance['enrichment_requests'] == 0,
            'PACKAGE_ALLOWANCE_COUNT')
    require(allowance['released'] is False and allowance['cost_unit'] == account['cost_unit'],
            'PACKAGE_ALLOWANCE_UNRELEASED')
    # Precision is bounded independently of a caller's Decimal context.
    with localcontext() as ctx:
        ctx.prec = 64
        total = maximum_requests * money(account['maximum_request_cost'])
        require(money(allowance['maximum_cost']) == total <= money(account['available_unreserved']),
                'PACKAGE_ALLOWANCE_COST')
    return {'schema': SHORT_PACKAGE if short else SCHEMA, 'scope': SCOPE, 'source_commit': source_commit, 'session': plan['session'],
            'parents': dict(input_pins), 'session_parents': dict(expected),
            'maximum_requests': maximum_requests, 'maximum_cost': allowance['maximum_cost'],
            'cost_unit': allowance['cost_unit'], 'status': 'BINDINGS_VALID_ONLY',
            'qualification_authorized': False, 'execution_authorized': False,
            'production_qualified': False, 'allowance_released': False, 'authority': locked_authority(),
            'pending': ['REAL_ACCOUNT_EVIDENCE', 'RUNTIME_FILES_AND_PLATFORM', 'OS_CONFINEMENT',
                        'LIVE_PREFLIGHT', 'PRODUCTION_ADAPTER', 'INSTALLATION_AND_EXECUTION_AUTHORITY']}


def verify_bound_package(candidate, candidate_hash, *args, **kwargs):
    safe_document(candidate)
    pin(candidate, candidate_hash)
    rebuilt = bound_package(*args, **kwargs)
    require(content_hash(candidate) == content_hash(rebuilt), 'PACKAGE_SUBSTITUTION')
    return rebuilt

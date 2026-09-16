"""Explicit billing arithmetic for reviewed observation candidates, never release.

Evidence hashes establish identity, not truth. Independent semantic account
review must supply these documents; public pricing cannot populate them.
"""
from decimal import localcontext

from alpha_session_contract import instant, require
from alpha_session_package import money, sha, label
from provider_gateway_contract import content_hash, pin, safe_document, locked_authority

SCHEMA = 'iios-alpha-observation-billing-v1'
MODELS = ('PREPAID_UNITS', 'METERED_CURRENCY', 'FLAT_SUBSCRIPTION')


def review_billing(document, expected, *, plan, plan_hash, account_identity,
                   evidence_parents, now):
    safe_document(document); pin(document, expected); pin(plan, plan_hash)
    from alpha_short_observation import PLAN_SCHEMA
    require(plan['schema'] == PLAN_SCHEMA and len(plan['rows']) == 3, 'BILLING_SHORT_PLAN')
    require(set(document) == {'schema', 'scope', 'source_commit', 'plan_parent', 'account_identity',
        'valid_from', 'expires_at', 'model', 'evidence_parents', 'currency', 'maximum_request_charge',
        'spending_cap', 'spending_headroom', 'request_cap', 'available_requests', 'quota_unlimited',
        'unit_name', 'units_per_request', 'available_units', 'overage_enabled', 'automatic_top_up',
        'ambiguous_policy', 'zero_incremental_charge_proven', 'authority'}, 'BILLING_SCHEMA')
    require(document['schema'] == SCHEMA and document['scope'] == 'OFFLINE_INTEGRATION_ONLY' and
            document['source_commit'] == plan['source_commit'] and document['plan_parent'] == plan_hash and
            label(account_identity) and document['account_identity'] == account_identity, 'BILLING_BINDING')
    require(instant(document['valid_from']) <= now < instant(document['expires_at']) and
            instant(document['valid_from']) <= instant(plan['startup_not_before']) and
            instant(document['expires_at']) >= instant(plan['finalization_deadline']), 'BILLING_VALIDITY')
    require(type(evidence_parents) is dict and set(evidence_parents) == {'cost', 'billing', 'rate'} and
            all(sha(v) for v in evidence_parents.values()) and
            document['evidence_parents'] == evidence_parents, 'BILLING_EVIDENCE')
    require(document['model'] in MODELS and document['currency'] in ('USD',), 'BILLING_MODEL')
    require(document['overage_enabled'] is False and document['automatic_top_up'] is False and
            document['ambiguous_policy'] == 'RESERVE_MAXIMUM_NO_RETRY', 'BILLING_POLICY')
    require(type(document['authority']) is dict and set(document['authority']) == set(locked_authority()) and
            all(v is False for v in document['authority'].values()), 'BILLING_AUTHORITY')
    require(type(document['request_cap']) is int and document['request_cap'] == 3 and
            type(document['quota_unlimited']) is bool, 'BILLING_REQUEST_CAP')
    if document['quota_unlimited']:
        require(document['available_requests'] is None, 'BILLING_QUOTA_AMBIGUITY')
    else:
        require(type(document['available_requests']) is int and
                3 <= document['available_requests'] <= 10**9, 'BILLING_REQUEST_HEADROOM')
    with localcontext() as ctx:
        ctx.prec = 64
        charge = money(document['maximum_request_charge'])
        cap = money(document['spending_cap']); headroom = money(document['spending_headroom'])
        require(type(document['zero_incremental_charge_proven']) is bool and
                (charge != 0 or document['zero_incremental_charge_proven'] is True), 'BILLING_ZERO_UNPROVEN')
        require(charge * 3 <= cap <= headroom, 'BILLING_SPENDING_CAP')
        if document['model'] == 'PREPAID_UNITS':
            require(label(document['unit_name']), 'BILLING_UNIT')
            units = money(document['units_per_request'])
            require(units > 0 and units * 3 <= money(document['available_units']), 'BILLING_PREPAID_HEADROOM')
            unit_total = format(units * 3, 'f')
        else:
            require(all(document[k] is None for k in ('unit_name', 'units_per_request', 'available_units')),
                    'BILLING_NOT_PREPAID')
            unit_total = None
        total = format(charge * 3, 'f')
    return {'schema': 'iios-alpha-observation-billing-review-v1', 'scope': 'OFFLINE_INTEGRATION_ONLY',
        'billing_parent': expected, 'plan_parent': plan_hash, 'model': document['model'],
        'request_cap': 3, 'maximum_spend': total, 'spending_cap': document['spending_cap'],
        'currency': document['currency'], 'prepaid_units_reserved_maximum': unit_total,
        # Existing package arithmetic is currency-neutral. This projection is
        # local spending headroom, NOT a fabricated provider credit balance.
        'package_projection': {'cost_unit': document['currency'],
            'maximum_request_cost': document['maximum_request_charge'],
            'available_unreserved': document['spending_headroom'], 'maximum_cost': total},
        'ambiguous_consumption': 'KEEP_REQUEST_AND_MAXIMUM_SPEND_RESERVED',
        'authority': locked_authority(), 'allowance_released': False, 'production_qualified': False}

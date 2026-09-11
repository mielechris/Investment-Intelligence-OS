"""Explicit qualification admission. Public pins never imply operational authority."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from provider_gateway_contract import canonical, content_hash, locked_authority, pin, safe_document, symbols, utc
from provider_gateway_adapters import FEEDS

SELECTORS = {
    'ALPACA': ('IIOS_ALPACA_PAPER_API_KEY', 'IIOS_ALPACA_PAPER_API_SECRET'),
    'MASSIVE': ('IIOS_MASSIVE_API_KEY',),
    'FINANCIAL_DATASETS': ('IIOS_FINANCIAL_DATASETS_API_KEY',),
    'BIGDATA': ('IIOS_BIGDATA_API_KEY',),
    'ALPHA_VANTAGE': ('IIOS_ALPHA_VANTAGE_API_KEY',),
}
ROUTES = {
    'ALPACA': ('GET', 'data.alpaca.markets', '/v2/stocks/snapshots', 'MULTI_SYMBOL_SNAPSHOT'),
    'MASSIVE': ('GET', 'api.massive.com', '/v2/snapshot/locale/us/markets/stocks/tickers', 'BULK_SNAPSHOT'),
    'FINANCIAL_DATASETS': ('GET', 'api.financialdatasets.ai', '/company/facts', 'COMPANY_FACTS'),
    'BIGDATA': ('POST', 'api.bigdata.com', '/v1/search', 'COMPANY_RESEARCH'),
    'ALPHA_VANTAGE': ('GET', 'www.alphavantage.co', '/query', 'ENRICHMENT'),
}
CLAIMS = ('endpoint', 'symbols', 'feed', 'rate', 'cost', 'internal_use', 'billing', 'selector_binding', 'retention')
BASE = '9528c229a534a4fa21c0053fdf6b8586f586f6a2'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def amount(value):
    require(isinstance(value, str) and bool(re.fullmatch(r'\d+(?:\.\d{1,8})?', value)), 'AMOUNT_INVALID')
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError('AMOUNT_INVALID') from None
    require(result.is_finite() and result >= 0, 'AMOUNT_INVALID')
    return result


def request_parameters(provider, members, feed, *, function=None):
    """No arbitrary URL, credential, account, query or provider fallback input."""
    require(function is None or provider == 'ALPHA_VANTAGE', 'FUNCTION_PROVIDER')
    members = symbols(members)
    if provider == 'ALPACA':
        return {'symbols': ','.join(members), 'feed': feed}
    if provider == 'MASSIVE':
        return {'tickers': ','.join(members), 'include_otc': 'false'}
    require(members == ['MU'], 'SINGLE_CORPORATE_PILOT_REQUIRED')
    if provider == 'FINANCIAL_DATASETS':
        return {'ticker': 'MU'}
    if provider == 'ALPHA_VANTAGE':
        require(function in (None, 'SMA', 'GLOBAL_QUOTE'), 'ALPHA_FUNCTION')
        if function == 'GLOBAL_QUOTE':
            return {'function': 'GLOBAL_QUOTE', 'symbol': 'MU', 'entitlement': 'realtime', 'datatype': 'json'}
        return {'function': 'SMA', 'symbol': 'MU', 'interval': 'daily', 'time_period': '20', 'series_type': 'close', 'datatype': 'json'}
    require(provider == 'BIGDATA', 'PROVIDER_INVALID')
    return {'search_mode': 'fast', 'query': {'text': 'Micron Technology MU corporate evidence', 'max_chunks': 10}, 'include_audit': True}


@dataclass(frozen=True, repr=False)
class Admission:
    _manifest: bytes = field(repr=False)
    _account: bytes = field(repr=False)
    _runtime: bytes = field(repr=False)
    parents: tuple

    def documents(self):
        return tuple(json.loads(x) for x in (self._manifest, self._account, self._runtime))

    def recheck(self, now):
        m, a, r = self.documents()
        return admit(m, a, r, expected=dict(self.parents), now=now)


def admit(manifest, account, runtime, *, expected, now):
    """Expected hashes are supplied independently of all three documents."""
    require(set(expected) == {'manifest', 'account', 'runtime'}, 'PARENT_SET_INVALID')
    for name, doc in (('manifest', manifest), ('account', account), ('runtime', runtime)):
        safe_document(doc)
        pin(doc, expected[name])
    m, a, r = manifest, account, runtime
    require(set(m) == {'schema', 'mode', 'batch_id', 'provider', 'role', 'source_commit', 'account_parent', 'runtime_parent', 'root', 'symbols', 'feed', 'method', 'host', 'path', 'endpoint', 'parameters', 'valid_from', 'expires_at', 'maximum_requests', 'maximum_cost', 'cost_unit', 'timeout_seconds', 'maximum_response_bytes', 'maximum_age_seconds', 'authority', 'qualification_authorized'}, 'MANIFEST_SCHEMA')
    require(m['schema'] == 'iios-provider-qualification-v1' and m['mode'] in ('OFFLINE_TEST', 'LIVE_QUALIFICATION'), 'MODE_INVALID')
    require(m['authority'] == locked_authority() and all(v is False for v in m['authority'].values()), 'AUTHORITY_INVALID')
    require(m['qualification_authorized'] is True, 'QUALIFICATION_AUTHORITY_REQUIRED')
    require(m['provider'] in ROUTES, 'PROVIDER_INVALID')
    from provider_gateway_contract import PROVIDER_ROLES
    p = m['provider']
    require(m['role'] == PROVIDER_ROLES[p], 'ROLE_SUBSTITUTION')
    require((m['method'], m['host'], m['path'], m['endpoint']) == ROUTES[p], 'ROUTE_SUBSTITUTION')
    require(m['feed'] in FEEDS[p] and m['feed'] != 'unavailable', 'FEED_REQUIRED')
    require(symbols(m['symbols']) == m['symbols'] and len(m['symbols']) <= 517, 'SYMBOL_SCOPE')
    function = m['parameters'].get('function') if p == 'ALPHA_VANTAGE' and isinstance(m['parameters'], dict) else None
    require(m['parameters'] == request_parameters(p, m['symbols'], m['feed'], function=function), 'PARAMETER_SUBSTITUTION')
    alpha_quote = p == 'ALPHA_VANTAGE' and function == 'GLOBAL_QUOTE'
    if alpha_quote:
        require(m['timeout_seconds'] <= 20 and m['maximum_response_bytes'] <= 1_000_000, 'QUOTE_TRANSPORT_BOUND')
        require(a.get('qualification_parameters') == m['parameters'], 'QUOTE_ACCOUNT_FUNCTION_BINDING')
    require(m['maximum_requests'] == 1 and type(m['maximum_requests']) is int, 'ONE_REQUEST_REQUIRED')
    require(type(m['timeout_seconds']) is int and 1 <= m['timeout_seconds'] <= 20, 'DEADLINE_INVALID')
    require(type(m['maximum_response_bytes']) is int and 1 <= m['maximum_response_bytes'] <= 4_000_000, 'BODY_BOUND_INVALID')
    require(type(m['maximum_age_seconds']) is int and 0 < m['maximum_age_seconds'] <= 86400, 'FRESHNESS_BOUND_INVALID')
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,80}', m['batch_id']) is not None, 'BATCH_ID_INVALID')
    root = Path(m['root'])
    require(root.is_absolute() and root.resolve() == root and not root.is_symlink(), 'ROOT_ALIAS')
    require(utc(m['valid_from']) <= utc(now) < utc(m['expires_at']), 'AUTHORITY_EXPIRED')
    require(m['account_parent'] == expected['account'] and m['runtime_parent'] == expected['runtime'], 'WRONG_PARENT')
    require(re.fullmatch(r'[a-f0-9]{40}', m['source_commit']) is not None and m['source_commit'] == r.get('source_commit'), 'SOURCE_BINDING')
    require(m['mode'] != 'LIVE_QUALIFICATION' or m['source_commit'] != BASE, 'EDITED_SOURCE_NOT_BASE')
    require(a.get('provider') == p and a.get('account_identity') and a.get('tier_identity'), 'ACCOUNT_REQUIRED')
    require(a.get('scope') == m['mode'], 'ACCOUNT_SCOPE')
    require(a.get('selectors') == [{'service': s, 'account': 'iios-provider'} for s in SELECTORS[p]], 'SELECTOR_SUBSTITUTION')
    require(a.get('endpoint') == m['endpoint'] and a.get('feed') == m['feed'] and a.get('symbols') == m['symbols'], 'ACCOUNT_SCOPE')
    require(utc(a['valid_from']) <= utc(m['valid_from']) and utc(a['expires_at']) >= utc(m['expires_at']), 'ACCOUNT_EXPIRED')
    proofs = a.get('proofs', {})
    require(set(proofs) == set(CLAIMS), 'ACCOUNT_PROOFS_REQUIRED')
    for proof in proofs.values():
        require(set(proof) == {'status', 'evidence_sha256'} and proof['status'] == 'VERIFIED' and re.fullmatch('[a-f0-9]{64}', proof['evidence_sha256']) is not None, 'ACCOUNT_PROOF_UNVERIFIED')
    require(a.get('cost_unit') == m['cost_unit'] and isinstance(m['cost_unit'], str) and 0 < len(m['cost_unit']) <= 40, 'COST_UNIT')
    require(amount(a['maximum_request_cost']) <= amount(m['maximum_cost']) <= amount(a['available_unreserved']), 'COST_UNBOUNDED')
    require(type(a.get('rate_per_minute')) is int and a['rate_per_minute'] >= 1 and a.get('rate_slot_reserved') is True, 'RATE_SLOT_REQUIRED')
    if alpha_quote:
        require(a['rate_per_minute'] <= 150, 'ALPHA_DOCUMENTED_RATE_CEILING')
    require(a.get('overage_enabled') is False and a.get('automatic_top_up') is False, 'OVERAGE_NOT_DISABLED')
    require(a.get('ambiguous_billing') == 'RESERVE_MAXIMUM_NO_RETRY', 'BILLING_RULE_REQUIRED')
    retention = a.get('retention', {})
    require(retention.get('raw_body') is True and retention.get('normalized') is True and retention.get('references') is True and retention.get('hashes') is True, 'RETENTION_NOT_ESTABLISHED')
    require(retention.get('agreement_sha256') == proofs['retention']['evidence_sha256'] and utc(retention['retain_until']) >= utc(m['expires_at']), 'RETENTION_BINDING')
    if p == 'BIGDATA':
        require(retention.get('explicit_api_storage_permission') is True and retention.get('no_grounding_or_model_call') is True, 'BIGDATA_STORAGE_BLOCKED')
    require(r.get('scope') == m['mode'], 'RUNTIME_SCOPE')
    return Admission(canonical(m), canonical(a), canonical(r), tuple(sorted(expected.items())))


def verify_qualification_receipt(receipt, expected_hash, *, parents):
    """Check an independently supplied receipt identity and complete parent set."""
    safe_document(receipt)
    pin(receipt, expected_hash)
    body = {key: value for key, value in receipt.items() if key != 'receipt_hash'}
    require(receipt.get('receipt_hash') == content_hash(body), 'RECEIPT_SELF_HASH')
    require(set(parents) == {'manifest', 'account', 'runtime', 'reservation'} and receipt.get('parents') == parents, 'RECEIPT_PARENT_SUBSTITUTION')
    require(receipt.get('schema') == 'iios-provider-qualification-receipt-v1' and receipt.get('scope') in ('OFFLINE_TEST', 'LIVE_QUALIFICATION'), 'RECEIPT_SCOPE')
    require(receipt.get('authority') == locked_authority() and all(v is False for v in receipt['authority'].values()), 'RECEIPT_AUTHORITY')
    require(receipt.get('provider_readiness') == 'NOT_READY' and receipt.get('retry_count') == 0, 'RECEIPT_OVERCLAIM')
    observations = receipt.get('observations')
    require((observations is None and receipt.get('normalized_sha256') is None) or (observations is not None and content_hash(observations) == receipt.get('normalized_sha256')), 'OBSERVATION_HASH')
    return receipt

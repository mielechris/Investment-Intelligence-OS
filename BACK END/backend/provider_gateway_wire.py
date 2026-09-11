"""Public response decoding. No I/O, secret material or invented event times."""
from __future__ import annotations

from collections import Counter
from datetime import date as calendar_date
from decimal import Decimal
import re

from provider_gateway_adapters import normalize
from provider_gateway_contract import freshness, safe_document
from provider_gateway_live_contract import Admission, require


def decode(admission, payload, *, received_at):
    require(type(admission) is Admission, 'ADMISSION_REQUIRED')
    admission.recheck(received_at)
    m, account, _ = admission.documents()
    safe_document(payload)
    require(isinstance(payload, dict), 'WIRE_SCHEMA')
    require(not any(k in payload for k in ('error', 'errors', 'message', 'code', 'Note', 'Information', 'Error Message', 'next_url', 'next_page_token', 'next_cursor')), 'ERROR_OR_PAGINATION')
    p = m['provider']
    original = payload
    alpha_quote = p == 'ALPHA_VANTAGE' and m['parameters']['function'] == 'GLOBAL_QUOTE'
    if p == 'FINANCIAL_DATASETS':
        require(set(payload) == {'company_facts'} and isinstance(payload['company_facts'], dict), 'FD_FACTS_SCHEMA')
        facts = payload['company_facts']
        require(facts.get('ticker') == m['symbols'][0], 'FD_SYMBOL_MISMATCH')
        payload = {'records': [facts]}
    elif p == 'BIGDATA':
        retention = account['retention']
        require(retention.get('explicit_api_storage_permission') is True and retention.get('references') is True, 'BIGDATA_STORAGE_BLOCKED')
        require(isinstance(payload.get('results'), list) and not payload.get('external_results'), 'BIGDATA_WIRE_SCOPE')
        rows = []
        for document in payload['results']:
            require(isinstance(document, dict) and isinstance(document.get('id'), str), 'DOCUMENT_ID_REQUIRED')
            rows.append({'ticker': 'MU', 'document_identity': document['id'], 'publication_time': document.get('timestamp'), 'observation_time': None, 'source_references': [document['url']] if document.get('url') else []})
        # Query association is not demonstrated company/ticker coverage.
        payload = {'records': rows}
    elif alpha_quote:
        require(set(payload) == {'Global Quote'} and isinstance(payload['Global Quote'], dict), 'QUOTE_SCHEMA')
        quote = payload['Global Quote']
        require(quote.get('01. symbol') == 'MU', 'QUOTE_SYMBOL')
        price = quote.get('05. price')
        require(isinstance(price, str) and re.fullmatch(r'\d+(?:\.\d+)?', price) is not None, 'QUOTE_PRICE')
        require(Decimal(price).is_finite() and Decimal(price) > 0, 'QUOTE_PRICE')
        day = quote.get('07. latest trading day')
        if day is not None:
            require(isinstance(day, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) is not None, 'QUOTE_DATE')
            calendar_date.fromisoformat(day)
        payload = {'records': [{'ticker': 'MU', 'indicator': 'GLOBAL_QUOTE_PRICE', 'value': price, 'observation_time': None, 'publication_time': None}]}
    elif p == 'ALPHA_VANTAGE':
        meta, points = payload.get('Meta Data'), payload.get('Technical Analysis: SMA')
        require(isinstance(meta, dict) and meta.get('1: Symbol') == 'MU' and isinstance(points, dict), 'INDICATOR_SCHEMA')
        require(meta.get('4: Interval') == 'daily' and str(meta.get('5: Time Period')) == '20' and meta.get('6: Series Type') == 'close', 'INDICATOR_PARAMETERS')
        rows = []
        for date, point in sorted(points.items()):
            require(re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) is not None and isinstance(point, dict), 'INDICATOR_DATE')
            number = Decimal(point['SMA'])
            require(number.is_finite(), 'INDICATOR_NUMBER')
            rows.append({'ticker': 'MU', 'indicator': 'SMA_DAILY_20_CLOSE', 'value': str(number), 'observation_time': None, 'publication_time': None})
        payload = {'records': rows}
    parsed = normalize(p, m['endpoint'], payload)
    rows = parsed['observations']
    counts = Counter(row['ticker'] for row in rows)
    requested, returned = set(m['symbols']), set(counts)
    # Multiple historical periods/research documents are not duplicate quotes.
    duplicates = sorted(s for s, n in counts.items() if n > 1) if p in ('MASSIVE', 'ALPACA', 'FINANCIAL_DATASETS') else []
    missing, unexpected = sorted(requested - returned), sorted(returned - requested)
    if alpha_quote:
        rows[0]['provider_event_timestamps']['latest_trading_day'] = day
        rows[0]['event_time_basis'] = 'PROVIDER_TRADING_DATE_NO_INSTANT' if day else 'NO_PROVIDER_TIMESTAMP'
    elif p == 'ALPHA_VANTAGE':
        for row, date in zip(rows, sorted(original['Technical Analysis: SMA'])):
            row['provider_event_timestamps']['period_date'] = date
            row['provider_event_timestamps']['provider_timezone'] = original['Meta Data'].get('7: Time Zone')
            row['event_time_basis'] = 'PROVIDER_PERIOD_DATE_NO_INSTANT'
    delay_conflict = (p in ('ALPACA', 'MASSIVE') and m['feed'] in ('sip', 'real_time') and (parsed['status'] == 'DELAYED' or (parsed['provider_reported_delay'] or 0) > 0))
    result = {'observations': rows, 'provider_timestamps': [r['provider_event_timestamps'] for r in rows],
            'requested_symbols': m['symbols'], 'returned_symbols': sorted(returned), 'missing_symbols': missing,
            'unexpected_symbols': unexpected, 'duplicate_symbols': duplicates,
            'coverage': 'QUERY_ASSOCIATION_ONLY' if p == 'BIGDATA' else 'COMPLETE' if not missing and not unexpected and not duplicates and not parsed['partial_response'] else 'PARTIAL',
            'freshness': [freshness(r['event_time'], received_at, m['maximum_age_seconds']) for r in rows],
            'feed': m['feed'], 'feed_basis': 'PINNED_ACCOUNT_AND_EXPLICIT_REQUEST', 'feed_conflict': delay_conflict,
            'provider_reported_delay': parsed['provider_reported_delay'], 'atomic_exchange_snapshot': False,
            'provider_usage': original.get('usage') if p == 'BIGDATA' else None,
            'usage_basis': 'PROVIDER_REPORTED_NOT_INDEPENDENT_BILLING_PROOF', 'provider_readiness': 'NOT_READY'}

    if alpha_quote:
        result.update({'requested_entitlement': 'realtime', 'response_realtime_entitlement': 'UNVERIFIED',
                       'provider_feed_evidence': {k: v for k, v in quote.items() if any(word in k.lower() for word in ('feed', 'entitlement', 'delay'))},
                       'provider_quote_fields': quote, 'feed_basis': 'SECONDARY_ROLE_ONLY_NOT_RESPONSE_REALTIME_PROOF'})
    return result

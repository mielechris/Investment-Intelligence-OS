"""Offline session identity validation; never execution or calendar authority.

The caller supplies independently accepted hashes. This module does not decide
exchange holidays, approve accounts, or replace the legacy production runner.
"""
from datetime import date, datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from provider_gateway_contract import pin, safe_document, symbols, locked_authority

SCHEMA = 'iios-alpha-session-identity-v1'
CALENDAR_SCHEMA = 'iios-reviewed-exchange-session-v1'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def instant(value):
    require(type(value) is str, 'SESSION_TIMESTAMP')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError('SESSION_TIMESTAMP') from None
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), 'SESSION_TIMESTAMP')
    require(value == parsed.isoformat(), 'SESSION_TIMESTAMP_CANONICAL')
    return parsed


def validate_session(contract, calendar, universe, *, expected, now):
    """Validate data only; a successful return explicitly grants no authority."""
    require(type(expected) is dict and set(expected) == {'session', 'calendar', 'universe'}, 'SESSION_PINS')
    for value, name in ((contract, 'session'), (calendar, 'calendar'), (universe, 'universe')):
        safe_document(value)
        pin(value, expected[name])
    require(type(contract) is dict and set(contract) == {
        'schema', 'source_commit', 'session', 'calendar_parent', 'universe_parent',
        'valid_from', 'expires_at', 'authority'}, 'SESSION_SCHEMA')
    require(contract['schema'] == SCHEMA, 'SESSION_SCHEMA')
    require(type(contract['source_commit']) is str and
            re.fullmatch('[0-9a-f]{40}', contract['source_commit']) is not None, 'SESSION_SOURCE')
    require(contract['calendar_parent'] == expected['calendar'] and
            contract['universe_parent'] == expected['universe'], 'SESSION_PARENTS')
    authority = contract['authority']
    require(type(authority) is dict and set(authority) == set(locked_authority()) and
            all(value is False for value in authority.values()), 'SESSION_AUTHORITY')
    require(type(calendar) is dict and set(calendar) == {
        'schema', 'exchange', 'timezone', 'session', 'open', 'close', 'review_parent'}, 'SESSION_CALENDAR')
    require(calendar['schema'] == CALENDAR_SCHEMA and calendar['exchange'] == 'XNYS' and
            calendar['timezone'] == 'America/New_York', 'SESSION_CALENDAR')
    require(type(calendar['review_parent']) is str and
            re.fullmatch('[0-9a-f]{64}', calendar['review_parent']) is not None, 'CALENDAR_REVIEW_REQUIRED')
    try:
        session = date.fromisoformat(contract['session'])
    except (ValueError, TypeError):
        raise ValueError('SESSION_DATE') from None
    require(session.isoformat() == contract['session'] == calendar['session'], 'SESSION_DATE')
    opening, closing = instant(calendar['open']), instant(calendar['close'])
    local_open, local_close = (x.astimezone(ZoneInfo(calendar['timezone'])) for x in (opening, closing))
    require(local_open.date() == local_close.date() == session and
            timedelta(0) < closing - opening <= timedelta(hours=6, minutes=30), 'SESSION_WINDOW')
    start, expiry = instant(contract['valid_from']), instant(contract['expires_at'])
    require(start <= opening < closing <= expiry and
            expiry - start <= timedelta(days=1), 'SESSION_VALIDITY')
    require(isinstance(now, datetime) and now.tzinfo is not None and
            now.utcoffset() == timedelta(0), 'SESSION_CLOCK')
    require(start <= now < expiry, 'SESSION_EXPIRED_OR_NOT_STARTED')
    require(type(universe) is list, 'SESSION_UNIVERSE')
    symbols(universe, count=517)
    return {'schema': 'iios-alpha-session-contract-check-v1', 'status': 'CONTRACT_VALID_ONLY',
            'session': session.isoformat(), 'source_commit': contract['source_commit'],
            'parents': dict(expected), 'authority': locked_authority(),
            'production_qualified': False, 'execution_authorized': False}

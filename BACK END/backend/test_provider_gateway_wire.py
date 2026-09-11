import unittest
from provider_gateway_wire import decode
from test_provider_gateway_live_contract import admitted, NOW
from test_provider_gateway_transport import snapshot


def facts():
    return {'company_facts': {'ticker': 'MU', 'name': 'Synthetic Corporation', 'sector': 'Technology', 'industry': 'Synthetic', 'exchange': 'SYNTHETIC'}}


def research():
    return {'results': [{'id': 'synthetic-document', 'timestamp': NOW, 'url': 'https://example.invalid/document'}], 'usage': {'api_query_units': 1}, 'external_results': {}}


def enrichment():
    return {'Meta Data': {'1: Symbol': 'MU', '4: Interval': 'daily', '5: Time Period': 20, '6: Series Type': 'close', '7: Time Zone': 'US/Eastern'}, 'Technical Analysis: SMA': {'2026-09-11': {'SMA': '123.4567890123456789'}}}


class WireTests(unittest.TestCase):
    def test_missing_unexpected_and_quote_timestamps(self):
        value = decode(admitted(), {'OTHER': snapshot()['MU']}, received_at=NOW)
        self.assertEqual(value['missing_symbols'], ['MU'])
        self.assertEqual(value['unexpected_symbols'], ['OTHER'])
        self.assertEqual(value['provider_timestamps'][0]['quote'], NOW)
        self.assertEqual(value['coverage'], 'PARTIAL')

    def test_massive_duplicates_and_nanosecond_precision(self):
        row = {'ticker': 'MU', 'lastQuote': {'p': 99, 'P': 101, 't': 1789392630000000001}}
        value = decode(admitted('MASSIVE'), {'tickers': [row, row]}, received_at=NOW)
        self.assertEqual(value['duplicate_symbols'], ['MU'])
        self.assertEqual(value['provider_timestamps'][0]['quote'], 1789392630000000001)
        self.assertFalse(value['atomic_exchange_snapshot'])

    def test_fd_original_missing_time_not_receipt_time(self):
        value = decode(admitted('FINANCIAL_DATASETS'), facts(), received_at=NOW)
        self.assertIsNone(value['observations'][0]['event_time'])
        self.assertEqual(value['freshness'], ['UNVERIFIED'])

    def test_fd_wrong_ticker_rejected(self):
        payload = facts()
        payload['company_facts']['ticker'] = 'OTHER'
        with self.assertRaises(ValueError):
            decode(admitted('FINANCIAL_DATASETS'), payload, received_at=NOW)

    def test_research_association_not_coverage_and_references_preserved(self):
        value = decode(admitted('BIGDATA'), research(), received_at=NOW)
        self.assertEqual(value['coverage'], 'QUERY_ASSOCIATION_ONLY')
        self.assertEqual(value['observations'][0]['publication_time'], NOW)
        self.assertIsNone(value['observations'][0]['event_time'])
        self.assertEqual(value['provider_usage'], {'api_query_units': 1})

    def test_research_external_search_rejected(self):
        payload = research()
        payload['external_results'] = {'web': [{'id': 'extra'}]}
        with self.assertRaises(ValueError):
            decode(admitted('BIGDATA'), payload, received_at=NOW)

    def test_indicator_precision_date_and_timezone_not_fabricated_instant(self):
        value = decode(admitted('ALPHA_VANTAGE'), enrichment(), received_at=NOW)
        row = value['observations'][0]
        self.assertEqual(row['fields']['value'], '123.4567890123456789')
        self.assertEqual(row['provider_event_timestamps']['period_date'], '2026-09-11')
        self.assertIsNone(row['event_time'])

    def test_indicator_wrong_contract_rejected(self):
        payload = enrichment()
        payload['Meta Data']['4: Interval'] = '1min'
        with self.assertRaises(ValueError):
            decode(admitted('ALPHA_VANTAGE'), payload, received_at=NOW)

    def test_provider_errors_and_pagination_fail_closed(self):
        for key in ('Note', 'Information', 'Error Message', 'next_url', 'next_page_token', 'next_cursor'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                decode(admitted(), {key: 'synthetic'}, received_at=NOW)

    def test_delay_conflict_and_unchanged_prices(self):
        a = admitted('MASSIVE')
        value = decode(a, {'status': 'DELAYED', 'tickers': []}, received_at=NOW)
        self.assertTrue(value['feed_conflict'])
        a = admitted()
        first = decode(a, snapshot(), received_at=NOW)
        second = decode(a, snapshot(), received_at=NOW)
        self.assertEqual(first['freshness'], ['CURRENT'])
        self.assertEqual(first, second)

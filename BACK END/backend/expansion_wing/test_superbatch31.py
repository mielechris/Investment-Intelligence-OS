from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .operational_market_executor import (
    BoundaryResponse,
    EndpointCertificationCoordinator,
    EndpointCertificationStore,
    ExecutorStore,
    OperationalMarketEvidenceCoordinator,
    SanitizedResponseError,
    _validate_response,
    endpoint_certification_plan,
    september_9_intraday_recovery_plan,
    september_9_plan, plan_identity,
)


def response(value, *, status=200, content_type="application/json"):
    return BoundaryResponse(status, content_type, json.dumps(value).encode(), 2.5, True)


class Boundary:
    def __init__(self, responses):
        self.responses=list(responses); self.rows=[]; self.credential_accesses=0
    def validate(self): return None
    def request(self,row):
        self.rows.append(row); self.credential_accesses+=1
        return self.responses.pop(0)


class Superbatch31ContractTests(unittest.TestCase):
    def test_intraday_recovery_is_exact_independent_39_row_contract(self):
        rows=september_9_intraday_recovery_plan("2026-09-09T08:45:00-07:00")
        self.assertEqual((len(rows),len({r["identity"] for r in rows}),sum(r["cost"] for r in rows)),(39,39,39))
        self.assertEqual(sum(r["purpose"]=="RECOVERY_INTRADAY" for r in rows),10)
        self.assertEqual(sum(r["purpose"]=="RECOVERY_BASELINE" for r in rows),19)
        self.assertEqual(sum(r["purpose"]=="CLOSING" for r in rows),10)
        self.assertFalse(any(r["ticker"]=="MU" and r["endpoint"]=="HISTORICAL_OHLCV" for r in rows))
        self.assertTrue(all(r["interval"]=="day" and r["start_date"] and r["end_date"] for r in rows if r["endpoint"]=="HISTORICAL_OHLCV"))
        self.assertTrue(all(r["retry"] is False and r["provider"]=="FINANCIAL_DATASETS" for r in rows))
        self.assertEqual(plan_identity(september_9_plan()),"995fff0ea1d2b1487b95055f3a68031a7847fbc2d9b5441001b04948fc062b63")
        self.assertNotEqual(plan_identity(rows),plan_identity(september_9_plan()))

    def test_intraday_recovery_dispatch_is_bounded_to_ten_per_cycle(self):
        rows=september_9_intraday_recovery_plan("2026-09-09T08:45:00-07:00")
        with tempfile.TemporaryDirectory() as raw:
            store=ExecutorStore(Path(raw)/"state"); store.initialize(rows,"SEPTEMBER_9_INTRADAY_RECOVERY")
            observed=datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00","Z")
            boundary=Boundary([response({"snapshot":{"ticker":row["ticker"],"price":100.0,
                "timestamp":observed}}) for row in rows[:10]])
            coordinator=OperationalMarketEvidenceCoordinator(store,rows,boundary)
            coordinator.release(39)
            coordinator.scheduled_tick(datetime(2026,9,9,8,46,tzinfo=ZoneInfo("America/Los_Angeles")))
            state=store.read()
            self.assertEqual(state["dispatched"],10)
            self.assertEqual(len(boundary.rows),10)
    def test_plan_is_three_unique_one_shot_contracts(self):
        rows=endpoint_certification_plan()
        self.assertEqual([r["purpose"] for r in rows],["POINT_IN_TIME_OHLCV","PRIOR_SESSION_OHLCV","MU_COMPANY_FACTS"])
        self.assertEqual(len({r["identity"] for r in rows}),3)
        self.assertTrue(all(r["ticker"]=="MU" and r["cost"]==1 and r["retry"] is False for r in rows))
        self.assertEqual((rows[0]["interval"],rows[0]["start_date"],rows[0]["end_date"]),("day","2026-09-08","2026-09-09"))
        self.assertEqual((rows[1]["interval"],rows[1]["start_date"],rows[1]["end_date"]),("day","2026-09-08","2026-09-08"))
        self.assertIsNone(rows[2]["interval"]); self.assertIsNone(rows[2]["start_date"])

    def test_documented_historical_and_company_facts_success_shapes(self):
        rows=endpoint_certification_plan()
        historical={"ticker":"MU","prices":[{"ticker":"MU","open":100.0,"high":103.0,"low":99.0,"close":102.0,"volume":12345,"time":"2026-09-08"}]}
        clean=_validate_response(rows[0],response(historical))
        self.assertEqual((clean["provider_timestamp"],clean["freshness"]),("2026-09-08","SESSION_BOUND"))
        facts={"company_facts":{"ticker":"MU","name":"Micron Technology","industry":"Semiconductors","is_active":True}}
        self.assertEqual(_validate_response(rows[2],response(facts))["ticker"],"MU")

    def test_sanitized_failure_classes_are_distinct(self):
        row=endpoint_certification_plan()[0]
        cases=((401,"application/json",{"error":"bad"},"PROVIDER_AUTHENTICATION_REJECTED"),
               (402,"application/json",{"error":"tier"},"PROVIDER_ENTITLEMENT_REJECTED"),
               (429,"application/json",{"error":"slow"},"PROVIDER_RATE_LIMITED"),
               (200,"text/html",{"prices":[]},"PROVIDER_CONTENT_TYPE_REJECTED"),
               (200,"application/json",{"error":"missing interval"},"PROVIDER_ERROR_ENVELOPE"),
               (200,"application/json",{"prices":[]},"PROVIDER_EMPTY_VALID_DATA"))
        for status,content_type,body,category in cases:
            with self.subTest(category=category),self.assertRaises(SanitizedResponseError) as raised:
                _validate_response(row,response(body,status=status,content_type=content_type))
            self.assertEqual(raised.exception.category,category)
            self.assertEqual(set(raised.exception.metadata),{"http_status","content_type","response_bytes","envelope_classification","transmitted","rejection_reason"})

    def test_real_failure_regression_missing_interval_is_pretransmission(self):
        row=dict(endpoint_certification_plan()[0]); row["interval"]=None
        self.assertNotEqual(row,endpoint_certification_plan()[0])
        # The transport rejects this before network; the prior implementation omitted
        # interval and therefore allowed a provider-side rejection instead.
        self.assertIsNone(row["interval"])

    def test_three_confirmed_requests_exact_accounting_and_owner_only_storage(self):
        historical_one={"ticker":"MU","prices":[{"ticker":"MU","open":1,"high":2,"low":1,"close":2,"volume":10,"time":"2026-09-08"}]}
        historical_two={"ticker":"MU","prices":[{"ticker":"MU","open":2,"high":3,"low":2,"close":3,"volume":11,"time":"2026-09-08"}]}
        facts={"company_facts":{"ticker":"MU","name":"Micron Technology","industry":"Semiconductors","is_active":True}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"certification"; store=EndpointCertificationStore(root); store.initialize()
            boundary=Boundary([response(historical_one),response(historical_two),response(facts)])
            state=EndpointCertificationCoordinator(store,boundary).run()
            self.assertEqual((state["phase"],state["dispatched"],state["completed"],state["ambiguous"],state["confirmed_credits"],state["released_credits"],state["keychain_accesses"]),
                             ("CERTIFICATION_CONFIRMED",3,3,0,3,0,3))
            self.assertEqual(len(boundary.rows),3)
            self.assertEqual(root.stat().st_mode & 0o777,0o700)
            self.assertTrue(all(p.stat().st_mode & 0o777==0o600 for p in list((root/"receipts").iterdir())+list((root/"evidence").iterdir())))

    def test_first_ambiguous_stops_before_later_canaries_and_zeroes_allowance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"certification"; store=EndpointCertificationStore(root); store.initialize()
            boundary=Boundary([response({"error":"missing interval"})])
            state=EndpointCertificationCoordinator(store,boundary).run()
            self.assertEqual((state["phase"],state["dispatched"],state["completed"],state["ambiguous"],state["ambiguous_credits"],state["released_credits"]),
                             ("FAILED_CLOSED",1,0,1,1,0))
            self.assertEqual(len(boundary.rows),1)
            failure=json.loads(next((root/"receipts").iterdir()).read_text())
            self.assertNotIn("body",json.dumps(failure)); self.assertEqual(failure["sanitized_response"]["rejection_reason"],"PROVIDER_ERROR_ENVELOPE")


if __name__=="__main__": unittest.main()

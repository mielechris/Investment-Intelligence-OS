"""SB3.6B: isolated SQLite captures through the actual publisher and GET path."""
import ast
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

import test_truth_spine_session as fixtures
from truth_spine_adapters import coverage_metadata
from truth_spine_contract import canonical, seal, digest
from truth_spine_factory_coverage import AGENTS, ROOMS, ROUTES, HISTORY, SUBSYSTEMS, factory_coverage
from truth_spine_full_day_service import service_response
from truth_spine_generations import GenerationStore
from truth_spine_integration import atomic
from truth_spine_session_package import captured_cycle, BACKEND_FILES


class FactoryCoverageTests(unittest.TestCase):
    setUp = fixtures.ProductionPathTests.setUp
    write_cycle = fixtures.ProductionPathTests.write_cycle
    actual_probes = fixtures.ProductionPathTests.actual_probes

    def add(self, key, kind, payload, store="historical"):
        with closing(sqlite3.connect(self.base/(store+".db"))) as db, db:
            db.execute("INSERT INTO ledger_objects VALUES (?,?,?,?)", (key,kind,canonical(payload).decode(),"2026-09-08T20:00:00Z"))

    def view(self):
        self.assertEqual(self.supervisor.cycle()["ready"],200)
        code, view = service_response(self.root/"topology.json","/truth-spine/full-session",now=self.clock())
        self.assertEqual(code,200)
        self.assertEqual(view["readiness"],200)
        self.assertIsNotNone(view["factory"])
        self.assertEqual(view["factory"],json.loads((self.root/"projections/current.json").read_bytes())["factory"])
        return view["factory"]

    def test_exact_catalogs_match_committed_configuration_and_frontend(self):
        def literal(path, name):
            tree = ast.parse(path.read_text())
            return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                        and any(isinstance(t,ast.Name) and t.id == name for t in n.targets))
        source = Path(__file__).parent
        products = literal(source/"expansion_wing/multi_product_research.py","_PRODUCT_ROWS")
        agents = literal(source/"main.py","AGENT_CONFIGS")
        self.assertEqual(ROOMS,[[r[i] for i in (0,1,3,4,8)] for r in products])
        self.assertEqual(AGENTS,[[key,a["name"],a["room"]] for key,a in agents.items()])
        frontend = (source.parents[1]/"FRONT END/src/truthSpineFactoryView.ts").read_text()
        catalog = json.loads(frontend.split("export const factoryCatalog = ")[1].split(" as const;")[0])
        for key, rows in [("rooms",ROOMS),("agents",AGENTS),("routes",ROUTES),("history",HISTORY),("subsystems",SUBSYSTEMS)]:
            self.assertEqual(catalog[key],[[r[0],r[1]] for r in rows])
        self.assertEqual(len(ROOMS),24); self.assertEqual(len(AGENTS),8)
        self.assertIn("truth_spine_factory_coverage.py",BACKEND_FILES)

    def test_aggregate_records_never_manufacture_individual_counts(self):
        self.add("aggregate","agent_result",{"agents_complete":8,"rooms":24,"status":"complete","classification":"LIVE_VERIFIED"})
        f = self.view()
        self.assertEqual(len(f["rooms"]),24); self.assertEqual(len(f["agents"]),8)
        for r in f["rooms"]:
            self.assertIsNone(r["candidate_count"]); self.assertIsNone(r["case_count"])
            self.assertEqual(r["readiness"],"UNAVAILABLE"); self.assertEqual(r["bindings"],[])
        for a in f["agents"]: self.assertIsNone(a["completed_result_count"])

    def test_explicit_room_and_agent_identity_not_ticker_or_family(self):
        self.add("case-bound","case",{"product_id":ROOMS[0][0],"classification":"REPLAY"})
        self.add("candidate","opportunity_candidate",{"product_id":ROOMS[0][0],"classification":"SIMULATED"})
        self.add("ticker-only","case",{"ticker":"SPY","family":"EQUITY_ETF","classification":"LIVE_VERIFIED"})
        for key, _, _ in AGENTS:
            self.add(key,"agent_result",{"agent_key":key,"status":"complete","classification":"NARRATIVE"})
        f = self.view()
        self.assertEqual(f["rooms"][0]["case_count"],1); self.assertEqual(f["rooms"][0]["candidate_count"],1)
        self.assertTrue(all(r["case_count"] is None for r in f["rooms"][1:]))
        for a in f["agents"]:
            self.assertEqual(a["completed_result_count"],1); self.assertEqual(a["operational_state"],"SUPPRESSED")
            self.assertEqual(a["evidence_classifications"],{"NARRATIVE":1})
        self.assertEqual(f["governance"][0]["registered_agent_reference"],"skeptic")
        self.assertEqual(f["governance"][0]["binding_count"],1)

    def test_classifications_and_original_clocks_hashes_never_upgraded(self):
        classes = ["SIMULATED","REPLAY","NARRATIVE","UNAVAILABLE","STALE","FAILED_CLOSED"]
        for c in classes:
            self.add(c,"case",{"product_id":ROOMS[0][0],"classification":c,"created_at":"2026-09-08T19:00:00Z",
                               "observed_at":"2026-09-08T19:01:00Z","generated_at":"2026-09-08T19:02:00Z"})
        r = self.view()["rooms"][0]
        self.assertEqual(r["evidence_classifications"],dict.fromkeys(classes,1))
        self.assertEqual(r["operational_state"],"OBSERVATION_ONLY")
        for b in r["bindings"]:
            self.assertEqual(b["event_time"],"2026-09-08T19:00:00Z")
            self.assertEqual(b["observation_time"],"2026-09-08T19:01:00Z")
            self.assertEqual(b["publication_time"],"2026-09-08T19:02:00Z")
            self.assertEqual(len(b["payload_hash"]),64)

    def test_routes_unknown_disabled_and_no_provider_credential_or_model_call(self):
        with patch("socket.create_connection",side_effect=AssertionError("NETWORK_FORBIDDEN")), \
             patch("subprocess.run",side_effect=AssertionError("SUBPROCESS_FORBIDDEN")):
            f = self.view()
        self.assertEqual([r["id"] for r in f["routes"]],[r[0] for r in ROUTES])
        for r in f["routes"]:
            self.assertEqual(r["credential_presence"],"UNKNOWN"); self.assertEqual(r["configured"],"UNKNOWN")
            self.assertFalse(r["enabled"]); self.assertFalse(r["authoritative_truth_source"])
            self.assertEqual(r["request_count"],0); self.assertIsNone(r["credit_cost_count"])
            self.assertTrue(all(v is False for v in r["authority"].values()))

    def test_day_paper_is_retained_evidence_not_current_live_account(self):
        self.add("paper","paper_portfolio_snapshot",{"nav":10000,"cash":10000,"position_count":0,"classification":"HISTORICAL"},"operational")
        d = self.view()["day_trading"]
        self.assertEqual(d["paper"],{"nav":"10000","cash":"10000","positions":0})
        self.assertEqual(d["paper_scope"],"RETAINED_L7_SNAPSHOT_NOT_LIVE_ACCOUNT")
        self.assertEqual(d["order_allowance"],0)
        for k in ("paper_authority","live_authority","broker_connection"): self.assertIs(d[k],False)

    def test_missing_or_ambiguous_paper_is_unavailable(self):
        self.assertTrue(all(v is None for v in self.view()["day_trading"]["paper"].values()))

    def test_tied_paper_snapshots_not_arbitrarily_selected(self):
        for i in (1,2): self.add(str(i),"paper_portfolio_snapshot",{"nav":i,"cash":i,"position_count":0},"operational")
        self.assertTrue(all(v is None for v in self.view()["day_trading"]["paper"].values()))

    def test_history_subsystems_stores_never_merged(self):
        self.add("committee","committee_decision",{"classification":"HISTORICAL"})
        self.add("risk","risk_authorization",{"classification":"SIMULATED"})
        f = self.view()
        self.assertEqual(len(f["history"]),14); self.assertEqual(len(f["subsystems"]),7)
        l7,l8 = f["history"][:2]
        self.assertEqual({b["source_store"] for b in l7["bindings"]},{"unit:operational"})
        self.assertEqual({b["source_store"] for b in l8["bindings"]},{"unit:historical"})
        self.assertEqual(f["governance"][1]["binding_count"],1); self.assertEqual(f["governance"][2]["binding_count"],1)

    def test_reconstruction_deterministic_across_readonly_restart(self):
        self.add("agent","agent_result",{"agent_key":"policy","status":"complete"})
        f = self.view(); watermark = self.store.watermark()
        restarted = GenerationStore(self.root,self.session.identity,self.registry,digest(self.registry),readonly=True)
        cycle = captured_cycle(self.root,self.store.selected(),store=restarted,session=self.session,now=self.clock())
        rebuilt = factory_coverage(restarted.selected(),restarted.selected_events(),cycle,f["phase"])
        self.assertEqual(canonical(f),canonical(rebuilt)); self.assertEqual(watermark,restarted.watermark())

    def test_missing_mismatched_or_resealed_fabricated_projection_fail_closed(self):
        self.view(); self.publish_enabled = False
        p = json.loads((self.root/"projections/current.json").read_bytes())
        p["factory"]["rooms"][0]["case_count"] = 999
        p["factory"] = seal(p["factory"]); atomic(self.root/"projections/current.json",seal(p))
        view = service_response(self.root/"topology.json","/truth-spine/full-session",now=self.clock())[1]
        self.assertEqual(view["readiness"],503); self.assertIsNone(view["factory"])
        self.assertEqual(service_response(self.root/"topology.json","/health/ready",now=self.clock())[0],503)
        with self.assertRaises(ValueError): self.reader.collect(self.clock(),self.store.selected(),self.store.watermark())

    def test_stale_capture_cannot_become_current_coverage(self):
        self.view(); self.clock.advance(901)
        view = service_response(self.root/"topology.json","/truth-spine/full-session",now=self.clock())[1]
        self.assertEqual(view["readiness"],503); self.assertIsNone(view["factory"])

    def test_malformed_cycle_duplicate_event_and_identity_conflict_rejected(self):
        f = self.view(); g = self.store.selected(); events = self.store.selected_events()
        cycle = captured_cycle(self.root,g,store=self.store,session=self.session,now=self.clock())
        for c, rows in [({**cycle,"generation":"f"*64},events),(cycle,events+events[:1])]:
            with self.assertRaises(ValueError): factory_coverage(g,rows,c,f["phase"])
        with self.assertRaises(ValueError): coverage_metadata({"agent_key":"policy","agent_id":"skeptic"},"agent_result")
        self.assertIsNone(coverage_metadata({"agent_key":"not/a/safe/reference"},"agent_result")["agent_id"])

    def test_sanitizer_drops_raw_prose_and_private_configuration(self):
        data = {"agent_key":"macro","status":"complete","secret":"DO_NOT_PROJECT","response_body":"DO_NOT_PROJECT",
                "credential_selector":"DO_NOT_PROJECT","private_path":"DO_NOT_PROJECT","nav":float('inf')}
        cleaned = coverage_metadata(data,"agent_result")
        self.assertNotIn("DO_NOT_PROJECT",canonical(cleaned).decode()); self.assertIsNone(cleaned["paper"])

    def test_source_inputs_byte_identical_after_publisher_and_browser(self):
        before = {s["path"]:Path(s["path"]).read_bytes() for s in self.inputs}
        self.view()
        self.assertEqual(before,{s["path"]:Path(s["path"]).read_bytes() for s in self.inputs})

    def test_real_browser_payload_accepted_by_frontend_validator(self):
        self.add("actual-agent","agent_result",{"agent_key":"policy","status":"complete","classification":"REPLAY"})
        self.view()
        view = service_response(self.root/"topology.json","/truth-spine/full-session",now=self.clock())[1]
        frontend = Path(__file__).resolve().parents[2]/"FRONT END"
        result = subprocess.run(["node","--experimental-strip-types","--input-type=module","-e",
            "import {validSessionView} from './src/truthSpineSessionView.ts';"
            "let input=''; for await (const c of process.stdin) input+=c;"
            "const v=JSON.parse(input); if(!validSessionView(v,Date.parse(v.published_at))) process.exit(1);"],
            cwd=frontend,input=canonical(view),capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode())

    def test_disclosure_bound_preserves_complete_count_and_hash(self):
        for i in range(25): self.add(str(i),"committee_decision",{"status":"complete","classification":"HISTORICAL"})
        r = self.view()["governance"][1]
        self.assertEqual(r["completed_result_count"],25); self.assertEqual(r["binding_count"],25)
        self.assertEqual(len(r["bindings"]),20)
        self.assertNotEqual(r["binding_set_hash"],digest({"bindings":r["bindings"]}))


if __name__ == "__main__": unittest.main()

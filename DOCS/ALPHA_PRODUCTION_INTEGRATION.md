# Alpha production integration: first increment

Baseline: 3e1ff9d040326caff7d4ce76ff6d8108e8a352fb. The accepted
475-request synthetic rehearsal is retained. It does not qualify OS confinement,
provider entitlements, installation, or production execution.

## This increment

`alpha_session_contract.py` validates an independently pinned session contract,
reviewed XNYS calendar document, and ordered 517-symbol universe entirely in
memory. Date, UTC instants, calendar timezone, validity window, parent bindings,
and false authority fields are checked. Short sessions and winter UTC offsets
are supported as inputs; holidays and actual exchange hours are NOT inferred.
An external calendar reviewer must establish the document's semantics before
supplying its independent hash. Synthetic test dates are not calendar evidence.

Successful validation means CONTRACT_VALID_ONLY. It never means production
readiness or permission to execute. The new module is not wired into the
production runner. Existing MONDAY_ONLY, CLI_LIVE_ONLY and
RADAR_NATIVE_ADAPTER_PENDING guards and legacy assertions remain unchanged.
No request schedule is generated here; a short session must not silently inherit
the full-day 475-request schedule.

The dedicated CI job runs offline unit tests on Python 3.14.7. It launches no
fixture, provider request, native qualification, production service or order.
It does not establish an installed immutable runtime identity.

## Second increment: existing Truth Spine binding

`alpha_session_integration.py` reconciles the separately pinned Alpha session
with `truth_spine_session.parse_session`. It requires matching date, opening
and closing times, and independently expected source commit. Closed, shortened
and historical replay sessions cannot use the normal-session 475-request policy.
The existing calendar's bounded year and closure limitations remain in force.

The versioned candidate preserves one separately bound PILOT preflight and 79
six-batch scans (100/100/100/100/100/17). The final scan ends 5m30s after close,
as in the accepted legacy policy, and must fit the 15-minute reconciliation
window. Short-session request counts are deliberately not inferred.

Reconstruction rejects even rehashed plan changes. The offline stage join binds
every stage to the new date, source, candidate and previous accepted stage hash.
Missing stages block completion; even a complete chain is OFFLINE_COMPLETE,
never production GREEN. Real stage semantics remain the responsibility of
existing governance owners. This is a planning/receipt interface, not a running
Factory adapter. No live receipt converter or new supervisor is introduced.

The old production CLI rejects the new candidate schema. Wiring that schema to
execution remains a later separately qualified increment, and every existing
production admission guard remains intact.

## Subsequent implementation and acceptance

1. Connect the reviewed session identity to a versioned schedule/package and
   final receipt, retaining legacy schema behavior. Bind approved source/runtime,
   calendar, universe, account and allowance independently. No date-only patch.
2. Integrate production lifecycle and evidence with the EXISTING Truth Spine
   supervisor and publisher. Test missing, stale, cross-session and synthetic
   receipts. No second supervisor authority or Truth Spine is introduced.
3. Qualify OS confinement on disposable resources under a separately bounded
   native plan. Python audit hooks are not OS confinement proof.
4. Verify real provider feed/account/entitlement/freshness and approved cost
   allowance, then a separately admitted provider preflight. Connected chat
   provider apps are not local account qualification evidence.
5. Verify the selected installed release, immutable Python runtime, ledger path
   binding, generation, fresh supervisor heartbeat and publisher projection.
   The real backend readiness endpoint is /health/ready; a static frontend
   deployment or generic /health result cannot substitute for it.
6. Qualify production installation, noninterference, rollback and actual session
   operation before separate execution authority. All trading authorities stay
   false throughout this source increment.

## Evidence limits

The original full synthetic run proves accelerated logical execution and a
separate minute pacing boundary. It does not prove a full elapsed-time market
session. CI cannot inspect the user's installed Mac services or protected ledger.
Neither a branch merge nor a GREEN unit-test job establishes those local gates.

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

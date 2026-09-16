"""Receipt-only adapter for the reviewed observation topology.

No launcher, signal, provider transport, credential reader or CLI is added.
Truth Spine owns those effects and its current shadow-only admission is intact.
The adapter consumes independently pinned observations/receipts and emits
non-authorizing decisions for a future qualified production effect binding.
"""
from dataclasses import asdict
from functools import wraps
from copy import deepcopy
from pathlib import PurePosixPath

from alpha_observation_lifecycle import verify_topology
from alpha_session_contract import instant, require
from alpha_session_package import sha
from provider_gateway_contract import content_hash, locked_authority, pin, safe_document
from truth_spine_process_identity import ProcessObservation, utc_stamp
from truth_spine_session_supervisor import ROLES

SCOPE = 'OBSERVATION_ADAPTER_VALIDATION_ONLY'


def fail_closed(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception:
            if self.failed is None: self.failed = 'ADAPTER_VALIDATION'
            raise
    return guarded


class ObservationAdapter:
    """Stateful duplicate/ordering gates; supplied facts are never OS proof.

    Each method commits state only after complete verification. The parent must
    preserve consumed reservations on error. No recovery from self-asserted PASS.
    """
    def __init__(self, topology, topology_hash, **inputs):
        self.topology = deepcopy(verify_topology(topology, topology_hash, **inputs))
        self.parent = topology_hash
        self.owners, self.acknowledged, self.tls = {}, set(), None
        self.reservations, self.completions, self.cleanup_results = [], [], {}
        self.sent, self.responses = set(), set()
        self.failed = None
        self.last_time = instant(self.topology['startup_not_before'])

    def clock(self, now, deadline):
        require(self.last_time <= now < instant(deadline), 'ADAPTER_DEADLINE_OR_ROLLBACK')
        self.last_time = now

    def envelope(self, value, expected, stage):
        safe_document(value); pin(value, expected)
        require(type(value) is dict and set(value) == {'schema', 'scope', 'stage', 'topology_parent',
                'generation', 'source_commit', 'authority', 'payload'}, 'ADAPTER_ENVELOPE')
        require(value['schema'] == 'iios-alpha-observation-adapter-evidence-v1' and value['scope'] == SCOPE and
                value['stage'] == stage and value['topology_parent'] == self.parent and
                value['generation'] == self.topology['generation'] and
                value['source_commit'] == self.topology['source_commit'], 'ADAPTER_PARENT')
        require(type(value['authority']) is dict and set(value['authority']) == set(locked_authority()) and
                all(v is False for v in value['authority'].values()), 'ADAPTER_AUTHORITY')
        return value['payload']

    @fail_closed
    def register(self, role, samples, launch, launch_hash, startup, startup_hash, *, now):
        self.clock(now, self.topology['startup_deadline'])
        require(self.failed is None and role in ROLES and role not in self.owners, 'ADAPTER_DUPLICATE_OR_STOPPED')
        expected = self.envelope(launch, launch_hash, 'LAUNCH')
        require(set(expected) == {'role', 'owner_parent', 'observation'} and expected['role'] == role and
                expected['owner_parent'] == self.topology['owners'][role], 'ADAPTER_LAUNCH_PARENT')
        require(type(samples) is tuple and len(samples) == 3 and
                all(type(s) is ProcessObservation for s in samples), 'ADAPTER_THREE_SAMPLES')
        # Same complete OS predicates as the existing Truth Spine inspector;
        # preserve argv[0] too rather than weakening it through normalization.
        baseline = asdict(samples[0]); baseline['argv'] = list(baseline['argv'])
        require(type(baseline['pid']) is int and baseline['pid'] > 0 and
                type(baseline['parent_pid']) is int and baseline['parent_pid'] > 0 and
                baseline['argv'] and baseline['command'] == ' '.join(baseline['argv']) and
                all(type(baseline[k]) is str and PurePosixPath(baseline[k]).is_absolute() and
                    str(PurePosixPath(baseline[k])) == baseline[k] and '..' not in PurePosixPath(baseline[k]).parts
                    for k in ('executable', 'cwd')) and
                sha(baseline['executable_hash']) and
                utc_stamp(baseline['start_time']) == baseline['start_time'], 'ADAPTER_IDENTITY')
        for sample in samples:
            row = asdict(sample); row['argv'] = list(row['argv'])
            require(row == baseline == expected['observation'], 'ADAPTER_UNSTABLE_IDENTITY')
        require(all(v['identity']['pid'] != baseline['pid'] for v in self.owners.values()), 'ADAPTER_PID_REUSE')
        receipt = self.envelope(startup, startup_hash, 'STARTUP')
        require(receipt == {'role': role, 'launch_parent': launch_hash, 'observation': baseline},
                'ADAPTER_STARTUP_MISMATCH')
        self.owners[role] = dict(identity=baseline, launch=launch_hash, startup=startup_hash)

    @fail_closed
    def collect_registration(self, role, inspect, launch, launch_hash, startup, startup_hash, *, clock):
        # Inspection is supplied by the existing Truth Spine owner, never by a
        # command-line option or environment variable. No publication in loop.
        now = clock()
        self.clock(now, self.topology['startup_deadline'])
        samples = tuple(inspect(role) for _ in range(3))
        return self.register(role, samples, launch, launch_hash, startup, startup_hash, now=clock())

    @fail_closed
    def ack(self, role, listener, listener_hash, *, now):
        self.clock(now, self.topology['startup_deadline'])
        require(self.failed is None and role in self.owners and role not in self.acknowledged, 'ADAPTER_ACK_ORDER')
        value = self.envelope(listener, listener_hash, 'LISTENER')
        require(value.get('listener_match') is True and value == {'role': role, 'startup_parent': self.owners[role]['startup'],
                'owner_parent': self.topology['owners'][role], 'pid': self.owners[role]['identity']['pid'],
                'listener_match': True}, 'ADAPTER_LISTENER_MISMATCH')
        self.acknowledged.add(role)
        return self.decision('ACK_ELIGIBLE_ONLY', {'role': role, 'listener_parent': listener_hash})

    @fail_closed
    def verify_tls(self, receipt, expected, *, peer_parent, trust_parent, now):
        self.clock(now, self.topology['startup_deadline'])
        require(self.failed is None and self.acknowledged == set(ROLES) and self.tls is None, 'ADAPTER_TLS_ORDER')
        value = self.envelope(receipt, expected, 'TLS')
        require(sha(peer_parent) and sha(trust_parent) and value.get('verified') is True and value == {
            'peer_parent': peer_parent, 'trust_parent': trust_parent, 'verified': True}, 'ADAPTER_TLS_MISMATCH')
        self.tls = expected

    @fail_closed
    def reserve(self, slot, record, expected, *, now):
        require(self.failed is None and self.tls is not None and type(slot) is int and
                slot == len(self.reservations) == len(self.completions) and slot < 3, 'ADAPTER_RESERVATION_ORDER')
        row = self.topology['rows'][slot]
        self.clock(now, row['dispatch_before'])
        require(instant(row['valid_from']) <= now, 'ADAPTER_EARLY_REQUEST')
        value = self.envelope(record, expected, 'RESERVATION')
        require(value == {'slot': slot, 'row_parent': content_hash(row), 'tls_parent': self.tls,
                          'previous': self.completions[-1] if slot else None}, 'ADAPTER_RESERVATION_BINDING')
        self.reservations.append(expected)

    @fail_closed
    def before_send(self, slot, reservation_hash, *, now):
        require(self.failed is None and type(slot) is int and slot == len(self.completions) and
                len(self.reservations) == slot + 1 and self.reservations[slot] == reservation_hash and
                slot not in self.sent,
                'ADAPTER_UNRESERVED_SEND')
        row = self.topology['rows'][slot]
        self.clock(now, row['dispatch_before'])
        require(instant(row['valid_from']) <= now, 'ADAPTER_EARLY_REQUEST')
        self.sent.add(slot)  # Ambiguity consumes this slot; no second admission.
        # This decision is not transport admission. Existing CLI/gateway guards
        # still reject an offline package, even if every adapter check passes.
        return self.decision('SEND_WINDOW_VALID_ONLY', {'slot': slot, 'reservation_parent': reservation_hash})

    @fail_closed
    def complete(self, slot, receipt, expected, *, response_parent, now):
        require(self.failed is None and type(slot) is int and slot == len(self.completions) and
                len(self.reservations) == slot+1 and slot in self.sent, 'ADAPTER_COMPLETION_ORDER')
        self.clock(now, self.topology['rows'][slot]['expires_at'])
        value = self.envelope(receipt, expected, 'COMPLETION')
        require(sha(response_parent) and response_parent not in self.responses and value == {'slot': slot, 'reservation_parent': self.reservations[slot],
                'response_parent': response_parent, 'coverage': 'COMPLETE', 'freshness': 'VERIFIED'},
                'ADAPTER_RESPONSE_MISMATCH')
        self.completions.append(expected)
        self.responses.add(response_parent)

    def stop(self, category):
        require(category in ('STARTUP', 'IDENTITY', 'DEADLINE', 'AMBIGUOUS_REQUEST', 'PUBLICATION'), 'ADAPTER_CATEGORY')
        if self.failed is None: self.failed = category

    def cleanup(self, inspect, stop_owned, verify_exit):
        """Delegate effects to Truth Spine, independently per registered role.

        No unregistered child may be signalled through this adapter. The launch
        supervisor must retain partial/unregistered children and mark them
        unverified. Each callback remains behind its original native admission.
        """
        for role in reversed(ROLES):
            if role in self.cleanup_results: continue
            if role not in self.owners:
                self.cleanup_results[role] = 'UNREGISTERED'; continue
            try:
                observed = inspect(role)
                require(type(observed) is ProcessObservation, 'ADAPTER_CLEANUP_IDENTITY')
                current = asdict(observed); current['argv'] = list(current['argv'])
                require(current == self.owners[role]['identity'], 'ADAPTER_CLEANUP_IDENTITY')
                # stop_owned MUST reverify again before any signal, as required
                # by OwnedChildren.stop. This inspection cannot replace it.
                outcome = stop_owned(role)
                require(outcome in ('COOPERATIVE', 'VERIFIED_FORCED'), 'ADAPTER_CLEANUP_RESULT')
                require(verify_exit(role) is True, 'ADAPTER_EXIT_UNVERIFIED')
                self.cleanup_results[role] = outcome
            except Exception:
                self.cleanup_results[role] = 'UNVERIFIED'
        return dict(self.cleanup_results)

    def finish(self, reconciliation, expected, *, publication_parent, listener_clear, now):
        self.clock(now, self.topology['finalization_deadline'])
        value = self.envelope(reconciliation, expected, 'RECONCILIATION')
        require(set(value) == {'reservations', 'completions', 'observed_at'} and
                value['reservations'] == self.reservations and value['completions'] == self.completions and
                instant(self.topology['startup_deadline']) <= instant(value['observed_at']) <= now and
                instant(value['observed_at']) <= instant(self.topology['reconciliation_deadline']),
                'ADAPTER_RECONCILIATION')
        require(sha(publication_parent) and type(listener_clear) is tuple and len(listener_clear) == 3 and
                all(v is True for v in listener_clear), 'ADAPTER_FINAL_EVIDENCE')
        complete = (self.failed is None and len(self.completions) == len(self.reservations) == 3 and
                    set(self.cleanup_results) == set(ROLES) and
                    all(v == 'COOPERATIVE' for v in self.cleanup_results.values()))
        return self.decision('ADAPTER_COMPLETE' if complete else 'ADAPTER_BLOCKED',
                             {'reconciliation_parent': expected, 'publication_parent': publication_parent})

    def decision(self, result, details):
        return {'schema': 'iios-alpha-observation-adapter-result-v1', 'scope': SCOPE,
            'topology_parent': self.parent, 'result': result, 'details': details,
            'primary_failure': self.failed, 'cleanup': dict(self.cleanup_results),
            'authority': locked_authority(), 'production_qualified': False,
            'execution_authorized': False, 'native_semantics_verified': False, 'provider_requests': 0}


def observation_health(receipt, expected, *, topology_parent):
    """Receipt-only health projection; cannot replace shadow /health/ready."""
    safe_document(receipt); pin(receipt, expected)
    require(receipt.get('schema') == 'iios-alpha-observation-adapter-result-v1' and
            receipt.get('scope') == SCOPE and sha(topology_parent) and
            receipt.get('topology_parent') == topology_parent and
            receipt.get('production_qualified') is False and receipt.get('execution_authorized') is False and
            receipt.get('native_semantics_verified') is False and
            type(receipt.get('authority')) is dict and set(receipt['authority']) == set(locked_authority()) and
            all(v is False for v in receipt['authority'].values()), 'ADAPTER_HEALTH_SCOPE')
    return {'schema': 'iios-alpha-observation-health-v1', 'scope': SCOPE,
            'receipt_parent': expected, 'topology_parent': topology_parent,
            'adapter_complete': receipt.get('result') == 'ADAPTER_COMPLETE',
            'market_ready': False, 'production_qualified': False, 'authority': locked_authority()}

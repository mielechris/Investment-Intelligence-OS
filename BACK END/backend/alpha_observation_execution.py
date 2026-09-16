"""Connected short-session controller; external effects remain separately admitted.

The offline path uses the actual gateway, journals and receipt verification.
It cannot produce live authority. The existing native owner is component-only:
no production launch is obtained by supplying a different callback or scope.
"""
from copy import deepcopy
import os

from alpha_session_contract import instant, require
from alpha_short_observation import verify_short_plan
from alpha_session_execution import safe_root, publish, read_record, verify_destination
from provider_gateway_contract import content_hash, locked_authority, pin, safe_document
from provider_gateway_live_contract import admit, verify_qualification_receipt, amount
from provider_gateway_qualification import qualify, verify_runtime

SCHEMA = 'iios-alpha-short-gateway-plan-v1'
SCOPE = 'OFFLINE_TEST'

from contextvars import ContextVar
_ACTIVE_OBSERVATION = ContextVar('iios_verified_observation', default=None)


def gateway_plan(plan, expected_plan, inputs, *, root):
    """Reconstruct the exact dated plan; adding roots does not promote its scope."""
    require(type(inputs) is dict and set(inputs) == {'contract', 'calendar', 'universe',
        'spine_session', 'observation', 'expected', 'now', 'source_commit'}, 'SHORT_INPUTS')
    args = deepcopy(inputs); args['now'] = instant(args['now'])
    verified = verify_short_plan(plan, expected_plan, **args)
    from alpha_observation_launch import lexical
    base = lexical(root)
    rows = [{**row, 'root': str(base / row['id'])} for row in verified['rows']]
    return {**deepcopy(verified), 'schema': SCHEMA, 'scope': SCOPE,
        'root': str(base), 'inputs': deepcopy(inputs), 'planning_parent': expected_plan,
        'planning_document': deepcopy(plan), 'rows': rows, 'requires_preflight': True}


def verify_gateway_plan(plan, expected):
    safe_document(plan); pin(plan, expected)
    require(plan['schema'] == SCHEMA and plan['scope'] == SCOPE, 'SHORT_GATEWAY_SCOPE')
    rebuilt = gateway_plan(plan['planning_document'], plan['planning_parent'],
                           plan['inputs'], root=plan['root'])
    require(plan == rebuilt, 'SHORT_GATEWAY_SUBSTITUTION')
    return rebuilt


def window(account, now):
    """Called before both reservation levels and by the final HTTP-send hook."""
    plan = account.get('bulk_plan', {})
    if plan.get('schema') != SCHEMA: return
    row = plan['rows'][account['bulk_slot']]
    at = instant(now)
    require(instant(row['valid_from']) <= at < instant(row['dispatch_before']), 'SHORT_DISPATCH_WINDOW')


def verify_allowance(manifest, account):
    p = account['bulk_plan']; a = account.get('short_allowance', {})
    require(manifest['source_commit'] == p['source_commit'], 'SHORT_SOURCE_BINDING')
    require(p['scope'] == SCOPE, 'SHORT_NATIVE_ADMISSION_PENDING')
    if manifest['mode'] == 'LIVE_QUALIFICATION':
        require_active_observation(manifest, account)
    else:
        require(manifest['mode'] == SCOPE, 'SHORT_NATIVE_ADMISSION_PENDING')
    require(set(a) == {'plan_parent', 'source_commit', 'account_identity', 'maximum_requests',
        'maximum_cost', 'cost_unit', 'expires_at', 'enrichment_requests', 'released'}, 'SHORT_ALLOWANCE')
    require(a['plan_parent'] == account['bulk_plan_parent'] and a['source_commit'] == manifest['source_commit'] and
        a['account_identity'] == account['account_identity'], 'SHORT_ALLOWANCE_PARENT')
    require(type(a['maximum_requests']) is int and a['maximum_requests'] == 3 and
        type(a['enrichment_requests']) is int and a['enrichment_requests'] == 0 and a['released'] is False,
        'SHORT_ALLOWANCE_COUNT')
    from decimal import localcontext
    with localcontext() as context:
        context.prec = 64
        require(a['cost_unit'] == manifest['cost_unit'] and
            amount(a['maximum_cost']) == 3 * amount(manifest['maximum_cost']) <= amount(account['available_unreserved']),
            'SHORT_ALLOWANCE_COST')
    require(a['expires_at'] == p['finalization_deadline'] and
        instant(account['expires_at']) >= instant(p['finalization_deadline']) and
        instant(account['retention']['retain_until']) >= instant(p['finalization_deadline']), 'SHORT_ALLOWANCE_EXPIRY')


def reconcile(fd, plan, requests, expected_requests, receipts):
    require(len(receipts) == 3, 'SHORT_ACCOUNTING')
    expected_names = {'controller-start.json','day.lock'} | {row['id'] for row in plan['rows']}
    expected_names |= {f'{i}.{suffix}.json' for i in range(3) for suffix in ('reserved','complete')}
    require(set(os.listdir(fd)) == expected_names, 'SHORT_JOURNAL_CONTENTS')
    previous = None
    for i, (bundle, pins) in enumerate(zip(requests, expected_requests)):
        row = plan['rows'][i]; m = bundle['manifest']
        reserved = read_record(fd,f'{i}.reserved.json')
        require(reserved == {'plan':content_hash(plan),'slot':i,'source_commit':m['source_commit'],
            'previous':previous}, 'SHORT_FINAL_RESERVATION')
        child = safe_root(row['root'])
        try:
            require(set(os.listdir(child)) == {'batch.lock','batch.json','ALPHA_VANTAGE.reserved.json',
                'ALPHA_VANTAGE.receipt.json'}, 'SHORT_CHILD_CONTENTS')
            request_reservation=read_record(child,'ALPHA_VANTAGE.reserved.json')
            receipt=read_record(child,'ALPHA_VANTAGE.receipt.json',expected_hash=receipts[i])
            verify_qualification_receipt(receipt,receipts[i],parents={**pins,'reservation':content_hash(request_reservation)})
            require(receipt['result']=='OBSERVED' and receipt['request_id']==pins['manifest'] and
                receipt['batch_id']==m['batch_id'] and receipt['root']==row['root'], 'SHORT_FINAL_RECEIPT')
        finally:os.close(child)
        complete=read_record(fd,f'{i}.complete.json')
        require(complete == {'slot':i,'previous':previous,'reservation':content_hash(reserved),
            'receipt':receipts[i],'result':'OBSERVED'}, 'SHORT_FINAL_COMPLETION')
        previous=content_hash(complete)
    return previous


def publish_observation_checkpoint(fd, slot, document, *, publisher=False):
    """Atomic exclusive commit marker for independent concurrent journal readers."""
    from provider_gateway_contract import canonical
    require(type(slot) is int and 0 <= slot < 3, 'OBSERVATION_CHECKPOINT_SLOT')
    require(type(publisher) is bool,'OBSERVATION_CHECKPOINT_ROLE')
    name=('publisher-slot-' if publisher else 'observer-slot-')+str(slot)+'.json';stage=name+'.staging'
    data=canonical(document)
    require(len(data)<=8192,'OBSERVATION_CHECKPOINT_SIZE')
    out=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=fd)
    try:
        with os.fdopen(out,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.link(stage,name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
        os.unlink(stage,dir_fd=fd);os.fsync(fd)
    except BaseException:
        # Preserve failed staging bytes; never reuse an incomplete destination.
        raise
    return content_hash(document)


class OfflineLifecycle:
    """Explicit effect-substitution seam. Never accepted by a live entrypoint.

    Tests implement start, verify_ready and cleanup; native receipts cannot be
    relabeled into this seam. This is not a production launch implementation.
    """
    scope = 'OFFLINE_OBSERVATION_EFFECTS_ONLY'

    def observe_receipt(self, slot, receipt, pins, completion):
        # Optional publication boundary for offline external-effect fixtures.
        pass


def run_observation(plan, expected_plan, requests, expected_requests, *, lifecycle,
                    credential_backend, network, clock, monotonic_ns, wait):
    require(isinstance(lifecycle, OfflineLifecycle) and lifecycle.scope == 'OFFLINE_OBSERVATION_EFFECTS_ONLY',
            'SHORT_NATIVE_ADMISSION_PENDING')
    return _run_observation(plan, expected_plan, requests, expected_requests, lifecycle=lifecycle,
        credential_backend=credential_backend, network=network, clock=clock, monotonic_ns=monotonic_ns, wait=wait,
        mode=SCOPE)


def _run_observation(plan, expected_plan, requests, expected_requests, *, lifecycle,
                     credential_backend, network, clock, monotonic_ns, wait, mode):
    """Shared one-shot journal mechanics; effects remain separately admitted."""
    verify_gateway_plan(plan, expected_plan)
    require(mode == SCOPE or (mode == 'LIVE_QUALIFICATION' and type(_ACTIVE_OBSERVATION.get()) is _active_type()), 'SHORT_NATIVE_ADMISSION_PENDING')
    require(type(requests) is list and len(requests) == 3 and type(expected_requests) is list and
            len(expected_requests) == 3, 'SHORT_REQUEST_COUNT')
    requests = deepcopy(requests); plan = deepcopy(plan)
    for i, (bundle, pins) in enumerate(zip(requests, expected_requests)):
        require(set(bundle) == {'manifest', 'account', 'runtime'}, 'SHORT_REQUEST_DOCUMENTS')
        m,a,r = (bundle[k] for k in ('manifest','account','runtime'))
        require(m['mode'] == mode and a['bulk_plan'] == plan and
            a['bulk_slot'] == i and a['bulk_plan_parent'] == expected_plan, 'SHORT_REQUEST_BINDING')
        # Static preflight at each intended slot; actual-time rechecks remain in gateway.
        admission = admit(m,a,r,expected=pins,now=m['valid_from']); verify_runtime(admission)
    shared_accounts=[{k:v for k,v in b['account'].items() if k!='bulk_slot'} for b in requests]
    require(all(v==shared_accounts[0] for v in shared_accounts), 'SHORT_ACCOUNT_SUBSTITUTION')
    require(len({b['manifest']['root'] for b in requests}) == 3 and
        len({b['runtime']['source_commit'] for b in requests}) == 1 and
        len({content_hash(b['runtime']) for b in requests}) == 1 and
        len({b['account']['account_identity'] for b in requests}) == 1, 'SHORT_SESSION_IDENTITY')
    previous = None; receipts = []; primary = None; cleanup = None
    stage = 'STARTUP'; last_time = instant(clock()); last_ns = monotonic_ns()
    require(type(last_ns) is int and 0 <= last_ns < 2**63, 'SHORT_MONOTONIC')
    origin_time, origin_ns = last_time, last_ns
    def check(deadline):
        nonlocal last_time,last_ns
        now = instant(clock()); ns = monotonic_ns()
        require(type(ns) is int and last_ns <= ns < 2**63 and last_time <= now < instant(deadline), 'SHORT_CLOCK')
        # Both clocks constrain the same originally bound interval; neither resets a budget.
        delta=instant(deadline)-origin_time
        bound_ns=(delta.days*86400+delta.seconds)*1_000_000_000+delta.microseconds*1000
        require(ns-origin_ns < bound_ns, 'SHORT_MONOTONIC_DEADLINE')
        last_time,last_ns = now,ns
        return now
    fd = safe_root(plan['root'])
    try:
        publish(fd, 'controller-start.json', {'scope': mode, 'plan_parent': expected_plan,
            'requests': expected_requests, 'authority': locked_authority()})
    except BaseException:
        os.close(fd)
        raise
    try:
        check(plan['startup_deadline']); lifecycle.start()
        require(lifecycle.verify_ready() is True, 'SHORT_STARTUP_UNVERIFIED')
        check(plan['startup_deadline'])
        for slot, (bundle, pins) in enumerate(zip(requests, expected_requests)):
            stage = 'WAIT'
            row=plan['rows'][slot]
            if instant(clock()) < instant(row['valid_from']): wait(row['valid_from'])
            check(row['dispatch_before'])
            require(lifecycle.verify_ready() is True, 'SHORT_OWNERSHIP_UNVERIFIED')
            stage = 'GATEWAY'
            receipt = qualify(**bundle, expected=pins, credential_backend=credential_backend,
                network=network, clock=clock if mode == SCOPE else None, expected_bulk_previous=previous)
            child = safe_root(row['root'])
            try:
                reservation=read_record(child,'ALPHA_VANTAGE.reserved.json')
                verify_qualification_receipt(receipt,content_hash(receipt),
                    parents={**pins,'reservation':content_hash(reservation)})
                retained=read_record(child,'ALPHA_VANTAGE.receipt.json',expected_hash=content_hash(receipt))
                require(retained == receipt, 'SHORT_RETAINED_RECEIPT')
            finally: os.close(child)
            receipts.append(content_hash(receipt))
            completion=read_record(fd,f'{slot}.complete.json')
            reserved=read_record(fd,f'{slot}.reserved.json')
            require(completion == {'slot':slot,'previous':previous,'reservation':content_hash(reserved),
                'receipt':receipts[-1],'result':receipt['result']}, 'SHORT_COMPLETION')
            previous=content_hash(completion)
            require(receipt['result']=='OBSERVED' and receipt['scope']==mode and
                receipt['bulk_checks']['coverage']=='COMPLETE' and
                receipt['bulk_checks']['freshness']=='WITHIN_AGE_BOUND', 'SHORT_PROVIDER_STOP')
            stage='PUBLICATION'
            lifecycle.observe_receipt(slot,receipt,pins,completion)
            check(row['expires_at'])
        stage='RECONCILIATION'; check(plan['reconciliation_deadline'])
        # The gateway rechecks the complete journal at every continuation; the
        # final tail is independently bound above, with no response substitution.
        require(reconcile(fd,plan,requests,expected_requests,receipts)==previous, 'SHORT_FINAL_PARENT')
    except BaseException:
        primary=stage  # Fixed local stage only; no raw error or provider text.
    finally:
        try: cleanup=lifecycle.cleanup()
        except Exception: cleanup={'verified':False}
        cleanup_ok=(type(cleanup) is dict and cleanup=={'verified':True,'cooperative':True,
            'roles':['scheduler','publisher','backend'],'listener_owner_reconciled':True,'port_clear':[True]*3})
        try:
            check(plan['finalization_deadline']); verify_destination(fd,plan['root'])
            if primary is None:
                try: require(reconcile(fd,plan,requests,expected_requests,receipts)==previous, 'SHORT_FINAL_PARENT')
                except Exception: primary='FINAL_RECONCILIATION'
            report={'schema':'iios-alpha-connected-observation-result-v1','scope':mode,
                'plan_parent':expected_plan,'result':('OFFLINE_COMPLETE' if mode == SCOPE else 'OBSERVATION_COMPLETE') if primary is None and cleanup_ok else 'BLOCKED',
                'primary_failure':primary,'cleanup_verified':cleanup_ok,'response_parents':receipts,
                'completion_parent':previous,'authority':locked_authority(), 'production_qualified':False,
                'execution_authorized':False,'provider_requests':0 if mode == SCOPE else None,
                'request_count_basis':'OFFLINE_NO_PROVIDER' if mode == SCOPE else 'VERIFY_RESPONSE_AND_RESERVATION_JOURNALS',
                'offline_responses':len(receipts) if mode == SCOPE else 0,
                'complete_accounting':primary is None and len(receipts)==3}
            publish(fd,'controller-final.json',report)
        finally: os.close(fd)
    return report


def _active_type():
    from alpha_observation_lifecycle import ObservationExecution
    return ObservationExecution


def require_active_observation(manifest, account):
    """Additional gate to the existing live gateway, never an alternative to it."""
    from datetime import datetime, timezone
    from alpha_observation_lifecycle import verify_observation_execution
    cap = _ACTIVE_OBSERVATION.get()
    require(type(cap) is _active_type(), 'SHORT_NATIVE_ADMISSION_PENDING')
    verify_observation_execution(cap, cap.identity, now=datetime.now(timezone.utc))
    d = cap.document(); b = d['preflight']; a = b['account']
    require(manifest['source_commit'] == d['source_commit'] and
        manifest['provider'] == a['provider'] and manifest['endpoint'] == a['endpoint'] and
        manifest['symbols'] == a['symbols'] and manifest['feed'] == a['feed'], 'SHORT_LIVE_ROUTE')
    require(account['account_identity'] == a['account_identity'] and account['tier_identity'] == a['tier_identity'],
            'SHORT_LIVE_ACCOUNT')
    for key in ('cost_unit','maximum_request_cost','available_unreserved','rate_per_minute',
                'overage_enabled','automatic_top_up','ambiguous_billing'):
        require(account[key] == a[key], 'SHORT_LIVE_ACCOUNT_POLICY')
    require({k:v['evidence_sha256'] for k,v in account['proofs'].items()} == a['claim_parents'],
            'SHORT_LIVE_ACCOUNT_PROOFS')
    require(account['bulk_plan']['planning_parent'] == b['candidate']['parents']['plan'] and
        account['bulk_plan']['root'] == d['roots']['output'] + '/requests' and
        account['short_allowance']['maximum_cost'] == b['allowance']['maximum_cost'], 'SHORT_LIVE_PLAN')
    return cap


def run_admitted_observation(capability, expected, plan, plan_parent, requests, request_pins, *, lifecycle):
    """Fixed native effects only; no test/network/credential callback parameters."""
    from datetime import datetime, timezone
    import time
    from alpha_observation_lifecycle import verify_observation_execution
    from provider_gateway_credentials import MacKeychain
    from provider_gateway_transport import NativeHTTPS
    from truth_spine_full_day_runner import ObservationLifecycle
    require(type(lifecycle) is ObservationLifecycle and lifecycle.capability.identity == expected,
            'SHORT_TRUTH_SPINE_OWNER_REQUIRED')
    verify_observation_execution(capability, expected, now=datetime.now(timezone.utc))
    require(_ACTIVE_OBSERVATION.get() is None, 'SHORT_DUPLICATE_EXECUTION_CONTEXT')
    def clock(): return datetime.now(timezone.utc).isoformat()
    def wait(at):
        delay = (instant(at) - instant(clock())).total_seconds()
        require(0 <= delay <= 60, 'SHORT_WAIT_BOUND')
        end = time.monotonic_ns() + int(delay * 1_000_000_000)
        while time.monotonic_ns() < end:
            lifecycle.verify_ready()
            time.sleep(min(.1, max(0, (end-time.monotonic_ns())/1_000_000_000)))
    token = _ACTIVE_OBSERVATION.set(capability)
    try:
        return _run_observation(plan, plan_parent, requests, request_pins, lifecycle=lifecycle,
            credential_backend=MacKeychain(), network=NativeHTTPS(), clock=clock,
            monotonic_ns=time.monotonic_ns, wait=wait, mode='LIVE_QUALIFICATION')
    finally:
        _ACTIVE_OBSERVATION.reset(token)

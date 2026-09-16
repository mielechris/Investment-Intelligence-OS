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
    require(manifest['mode'] == SCOPE and p['scope'] == SCOPE, 'SHORT_NATIVE_ADMISSION_PENDING')
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


class OfflineLifecycle:
    """Explicit effect-substitution seam. Never accepted by a live entrypoint.

    Tests implement start, verify_ready and cleanup; native receipts cannot be
    relabeled into this seam. This is not a production launch implementation.
    """
    scope = 'OFFLINE_OBSERVATION_EFFECTS_ONLY'


def run_observation(plan, expected_plan, requests, expected_requests, *, lifecycle,
                    credential_backend, network, clock, monotonic_ns, wait):
    """One-shot connected offline execution with real journal/publication code.

    The unimplemented production launch/ACK binding is a named hard gate, not a
    callback-shaped bypass. No production/synthetic acceptance can arise here.
    """
    verify_gateway_plan(plan, expected_plan)
    require(isinstance(lifecycle, OfflineLifecycle) and lifecycle.scope == 'OFFLINE_OBSERVATION_EFFECTS_ONLY',
            'SHORT_NATIVE_ADMISSION_PENDING')
    require(type(requests) is list and len(requests) == 3 and type(expected_requests) is list and
            len(expected_requests) == 3, 'SHORT_REQUEST_COUNT')
    requests = deepcopy(requests); plan = deepcopy(plan)
    for i, (bundle, pins) in enumerate(zip(requests, expected_requests)):
        require(set(bundle) == {'manifest', 'account', 'runtime'}, 'SHORT_REQUEST_DOCUMENTS')
        m,a,r = (bundle[k] for k in ('manifest','account','runtime'))
        require(m['mode'] == SCOPE and a['bulk_plan'] == plan and
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
        publish(fd, 'controller-start.json', {'scope': SCOPE, 'plan_parent': expected_plan,
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
                network=network, clock=clock, expected_bulk_previous=previous)
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
            require(receipt['result']=='OBSERVED' and receipt['scope']==SCOPE and
                receipt['bulk_checks']['coverage']=='COMPLETE' and
                receipt['bulk_checks']['freshness']=='WITHIN_AGE_BOUND', 'SHORT_PROVIDER_STOP')
            check(row['expires_at'])
        stage='RECONCILIATION'; check(plan['reconciliation_deadline'])
        # The gateway rechecks the complete journal at every continuation; the
        # final tail is independently bound above, with no response substitution.
        require(reconcile(fd,plan,requests,expected_requests,receipts)==previous, 'SHORT_FINAL_PARENT')
    except Exception:
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
            report={'schema':'iios-alpha-connected-observation-result-v1','scope':SCOPE,
                'plan_parent':expected_plan,'result':'OFFLINE_COMPLETE' if primary is None and cleanup_ok else 'BLOCKED',
                'primary_failure':primary,'cleanup_verified':cleanup_ok,'response_parents':receipts,
                'completion_parent':previous,'authority':locked_authority(), 'production_qualified':False,
                'execution_authorized':False,'provider_requests':0,'offline_responses':len(receipts),
                'complete_accounting':primary is None and len(receipts)==3}
            publish(fd,'controller-final.json',report)
        finally: os.close(fd)
    return report

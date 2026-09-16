"""Read-only candidate preflight CLI. Never emits production READY or launches.

Run on the selected host with independently approved roots and bundle pins.
There are no default paths, secret discovery, clock override or execution mode.
"""
import argparse
from datetime import datetime, timezone
import json
import sys

from alpha_session_evidence import verify_files, json_document, verify_candidate_evidence
from alpha_session_contract import require
from provider_gateway_contract import locked_authority

FIELDS = {'schema','candidate','candidate_hash','plan','account','runtime','allowance',
          'runtime_manifest','claims_manifest','claims_manifest_hash','package_inputs'}
INPUT_FIELDS = {'input_pins','contract','calendar','universe','spine_session','expected','source_commit'}
PENDING = ['SEMANTIC_ACCOUNT_REVIEW','PLATFORM_AND_RUNNING_INTERPRETER','OS_CONFINEMENT',
           'LIVE_PREFLIGHT','PRODUCTION_LIFECYCLE','EXECUTION_AUTHORITY']


def report(result, *, failure=None, verified=None):
    return {'schema':'iios-alpha-readonly-preflight-v1','status':'BLOCKED',
            'candidate_evidence':result,'failure':failure,
            'package_parent':None if verified is None else verified['package_parent'],
            'pending':list(PENDING),'authority':locked_authority(),
            'production_qualified':False,'execution_authorized':False,
            'provider_requests':0,'process_launches':0}


def evaluate_bundle(bundle, *, now, approved_runtime_root, approved_claims_root):
    require(type(bundle) is dict and set(bundle)==FIELDS and bundle['schema'] in
            ('iios-alpha-preflight-input-v1','iios-alpha-short-preflight-input-v1'),'PREFLIGHT_BUNDLE_SCHEMA')
    from alpha_short_observation import PLAN_SCHEMA as SHORT_SCHEMA
    short=bundle['schema']=='iios-alpha-short-preflight-input-v1'
    require(type(bundle['plan']) is dict and
            (bundle['plan'].get('schema')==SHORT_SCHEMA) is short,'PREFLIGHT_MODE_BINDING')
    inputs=bundle['package_inputs']
    fields=INPUT_FIELDS|{'observation'} if short else INPUT_FIELDS
    require(type(inputs) is dict and set(inputs)==fields,'PREFLIGHT_INPUT_SCHEMA')
    verified=verify_candidate_evidence(bundle['candidate'],bundle['candidate_hash'],bundle['plan'],
        bundle['account'],bundle['runtime'],bundle['allowance'],runtime_manifest=bundle['runtime_manifest'],
        claims_manifest=bundle['claims_manifest'],claims_manifest_hash=bundle['claims_manifest_hash'],
        approved_runtime_root=approved_runtime_root,approved_claims_root=approved_claims_root,now=now,**inputs)
    return report('FILES_AND_BINDINGS_VERIFIED_ONLY',verified=verified)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',required=True)
    parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--expected-bytes',required=True,type=int)
    parser.add_argument('--approved-runtime-root',required=True)
    parser.add_argument('--approved-claims-root',required=True)
    args=parser.parse_args(argv)
    try:
        require(0<args.expected_bytes<=4*1024*1024,'PREFLIGHT_BUNDLE_SIZE')
        rows=[{'path':'admission-input.json','size':args.expected_bytes,'mode':0o400,
               'sha256':args.expected_sha256}]
        bodies=verify_files(args.input_root,rows,approved_root=args.input_root,retain=('admission-input.json',))
        bundle=json_document(bodies['admission-input.json'])
        value=evaluate_bundle(bundle,now=datetime.now(timezone.utc),
                              approved_runtime_root=args.approved_runtime_root,
                              approved_claims_root=args.approved_claims_root)
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as error:
        # Fixed categories only: never stringify paths, exception messages or data.
        category=('INPUT_UNAVAILABLE' if isinstance(error,FileNotFoundError) else
                  'ACCESS_DENIED' if isinstance(error,PermissionError) else
                  'FILESYSTEM_CHECK_FAILED' if isinstance(error,OSError) else 'INPUT_OR_EVIDENCE_REJECTED')
        value=report('FAILED',failure=category)
    print(json.dumps(value,sort_keys=True))
    # Exit 0 would be easy to mistake for session admission. Even successful
    # file validation returns a distinct BLOCKED code until live gates exist.
    return 2 if value['candidate_evidence']=='FILES_AND_BINDINGS_VERIFIED_ONLY' else 1


if __name__=='__main__': sys.exit(main())

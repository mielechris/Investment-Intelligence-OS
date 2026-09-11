"""Synthetic installation and mocked transport tests; no native processes or network."""
import ast
import hashlib
import json
import os
import platform
import plistlib
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from . import collection_runtime as runtime
from .collection_plan import SessionPlan, canonical, digest
from .test_collection_session import PLAN, OPEN, SPEC_SHA256, request_plan
from .collection_service import main
from .collection_session import Journal
from .collection_transport import CollectionBoundary
from .test_collection_session import test_root


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.base=test_root();self.payload=self.base/'payload';self.payload.mkdir(mode=0o700)
        (self.payload/'expansion_wing').mkdir(mode=0o700)
        self.root=self.base/'session';self.executable=self.base/'python';self.executable.write_bytes(b'SYNTHETIC_INTERPRETER')
        self.files={}
        for name in runtime.FILES:
            data=('synthetic '+name).encode();(self.payload/name).write_bytes(data)
            self.files[name]={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
        self.doc={'schema':'fd-collection-release-v2','session':'2026-09-11','spec_sha256':SPEC_SHA256,
            'installed_root':str(self.root),'source_commit':'1'*40,'label':PLAN.label,
            'files':self.files,'source_inventory_sha256':'b'*64,
            'runtime':{'executable':str(self.executable),'sha256':hashlib.sha256(self.executable.read_bytes()).hexdigest(),
                       'version':platform.python_version(),'architecture':platform.machine()}}
        self.manifest=self.base/'manifest.json';self.refresh_manifest()
        self.patch=patch.object(sys,'executable',str(self.executable));self.patch.start();self.addCleanup(self.patch.stop)

    def refresh_manifest(self):
        self.doc['source_inventory_sha256']=digest({'source_commit':self.doc['source_commit'],'files':{name:record for name,record in self.doc['files'].items() if name!='cacert.pem'}})
        self.manifest.write_bytes(canonical(self.doc));self.hash=hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def install(self):
        return runtime.install_disabled(self.root,self.payload,self.manifest,self.hash,'1'*40, plan=PLAN)

    def test_disabled_install_exact_pinned_copy_no_authority(self):
        self.assertEqual(self.install(),'INSTALLED_DISABLED_ZERO_RELEASED_CREDITS')
        self.assertFalse(list((self.root/'receipts').iterdir()))
        self.assertFalse(list((self.root/'inputs').iterdir()))
        runtime.validate_installed(self.root,self.hash,'1'*40, plan=PLAN)
        for name in runtime.FILES:self.assertEqual((self.payload/name).read_bytes(),(self.root/'release'/name).read_bytes())

    def test_existing_destination_rejected_preserved(self):
        self.install();before=(self.root/'release-manifest.json').read_bytes()
        with self.assertRaises(ValueError):self.install()
        self.assertEqual((self.root/'release-manifest.json').read_bytes(),before)

    def test_wrong_commit_or_manifest_pin_rejected(self):
        for commit,pin in [('2'*40,self.hash),('1'*40,'f'*64)]:
            with self.assertRaises(ValueError):runtime.install_disabled(self.root,self.payload,self.manifest,pin,commit, plan=PLAN)
        self.assertFalse(self.root.exists())

    def test_wrong_installed_root_rejected(self):
        self.doc['installed_root']=str(self.base/'other');self.refresh_manifest()
        with self.assertRaises(ValueError):self.install()

    def test_wrong_session_or_legacy_release_rejected(self):
        for field, value in [('session', '2026-09-14'), ('schema', 'fd-collection-release-v1'),
                             ('label', SessionPlan('2026-09-14').label)]:
            old = self.doc[field]
            self.doc[field] = value
            self.refresh_manifest()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.install()
            self.doc[field] = old
        self.refresh_manifest()
        with self.assertRaises(ValueError):
            runtime.install_disabled(self.root, self.payload, self.manifest, self.hash, '1'*40,
                                     plan=SessionPlan('2026-09-14'))
        self.assertFalse(self.root.exists())

    def test_missing_extra_or_traversal_inventory_rejected(self):
        for key in ('extra.py','../escape.py','/absolute.py'):
            with self.subTest(key=key):
                old=self.doc['files'];self.doc['files']=old|{key:{'size':1,'sha256':'a'*64}};self.refresh_manifest()
                with self.assertRaises(ValueError):self.install()
                self.doc['files']=old

    def test_extra_payload_file_rejected(self):
        (self.payload/'extra').write_bytes(b'extra')
        with self.assertRaises(ValueError):self.install()

    def test_substituted_payload_rejected(self):
        (self.payload/'cacert.pem').write_bytes(b'substitute')
        with self.assertRaises(ValueError):self.install()

    def test_symlink_payload_rejected(self):
        (self.payload/'extra').symlink_to(self.executable)
        with self.assertRaises(ValueError):self.install()

    def test_hardlink_input_rejected(self):
        alias=self.base/'alias';os.link(self.payload/'cacert.pem',alias)
        with self.assertRaises(ValueError):self.install()

    def test_wrong_runtime_interpreter_rejected(self):
        with patch.object(sys,'executable',str(self.base/'other')):
            with self.assertRaises(ValueError):self.install()

    def test_wrong_runtime_hash_version_architecture(self):
        for key,value in [('sha256','c'*64),('version','0.0'),('architecture','other')]:
            old=self.doc['runtime'][key];self.doc['runtime'][key]=value;self.refresh_manifest()
            with self.subTest(key=key),self.assertRaises(ValueError):self.install()
            self.doc['runtime'][key]=old

    def test_runtime_cannot_execute_from_mutable_checkout(self):
        self.install()
        with self.assertRaisesRegex(ValueError,'MUTABLE_CHECKOUT'):
            runtime.validate_installed(self.root,self.hash,'1'*40,executing=True, plan=PLAN)

    def test_root_identity_substitution_rejected(self):
        self.install();path=self.root/'state/ownership.json';value=json.loads(path.read_text());value['inode']+=1
        path.write_bytes(canonical(value))
        with self.assertRaises(ValueError):runtime.validate_installed(self.root,self.hash,'1'*40, plan=PLAN)

    def test_extra_account_input_rejected(self):
        self.install();(self.root/'inputs/unknown.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):runtime.validate_installed(self.root,self.hash,'1'*40, plan=PLAN)

    def test_unrepaired_source_commit_rejected(self):
        self.doc['source_commit']='455d31752a0fc73c73625f5757d0f4e87683a6ed';self.refresh_manifest()
        with self.assertRaisesRegex(ValueError,'UNREPAIRED_SOURCE'):
            runtime.install_disabled(self.root,self.payload,self.manifest,self.hash,self.doc['source_commit'], plan=PLAN)

    def test_source_inventory_parent_mismatch_rejected(self):
        self.doc['source_inventory_sha256']='c'*64
        self.manifest.write_bytes(canonical(self.doc));self.hash=hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'SOURCE_INVENTORY_BINDING'):
            self.install()

    def test_second_supervisor_lock_rejected(self):
        self.install();a=Journal(self.root,self.hash, plan=PLAN);b=Journal(self.root,self.hash, plan=PLAN)
        with a.lock('supervisor.lock'):
            with self.assertRaises(BlockingIOError):
                with b.lock('supervisor.lock'):pass

    def test_duplicate_service_start_does_not_append_failure(self):
        self.install()
        account_hash='c'*64;authority_hash='d'*64
        command=['supervise','--session-date',PLAN.session,'--root',str(self.root),'--release-sha256',self.hash,
                 '--source-commit','1'*40,'--account-sha256',account_hash,
                 '--authority-sha256',authority_hash]
        journal=Journal(self.root,self.hash, plan=PLAN)
        with journal.lock('supervisor.lock'), \
             patch('expansion_wing.collection_service.Journal',return_value=journal), \
             patch('expansion_wing.collection_service.validate_installed',return_value=self.doc), \
             patch('expansion_wing.collection_service.documents',return_value=({},{})):
            self.assertEqual(main(command),75)
        self.assertEqual(journal.events(),[])

    def test_plist_explicit_root_pins_no_restart_loop(self):
        value=plistlib.loads(runtime.startup_plist(self.root,self.hash,'1'*40,str(self.executable),'c'*64,'d'*64, plan=PLAN))
        self.assertFalse(value['KeepAlive']);self.assertTrue(value['RunAtLoad'])
        self.assertIn(self.hash,value['ProgramArguments']);self.assertIn('supervise',value['ProgramArguments'])
        self.assertEqual(value['WorkingDirectory'],str(self.root/'release'))
        self.assertNotIn('PYTHONPATH',value['EnvironmentVariables'])

    def test_validation_cli_no_credentials_or_services(self):
        self.install()
        with patch('expansion_wing.collection_service.production_boundary',side_effect=AssertionError('credentials')), \
             patch('subprocess.run',side_effect=AssertionError('process')), \
             patch('socket.socket',side_effect=AssertionError('network')):
            self.assertEqual(main(['validate','--session-date',PLAN.session,'--root',str(self.root),'--release-sha256',self.hash,'--source-commit','1'*40]),0)

    def test_failure_cli_returns_failure_not_success(self):
        self.assertEqual(main(['validate','--session-date',PLAN.session,'--root',str(self.root),'--release-sha256',self.hash,'--source-commit','1'*40]),78)

    def test_collection_import_closure_has_no_ledger_or_full_factory_service(self):
        directory=Path(__file__).parent
        prohibited={'ledger','sqlite3','deployment_contract','unattended_tuesday_service','operational_market_executor_service'}
        for name in runtime.MODULES:
            tree=ast.parse((directory/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):names=[x.name for x in node.names]
                elif isinstance(node,ast.ImportFrom):names=[node.module or '']
                else:continue
                self.assertFalse(prohibited & {x.split('.')[-1] for x in names},(name,names))


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.now=OPEN;self.credentials=Mock();self.credentials.retrieve.return_value=b'SYNTHETIC_NOT_A_CREDENTIAL'
        self.transport=Mock();self.transport.trust_readiness.return_value='READY'
        self.connection=Mock();self.response=Mock();self.response.status=200
        self.response.getheader.side_effect=lambda name: 'application/json' if name=='Content-Type' else None
        self.response.read.return_value=b'{}';self.connection.getresponse.return_value=self.response
        self.factory=Mock(return_value=self.connection);self.alarm=Mock(side_effect=lambda seconds:nullcontext())
        self.stopped=Mock(return_value=False)
        self.boundary=CollectionBoundary(self.credentials,self.transport,stopped=self.stopped,clock=lambda:self.now,
                                        alarm=self.alarm,connection_factory=self.factory, plan=PLAN)

    def test_exact_history_query_and_mock_credentials(self):
        row=request_plan()[10];self.boundary.request(row,OPEN.replace(hour=14))
        args,kwargs=self.connection.request.call_args
        self.assertEqual(args,('GET','/prices?ticker=MU&interval=day&start_date=2026-09-10&end_date=2026-09-11'))
        self.assertEqual(set(kwargs['headers']),{'X-API-KEY'})
        self.assertEqual(self.factory.call_args.args[:2],('api.financialdatasets.ai',443))
        self.alarm.assert_called_once_with(15.0);self.connection.close.assert_called_once()

    def test_unknown_row_rejected_before_credentials(self):
        row=request_plan()[0];row['host']='other.example'
        with self.assertRaises(ValueError):self.boundary.request(row,OPEN.replace(hour=14))
        self.credentials.retrieve.assert_not_called();self.factory.assert_not_called()

    def test_expired_or_stopped_no_credentials(self):
        with self.assertRaises(ValueError):self.boundary.request(request_plan()[0],OPEN)
        self.stopped.return_value=True
        with self.assertRaises(ValueError):self.boundary.request(request_plan()[0],OPEN.replace(hour=14))
        self.credentials.retrieve.assert_not_called()

    def test_trust_failure_before_credentials(self):
        self.transport.trust_readiness.return_value='BAD'
        with self.assertRaises(ValueError):self.boundary.request(request_plan()[0],OPEN.replace(hour=14))
        self.credentials.retrieve.assert_not_called()

    def test_expiry_during_mock_credential_retrieval_no_http(self):
        deadline=OPEN.replace(hour=14)
        def expired():self.now=deadline;return b'SYNTHETIC'
        self.credentials.retrieve.side_effect=expired
        with self.assertRaises(ValueError):self.boundary.request(request_plan()[0],deadline)
        self.factory.assert_not_called()

    def test_redirect_never_followed(self):
        self.response.status=302
        with self.assertRaises(ValueError):self.boundary.request(request_plan()[0],OPEN.replace(hour=14))
        self.factory.assert_called_once();self.connection.close.assert_called_once()

    def test_timeout_no_retry_and_close(self):
        self.connection.getresponse.side_effect=TimeoutError('mock timeout')
        with self.assertRaises(TimeoutError):self.boundary.request(request_plan()[0],OPEN.replace(hour=14))
        self.factory.assert_called_once();self.connection.close.assert_called_once()

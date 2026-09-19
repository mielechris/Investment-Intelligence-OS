import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

verify=module('control_verify',ROOT/'native-control/scripts/verify_source.py')
collect=module('control_collect',ROOT/'native-control/scripts/collect_evidence.py')
seal=module('control_seal',ROOT/'native-control/scripts/seal_source.py')

class Result:
    def __init__(self,value=b''):self.stdout=value;self.stderr=b'';self.returncode=0

class ControlTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def context(self):
        return {'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REPOSITORY':'mielechris/IIOS-Native-Control',
                'GITHUB_REF':'refs/heads/main','GITHUB_REF_TYPE':'branch','GITHUB_HEAD_REF':'','GITHUB_BASE_REF':'','INPUT_NATIVE':'true'}
    def test_standalone_verifier_accepts_only_exact_complete_inventory(self):
        source=self.root/'source';source.mkdir();item=source/'x.py';item.write_bytes(b'x=1\n');item.chmod(0o644)
        rows=[{'path':'x.py','bytes':4,'mode':0o644,'sha256':hashlib.sha256(b'x=1\n').hexdigest()}]
        binding={'schema':1,'repository':'mielechris/Investment-Intelligence-OS','commit':'a'*40,
                 'inventory':rows,'inventory_sha256':verify.digest(rows),'authority':verify.AUTHORITY}
        pin=self.root/'binding.json';pin.write_text(json.dumps(binding));receipt=self.root/'receipt.json'
        def command(args,root):
            values={('status','--porcelain=v1','--untracked-files=all'):b'',('rev-parse','HEAD'):(b'a'*40)+b'\n',
                    ('rev-parse','--abbrev-ref','HEAD'):b'HEAD\n',('remote','get-url','origin'):b'https://github.com/mielechris/Investment-Intelligence-OS.git\n',
                    ('ls-files','--stage','-z'):b'100644 '+b'b'*40+b' 0\tx.py\0'}
            return Result(values[tuple(args)])
        with patch.dict(os.environ,self.context(),clear=True),patch.object(verify,'command',side_effect=command):
            value=verify.verify(pin,source,receipt)
        self.assertTrue(value['verified']);self.assertEqual(value['authority'],verify.AUTHORITY)
        binding['inventory'][0]['bytes']=5;pin.write_text(json.dumps(binding));receipt.unlink()
        with patch.dict(os.environ,self.context(),clear=True),patch.object(verify,'command',side_effect=command):
            with self.assertRaisesRegex(ValueError,'INVENTORY'):verify.verify(pin,source,receipt)
        binding['inventory'][0]['bytes']=4;pin.write_text(json.dumps(binding));(source/'ignored.tmp').write_text('extra')
        with patch.dict(os.environ,self.context(),clear=True),patch.object(verify,'command',side_effect=command):
            with self.assertRaisesRegex(ValueError,'EXTRA_FILE'):verify.verify(pin,source,receipt)
    def test_untrusted_context_rejected_before_git(self):
        binding=self.root/'binding';binding.write_text(json.dumps({'schema':1,'repository':'mielechris/Investment-Intelligence-OS','commit':'a'*40,'inventory':[],'inventory_sha256':'b'*64,'authority':verify.AUTHORITY}))
        with patch.dict(os.environ,dict(self.context(),GITHUB_REF='refs/tags/v1'),clear=True),patch.object(verify,'command',side_effect=AssertionError('git called')):
            with self.assertRaisesRegex(ValueError,'CONTROL_CONTEXT'):verify.verify(binding,self.root,self.root/'receipt')
    def test_evidence_scanner_rejects_machine_paths_tokens_and_ids(self):
        for value in ({'runner_name':'selected'},{'uid':501},{'path':'/Users/person/Library/IIOS'},
                      {'value':'ghp_'+'a'*30},{'value':'Bearer credential'},{'token=secret':False}):
            with self.assertRaises(ValueError):collect.scan(value)
    def test_source_sealer_rejects_symlinks_and_makes_tree_owner_read_only(self):
        source=self.root/'source';source.mkdir();script=source/'run';script.write_text('x');script.chmod(0o755)
        data=source/'data';data.write_text('x');data.chmod(0o644)
        with patch('sys.argv',['seal_source.py','--source',str(source)]):seal.main()
        self.assertEqual(source.stat().st_mode&0o777,0o500)
        self.assertEqual(script.stat().st_mode&0o777,0o500);self.assertEqual(data.stat().st_mode&0o777,0o400)
    def test_control_workflow_is_manual_and_environment_gated(self):
        text=(ROOT/'native-control/.github/workflows/native-qualification.yml.in').read_text()
        self.assertIn('on:\n  workflow_dispatch:',text);self.assertNotIn('\n  pull_request:',text);self.assertNotIn('\n  push:',text)
        for value in ('environment: iios-native-qualification','runs-on: [self-hosted, macOS, ARM64, iios-selected-mac]',
                      'test "$NATIVE" = true','persist-credentials: false','@@SOURCE_COMMIT@@','verify_source.py'):
            self.assertIn(value,text)
        readme=(ROOT/'native-control/README.md.in').read_text()
        self.assertIn('Stop before runner registration',readme);self.assertIn('Required reviewers',readme)

if __name__=='__main__':unittest.main()

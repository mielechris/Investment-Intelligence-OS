import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'BACK END/backend'))
from iios_qualification_v2 import child
from iios_qualification_v2.state import AUTHORITY, decode
from truth_spine_contract import verified

class RoleContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def run_role(self,role,nonce):
        config=dict(role=role,nonce=nonce,session='session',work=str(self.root),authority=AUTHORITY)
        path=self.root/(role+'.json');path.write_text(json.dumps(config))
        output=io.StringIO()
        with patch.object(sys,'argv',['child',str(path)]),patch.object(sys,'stdin',io.StringIO('ACK '+nonce+'\nSTOP '+nonce+'\n')),contextlib.redirect_stdout(output):child.main()
        events=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([row['event'] for row in events],['READY','DATA','STOPPED'])
        self.assertTrue(all(row['authority']==AUTHORITY for row in events))
        self.assertTrue(all(len(origin['sha256'])==64 for origin in events[-1]['origins'].values()))
    def test_seed_to_projection_exact_lineage(self):
        self.run_role('scheduler','session');self.run_role('publisher','publisher')
        ledger=verified(decode((self.root/'seeded-ledger.json').read_bytes()))
        projection=verified(decode((self.root/'projection.json').read_bytes()))
        self.assertEqual(projection['parent'],ledger['content_hash'])
        self.assertEqual(projection['executed_requests'],0)
        self.assertEqual(len(ledger['records']),3)
    def test_substituted_ledger_rejected(self):
        self.run_role('scheduler','session')
        path=self.root/'seeded-ledger.json';row=decode(path.read_bytes());row['executed_requests']=1;path.chmod(0o600);path.write_text(json.dumps(row))
        with self.assertRaises(ValueError):self.run_role('publisher','publisher')

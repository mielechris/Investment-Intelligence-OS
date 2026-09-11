import json
import unittest
from unittest.mock import Mock
from truth_spine_contract import canonical
from truth_spine_lineage import file_hash
from test_truth_spine_lineage import retained_root, pin
from truth_spine_noninterference import CATEGORIES, load_baseline, observe, finish, permitted
from truth_spine_noninterference import PinnedBaseline
import hashlib
from pathlib import Path


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.root=retained_root('baseline')
        self.spec={'schema':'iios-protected-baseline-v1','owner_scope':'SIX_PINNED_OWNER_FILES',
                   'files':{k:[] for k in CATEGORIES},'trees':[],'processes':[],'listeners':[]}

    def test_incomplete_baseline_does_not_become_accepted(self):
        p=self.root/'spec.json';p.write_bytes(canonical(self.spec))
        with self.assertRaises(ValueError):load_baseline(p,file_hash(p))

    def test_process_change_fails_without_modification(self):
        self.spec['processes']=[{'pid':10}];self.spec['listeners']=[{'port':6000}]
        with self.assertRaises(ValueError):observe(self.spec,process_inventory=lambda _:[],listener_inventory=lambda x:x)

    def test_changed_file_is_not_rebaselined(self):
        p=self.root/'config.json';p.write_bytes(b'first');expected=pin(p)
        self.spec['files']['configurations']=[expected]
        p.write_bytes(b'second')
        with self.assertRaises(ValueError):observe(self.spec,process_inventory=lambda x:x,listener_inventory=lambda x:x)

    def test_owner_root_and_credential_paths_not_opened(self):
        for p in ['/private/tmp/iios-northstar-owner-snapshots-sb37-attempt2/l7/snapshot.db','/Users/crm/Library/Keychains/login.keychain-db']:
            with self.assertRaises(ValueError):permitted({'path':p})

    def test_failed_equality_writes_no_after_receipt(self):
        (self.root/'baselines').mkdir()
        with self.assertRaises(ValueError):finish(self.root,{'a':1},{'a':2})
        self.assertFalse((self.root/'baselines/after.json').exists())


class ExactMembershipTests(unittest.TestCase):
    def setUp(self):
        self.root=retained_root('exact-baseline');protected=self.root/'protected';protected.mkdir()
        rows={k:[] for k in CATEGORIES}
        for category in sorted(CATEGORIES):
            for i in range(37 if category=='configurations' else 5 if category=='permanent_artifacts' else 1):
                p=protected/(category+str(i)+'.json');p.write_bytes(b'SYNTHETIC_PROTECTED_FILE')
                rows[category].append(pin(p))
        self.spec={'schema':'iios-protected-baseline-v1','owner_scope':'SIX_PINNED_OWNER_FILES','files':rows,
                   'trees':[{'root':str(protected),'members':sorted(p.name for p in protected.iterdir())}],
                   'processes':[{'pid':10,'parent_pid':1,'start_time':'SYNTHETIC','executable':'/synthetic/python',
                                 'executable_hash':'a'*64,'argv':['synthetic'],'cwd':'/synthetic'}],
                   'listeners':[{'address':'127.0.0.1','port':6000,'pid':10}]}
        raw=canonical(self.spec);p=self.root/'baseline.json';p.write_bytes(raw)
        self.baseline=load_baseline(p,hashlib.sha256(raw).hexdigest())

    def observe(self,baseline=None,processes=None,listeners=None):
        return observe(baseline or self.baseline,process_inventory=lambda x:x if processes is None else processes,
                       listener_inventory=lambda x:x if listeners is None else listeners)

    def test_exact_membership_passes(self):
        self.assertEqual(self.observe(),self.observe())

    def test_missing_extra_and_substituted_members_rejected(self):
        for category in CATEGORIES:
            changed=json.loads(self.baseline.raw);changed['files'][category].pop()
            with self.assertRaises(ValueError):self.observe(PinnedBaseline(canonical(changed),self.baseline.expected_hash))
        (Path(self.spec['trees'][0]['root'])/'unlisted.json').write_bytes(b'EXTRA')
        with self.assertRaisesRegex(ValueError,'BASELINE_TREE_CHANGED'):self.observe()

    def test_process_and_listener_membership_is_exact(self):
        for processes in [[],self.spec['processes']*2]:
            with self.assertRaises(ValueError):self.observe(processes=processes)
        for listeners in [[],[{'address':'127.0.0.1','port':6000,'pid':11}]]:
            with self.assertRaises(ValueError):self.observe(listeners=listeners)

    def test_valid_self_hash_does_not_replace_independent_expected_pin(self):
        raw=canonical({**self.spec,'owner_scope':'WHOLE_OWNER_ROOT'})
        with self.assertRaisesRegex(ValueError,'BASELINE_SPEC_PIN_MISMATCH'):
            self.observe(PinnedBaseline(raw,self.baseline.expected_hash))

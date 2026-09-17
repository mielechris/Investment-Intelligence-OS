from copy import deepcopy
import unittest
from alpha_runtime_bootstrap import validate_recipe, admit_build_control, SCHEMA, TOOLS, STEPS
from provider_gateway_contract import content_hash, locked_authority

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.roots={k:'/disposable/'+k for k in ('quarantine','bootstrap','staging','output')}
        self.tools=dict.fromkeys(TOOLS,'a'*64)
        self.r=dict(schema=SCHEMA,scope='PRIVATE_BUILD_DESIGN_ONLY',source='a'*40,roots=self.roots,
            vendor_parent='b'*64,tools=self.tools,script_parent='c'*64,steps=list(STEPS),
            dependencies={v:[] if i==0 else [STEPS[i-1]] for i,v in enumerate(STEPS)},authority=locked_authority())
    def check(self,r):return validate_recipe(r,content_hash(r),roots=self.roots,source='a'*40,
        vendor_parent='b'*64,tool_parents=self.tools,script_parent='c'*64)
    def test_non_circular_recipe_never_authorizes_execution(self):
        value=self.check(self.r);self.assertEqual(value['status'],'RECIPE_BOUND_NOT_EXECUTED')
        self.assertFalse(value['execution_authorized']);self.assertFalse(value['production_qualified'])
        self.assertNotEqual(value['interpreter'].split('/bin/')[0],self.roots['output'])
    def test_circular_self_bootstrap_rejected(self):
        r=deepcopy(self.r);r['dependencies'][STEPS[0]]=[STEPS[-1]]
        with self.assertRaisesRegex(ValueError,'BOOTSTRAP_DEPENDENCIES'):self.check(r)
    def test_qualification_cannot_move_after_build(self):
        r=deepcopy(self.r);r['steps'][6],r['steps'][8]=r['steps'][8],r['steps'][6]
        with self.assertRaises(ValueError):self.check(r)
    def test_every_independent_parent_required(self):
        for k in ('vendor_parent','script_parent','source'):
            r=deepcopy(self.r);r[k]='0'*len(r[k])
            with self.subTest(k=k),self.assertRaises(ValueError):self.check(r)
    def test_unreviewed_python_tool_or_unknown_step_rejected(self):
        for k in ('tools','steps'):
            r=deepcopy(self.r)
            if k=='tools':r[k]['/usr/bin/python3']='a'*64
            else:r[k].append('RUN_FINAL_RUNTIME_FIRST')
            with self.assertRaises(ValueError):self.check(r)
    def test_overlapping_roots_rejected_even_if_independently_rehashed(self):
        self.roots['bootstrap']=self.roots['output']+'/sub'
        with self.assertRaises(ValueError):self.check(self.r)
    def test_missing_native_bootstrap_evidence_rejected(self):
        with self.assertRaises(ValueError):admit_build_control({},content_hash({}),recipe_parent='a'*64,
            bootstrap_manifest_parent='b'*64,vendor_parent='c'*64,tools_parent='d'*64,script_parent='e'*64,host_parent='f'*64)

    def test_v2_vendor_and_layout_are_independent_and_no_execution_grant(self):
        from alpha_runtime_files import layout_policy,VENDOR
        p=layout_policy();r=deepcopy(self.r);r.update(schema='iios-vendor-bootstrap-recipe-v2',
            vendor_parent=VENDOR,layout_policy=p,layout_parent=content_hash(p))
        args=dict(roots=self.roots,source='a'*40,vendor_parent=VENDOR,tool_parents=self.tools,script_parent='c'*64)
        result=validate_recipe(r,content_hash(r),**args);self.assertFalse(result['execution_authorized'])
        r['layout_policy']['links'][0]['target']='elsewhere';r['layout_parent']=content_hash(r['layout_policy'])
        with self.assertRaises(ValueError):validate_recipe(r,content_hash(r),**args)

    def test_v2_build_control_requires_final_signature_metadata_and_link_evidence(self):
        from alpha_runtime_files import layout_policy,VENDOR
        parents=dict(recipe_parent='a'*64,bootstrap_manifest_parent='b'*64,vendor_parent=VENDOR,
            tools_parent='d'*64,script_parent='e'*64,host_parent='f'*64)
        p=layout_policy();required=('vendor_signature','os_tool_trust','complete_closure','immutable_ownership',
            'final_destination_imports','no_historical_dependencies','scrubbed_environment',
            'final_signatures','final_metadata','final_link_graph')
        e=dict(schema='iios-reviewed-build-control-v2',scope='PRIVATE_BUILD_CONTROL_ONLY',**parents,
            layout_policy=p,layout_parent=content_hash(p),authority=locked_authority(),
            checks={k:dict(status='ACCEPTED',independent_parent='1'*64) for k in required})
        self.assertFalse(admit_build_control(e,content_hash(e),**parents)['production_qualified'])
        for missing in required:
            bad=deepcopy(e);del bad['checks'][missing]
            with self.assertRaises(ValueError):admit_build_control(bad,content_hash(bad),**parents)

"""Complete substituted static inputs; no OS inspection or runtime execution."""
import copy
import json
import unittest
from unittest.mock import patch
from iios_native_conductor import QualificationFailure,digest,canonical,STAGES
from iios_native_image_policy import *
from provider_gateway_contract import canonical as runtime_canonical


def inputs():
    files=[{'path':'Python','sha256':'a'*64,'size':100},{'path':'lib/_ssl.so','sha256':'b'*64,'size':100}]
    m={'runtime_root':'/fixture/runtime','release_commit':'c'*40,'file_inventory':files,'interpreter':'/fixture/runtime/Python','interpreter_sha256':'a'*64}
    static={'status':'PASS_STATIC_FINAL_LOCATION_ONLY','source_commit':'c'*40,'runtime_executed':False,
            'manifest_sha256':sha(runtime_canonical(m)),
            'images':[dict(path=r['path'],sha256=r['sha256'],uuid=str(i+1)*32,signature='VERIFIED',
                          load_dependencies=[['LC_LOAD_DYLIB','/usr/lib/libSystem.B.dylib']]) for i,r in enumerate(files)]}
    plan={'scope':'PRODUCTION_IMPORT_PLAN_V1','source_commit':'c'*40,'runtime_root':'/fixture/runtime','imports':['ssl'],
          'import_images':{'ssl':['lib/_ssl.so']},'interpreter':'Python','host':{'build':'fixture','arch':'arm64'},
          'os_image_paths':['/usr/lib/libSystem.B.dylib','/usr/lib/libffi-trampolines.dylib'],'review_parent':'d'*64}
    osref={'schema':'SIGNED_OS_CACHE_REFERENCE_V1','source_build':'fixture','arch':'arm64','cache_uuid':'3'*32,
           'signed_files':[{'path':'/System/Library/dyld/cache','sha256':'e'*64,'apple_anchor_verified':True,'exit':0}],
           'image_uuids':{'/usr/lib/libSystem.B.dylib':'4'*32}}
    standalone=[{'path':'/usr/lib/libffi-trampolines.dylib','uuid':'5'*32,'sha256':'f'*64,'size':123,
                 'apple_anchor_verified':True,'exit':0,'review_parent':'a'*64,'signature_parent':'b'*64}]
    d=dict(manifest=m,static=static,plan=plan,os_reference=osref,standalone=standalone)
    d['parents']={k:digest(v) for k,v in d.items()};return d


class PolicyTests(unittest.TestCase):
    def setUp(self):self.inputs=inputs()
    def build(self):return build_policy(**self.inputs)
    def repin(self):self.inputs['parents']={k:digest(v) for k,v in self.inputs.items() if k!='parents'}
    def reject(self,expected):
        with self.assertRaises(QualificationFailure) as c:self.build()
        self.assertEqual(c.exception.detail['predicate'],expected)
    def test_deterministic_external_reference(self):
        p=self.build();self.assertEqual(p,self.build());verify_policy(p,**self.inputs)
        self.assertEqual(p['image_maximum'],4);self.assertEqual(p['minimum_count'],3)
        self.assertEqual(p['mapped_memory_integrity'],'UNVERIFIED');self.assertEqual(p['boot_attestation'],'UNRESOLVED')
    def test_altered_parent(self):
        self.inputs['plan']['imports'].append('os');self.reject('PRODUCTION_POLICY_PARENT_HASH')
    def test_bootstrap_static_receipt_rejected(self):
        self.inputs['static']['status']='PASS_BOOTSTRAP_IDENTITY_ONLY';self.repin();self.reject('STATIC_RECEIPT_SCOPE')
    def test_bootstrap_policy_cannot_be_production(self):
        with self.assertRaises(QualificationFailure) as c:verify_policy({'scope':BOOTSTRAP},**self.inputs)
        self.assertEqual(c.exception.detail['predicate'],'PRODUCTION_REFERENCE_SCOPE')
    def test_production_cannot_be_bootstrap(self):
        raw=canonical(self.build())
        with self.assertRaises(QualificationFailure) as c:bootstrap_scope(raw,payload_sha256=sha(raw),interpreter='/fixture/runtime/Python',interpreter_sha256='a'*64)
        self.assertEqual(c.exception.detail['predicate'],'BOOTSTRAP_REFERENCE_SCOPE')
    def test_bootstrap_payload_preserved(self):
        value={'schema':'SCOPED_BOOTSTRAP_IMAGE_REFERENCE_V1','expected_count':557,'image_maximum':557,
               'ordered_rows':[{'id':i,'path':f'/bootstrap/{i}','kind':'PRIVATE_SEALED','sha256':'a'*64} for i in range(557)]}
        raw=canonical(value);before=bytes(raw);wrapper=bootstrap_scope(raw,payload_sha256=sha(raw),interpreter='/bootstrap/0',interpreter_sha256='a'*64)
        self.assertEqual(raw,before);self.assertEqual(wrapper['expected_count'],557)
    def test_forbidden_files(self):
        for name in ('lib/_tkinter.so','lib/tkinter/__init__.py','Frameworks/Tcl.framework/Tcl','Frameworks/Tk.framework/Tk','lib/libtk8.6.dylib','lib/libtcl9.0.dylib'):
            with self.subTest(name=name):
                self.inputs=inputs();self.inputs['manifest']['file_inventory'].append({'path':name,'sha256':'f'*64,'size':1})
                self.inputs['static']['manifest_sha256']=sha(runtime_canonical(self.inputs['manifest']));self.repin();self.reject('PRODUCTION_FORBIDDEN_COMPONENT')
    def test_forbidden_import(self):
        for name in ('_tkinter','tkinter','tkinter.ttk','Tcl','Tk'):
            self.inputs=inputs();self.inputs['plan']['imports']=[name];self.repin();self.reject('PRODUCTION_FORBIDDEN_IMPORT')
    def test_forbidden_dependency(self):
        self.inputs['static']['images'][0]['load_dependencies']=[['LC_LOAD_DYLIB','/System/Library/Frameworks/Tk.framework/Tk']]
        self.repin();self.reject('PRODUCTION_FORBIDDEN_DEPENDENCY')
    def test_substituted_private_hash(self):
        self.inputs['static']['images'][0]['sha256']='f'*64;self.repin();self.reject('PRIVATE_IMAGE_STATIC_IDENTITY')
    def test_unknown_dependency(self):
        self.inputs['static']['images'][0]['load_dependencies']=[['LC_LOAD_DYLIB','/usr/lib/unknown.dylib']]
        self.repin();self.reject('STATIC_DEPENDENCY_OUTSIDE_UNIVERSE')
    def test_dependency_escape(self):
        self.inputs['static']['images'][0]['load_dependencies']=[['LC_LOAD_DYLIB','@loader_path/../escape']]
        self.repin();self.reject('IMAGE_PATH')
    def test_dependency_closure(self):
        self.inputs['plan']['import_images']['ssl']=[]
        self.inputs['static']['images'][0]['load_dependencies'].append(['LC_LOAD_DYLIB','@loader_path/lib/_ssl.so'])
        self.repin();self.assertIn('/fixture/runtime/lib/_ssl.so',self.build()['required_paths'])
    def test_unsigned_cache(self):
        self.inputs['os_reference']['signed_files'][0]['apple_anchor_verified']=False;self.repin();self.reject('CACHE_APPLE_SIGNATURE')
    def test_wrong_os_host(self):
        self.inputs['os_reference']['source_build']='other';self.repin();self.reject('OS_HOST_BINDING')
    def test_unknown_standalone(self):
        self.inputs['standalone']=[];self.repin();self.reject('OS_IMAGE_INDEPENDENT_REFERENCE')
    def test_unsigned_standalone(self):
        self.inputs['standalone'][0]['exit']=1;self.repin();self.reject('STANDALONE_APPLE_SIGNATURE')
    def test_duplicate_os_universe(self):
        self.inputs['plan']['os_image_paths']*=2;self.repin();self.reject('OS_UNIVERSE_DUPLICATE')
    def test_static_manifest_substitution(self):
        self.inputs['manifest']['release_commit']='e'*40;self.repin();self.reject('STATIC_MANIFEST_PARENT')
    def test_duplicate_manifest(self):
        m=self.inputs['manifest'];m['file_inventory']*=2
        self.inputs['static']['manifest_sha256']=sha(runtime_canonical(m));self.repin();self.reject('MANIFEST_DUPLICATE_PATH')
    def test_plan_coverage(self):
        self.inputs['plan']['import_images']={};self.repin();self.reject('IMPORT_IMAGE_COVERAGE')
    def test_unreviewed_plan(self):
        self.inputs['plan']['review_parent']='UNKNOWN';self.repin();self.reject('PRODUCTION_IMPORT_PLAN_REVIEW')


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.policy=build_policy(**inputs());self.parent=digest(self.policy)
        images=[{k:r[k] for k in ('path','uuid')} for r in self.policy['rows']]
        scan={'complete':True,'count':len(images),'images':images}
        self.report={'scope':PRODUCTION,'policy_parent':self.parent,'imports':['ssl'],
                     'scans':[copy.deepcopy(scan),copy.deepcopy(scan)],'origins':[{'module':'ssl','file':'lib/_ssl.so'}],
                     'cache_uuids':['3'*32]*2}
    def decode(self):return decode_report(canonical(self.report),self.policy,self.parent)
    def reject(self,predicate):
        with self.assertRaises(QualificationFailure) as c:self.decode()
        self.assertEqual(c.exception.detail['predicate'],predicate)
    def test_two_complete_matching_scans(self):self.assertEqual(self.decode()['images'],4)
    def test_bootstrap_report_rejected(self):self.report['scope']=BOOTSTRAP;self.reject('RUNTIME_REPORT_SCOPE_PARENT')
    def test_policy_substitution(self):self.report['policy_parent']='e'*64;self.reject('RUNTIME_REPORT_SCOPE_PARENT')
    def test_reordered_import_plan(self):self.report['imports']=['os','ssl'];self.reject('RUNTIME_IMPORT_PLAN_EXACT')
    def test_two_scans_required(self):self.report['scans'].pop();self.reject('TWO_COMPLETE_IMAGE_SCANS')
    def test_incomplete_scan(self):self.report['scans'][1]['complete']=False;self.reject('IMAGE_SCAN_INCOMPLETE')
    def test_count_mismatch(self):self.report['scans'][0]['count']=3;self.reject('IMAGE_SCAN_COUNT')
    def test_no_overflow_truncation(self):
        self.report['scans'][0]['images']*=2;self.report['scans'][0]['count']=8;self.reject('IMAGE_REPORT_OVERFLOW_OR_MISSING')
    def test_duplicate_images(self):
        self.report['scans'][0]['images'][1]=self.report['scans'][0]['images'][0];self.reject('DUPLICATE_LOADED_IMAGE')
    def test_unknown_image(self):self.report['scans'][0]['images'][0]['path']='/usr/lib/unknown';self.reject('IMAGE_OUTSIDE_UNIVERSE')
    def test_out_of_root(self):self.report['scans'][0]['images'][0]['path']='/another/Python';self.reject('IMAGE_OUTSIDE_UNIVERSE')
    def test_changed_uuid(self):self.report['scans'][0]['images'][0]['uuid']='f'*32;self.reject('LOADED_IMAGE_UUID')
    def test_forbidden_loaded_image(self):self.report['scans'][0]['images'][0]['path']='/System/Library/Tcl.framework/Tcl';self.reject('PRODUCTION_FORBIDDEN_COMPONENT')
    def test_stability_order(self):self.report['scans'][1]['images'].reverse();self.reject('IMAGE_SCAN_STABILITY')
    def test_unknown_module_origin(self):self.report['origins'][0]['file']='other.so';self.reject('MODULE_ORIGIN_OUTSIDE_SEAL')
    def test_cache_substitution(self):self.report['cache_uuids'][1]='f'*32;self.reject('RUNTIME_CACHE_UUID')
    def test_raw_report_overflow(self):
        with self.assertRaises(QualificationFailure) as c:decode_report(b' '* (MAX_REPORT_BYTES+1),self.policy,self.parent)
        self.assertEqual(c.exception.detail['predicate'],'RUNTIME_REPORT_OVERFLOW')
    def test_duplicate_json_keys(self):
        with self.assertRaises(QualificationFailure) as c:decode_report(b'{"scope":1,"scope":2}',self.policy,self.parent)
        self.assertEqual(c.exception.detail['predicate'],'RUNTIME_REPORT_DUPLICATE_KEY')
    def test_no_reference_mutation_by_observation(self):
        before=canonical(self.policy);self.decode();self.assertEqual(canonical(self.policy),before)


class StageOrderTests(unittest.TestCase):
    def test_reference_before_acceptance(self):self.assertEqual(STAGES[5:8],('STATIC_SIGNATURE_AND_INVENTORY','STATIC_RUNTIME_REFERENCE','FINAL_RUNTIME_ACCEPTANCE'))
    def test_no_reference_before_static_receipt(self):
        from iios_native_dispatcher import NativeContext
        c=NativeContext({},'a'*64,'/fixture');c.stage=STAGES[6]
        with patch('iios_native_image_policy.build_policy') as build,self.assertRaises(QualificationFailure):run_stage(c,{},1,None)
        build.assert_not_called()

"""Substituted reference facts and pure audit-policy tests; no native inspection."""
import ast
import copy
from pathlib import Path
import unittest
from iios_native_conductor import QualificationFailure
from iios_native_runtime_reference import validate_reference,conflicts,admit_reference,SCHEMA


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.kw={'source':'a'*40,'root':'/fixture/runtime','host':{'machine':'arm64'},'layout_parent':'b'*64,
                 'policy':{'forbidden_import_roots':['_tkinter'],'excluded_prefixes':['Frameworks/Tk.framework']},
                 'imports':['ssl'],'now':10}
        self.ref={'schema':SCHEMA,'source_commit':'a'*40,'runtime_root':'/fixture/runtime','host':{'machine':'arm64'},
                  'layout_parent':'b'*64,'imports':['ssl'],'ordered_rows':[{'id':0,'path':'/fixture/runtime/bin/python',
                  'uuid':'1'*32,'kind':'PRIVATE_SEALED','file':'bin/python','sha256':'c'*64,'size':1}],
                  'expected_count':1,'cache_uuid':'2'*32,'independent_catalog_parent':'d'*64,
                  'membership_review_parent':'e'*64,'expires_at':20}
    def reject(self,predicate):
        with self.assertRaises(QualificationFailure) as caught:validate_reference(self.ref,**self.kw)
        self.assertEqual(caught.exception.detail['predicate'],predicate)
    def test_valid_substituted_reference(self):
        self.assertEqual(validate_reference(self.ref,**self.kw),self.ref)
    def test_missing_reference(self):
        with self.assertRaises(QualificationFailure) as caught:admit_reference(None,**self.kw)
        self.assertEqual(caught.exception.detail['predicate'],'FINAL_RUNTIME_IMAGE_REFERENCE_REQUIRED')
    def test_bootstrap_scope_rejected(self):
        self.ref['schema']='SCOPED_BOOTSTRAP_IMAGE_REFERENCE_V1';self.reject('FINAL_RUNTIME_REFERENCE_SCOPE')
    def test_cross_scope_parents(self):
        for key,value in [('source_commit','f'*40),('runtime_root','/other'),('host',{}),('layout_parent','f'*64)]:
            with self.subTest(key=key):
                previous=self.ref[key];self.ref[key]=value;self.reject('FINAL_RUNTIME_REFERENCE_PARENTS');self.ref[key]=previous
    def test_expiry(self):
        self.ref['expires_at']=10;self.reject('FINAL_RUNTIME_REFERENCE_EXPIRED')
    def test_import_order(self):
        self.ref['imports']=['other'];self.reject('FINAL_RUNTIME_IMPORT_ORDER')
    def test_excluded_import(self):
        self.kw['imports']=self.ref['imports']=['_tkinter'];self.reject('FINAL_RUNTIME_REFERENCE_EXCLUDED_COMPONENT')
    def test_excluded_image(self):
        self.ref['ordered_rows'][0]['file']='Frameworks/Tk.framework/Tk';self.reject('FINAL_RUNTIME_REFERENCE_EXCLUDED_COMPONENT')
    def test_incomplete_observation_reference(self):
        self.ref['expected_count']=2;self.reject('FINAL_RUNTIME_IMAGE_COUNT')
    def test_reordered_image(self):
        self.ref['ordered_rows'][0]['id']=1;self.reject('FINAL_RUNTIME_IMAGE_ROW')
    def test_path_substitution(self):
        self.ref['ordered_rows'][0]['path']='/other/python';self.reject('FINAL_RUNTIME_PRIVATE_IMAGE_ROOT')
    def test_unknown_image_kind(self):
        self.ref['ordered_rows'][0]['kind']='TRUST_ME';self.reject('FINAL_RUNTIME_PLATFORM_IMAGE_SCOPE')
    def test_unpinned_bytes(self):
        self.ref['ordered_rows'][0]['sha256']='unknown';self.reject('FINAL_RUNTIME_PRIVATE_IMAGE_PIN')
    def test_unreviewed_membership(self):
        self.ref['membership_review_parent']=None;self.reject('FINAL_RUNTIME_REFERENCE_INDEPENDENT_PARENT')
    def test_sanitized_conflict(self):
        self.ref['imports']=['_tkinter'];result=conflicts(self.ref,self.kw['policy'])
        self.assertEqual(result['forbidden_import_count'],1);self.assertFalse(result['dynamic_acceptance']);self.assertFalse(result['native_executed'])


class PreparationGuardTests(unittest.TestCase):
    def setUp(self):
        self.tree=ast.parse((Path(__file__).resolve().parents[2]/'scripts/iios_native_qualification.py').read_text())
        function=next(n for n in self.tree.body if isinstance(n,ast.FunctionDef) and n.name=='_preparation_audit')
        self.ns={'_preparation_mode':True}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'<pure-audit-policy>','exec'),self.ns)
        self.audit=self.ns['_preparation_audit']
    def test_installed_before_preparation_imports(self):
        imports=[];found=False
        for node in self.tree.body:
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='sys.addaudithook':found=True;break
            if isinstance(node,(ast.Import,ast.ImportFrom)):imports.append(ast.unparse(node))
        self.assertTrue(found);self.assertEqual(imports,['import sys'])
    def test_all_effect_families_denied(self):
        for event in ('socket.connect','subprocess.Popen','ctypes.dlopen','os.kill','os.mkdir','os.exec','os.posix_spawn','os.chmod','os.rename'):
            with self.subTest(event=event),self.assertRaises(PermissionError):self.audit(event,())
    def test_write_and_protected_path_denied(self):
        for args in (('/fixture/file','w',0),('/fixture/file','r',512),('/fixture/../file','r',0),('/fixture/credentials/token','r',0),(9,'r',0)):
            with self.subTest(args=args),self.assertRaises(PermissionError):self.audit('open',args)
    def test_read_permitted(self):
        self.audit('open',('/fixture/source.py','r',0))

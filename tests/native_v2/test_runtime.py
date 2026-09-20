import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'BACK END/backend'))
from iios_qualification_v2.runtime import *
from iios_qualification_v2.state import canonical

class RuntimeTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def wheel(self, extras=None):
        data={'sample.py':b'x=1\n',**(extras or {})};record='sample-1.dist-info/RECORD';out=io.StringIO();w=csv.writer(out)
        for n,b in data.items():w.writerow([n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).rstrip(b'=').decode(),len(b)])
        w.writerow([record,'','']);data[record]=out.getvalue().encode();p=self.root/'sample-1-py3-none-any.whl'
        with zipfile.ZipFile(p,'w') as z:
            for n,b in data.items():z.writestr(n,b)
        return p,{'filename':p.name,'size':p.stat().st_size,'sha256':file_hash(p)}
    def test_record_hashes_pass(self):p,pin=self.wheel();verify_wheel(p,pin)
    def test_wheel_hash_reject(self):
        p,pin=self.wheel();pin['sha256']='0'*64
        with self.assertRaises(ValueError):verify_wheel(p,pin)
    def test_traversal_reject(self):
        p,pin=self.wheel({'../escape':b'x'})
        with self.assertRaises(ValueError):verify_wheel(p,pin)
    def test_site_hooks_reject(self):
        p,pin=self.wheel({'hook.pth':b'import bad'})
        with self.assertRaises(ValueError):verify_wheel(p,pin)
    def test_wrong_platform_reject(self):
        p,pin=self.wheel();pin['filename']='sample-1-cp314-cp314-win_amd64.whl'
        with self.assertRaises(ValueError):verify_wheel(p,pin)
    def test_lock_exact_and_artifact_closure(self):
        lock=self.root/'lock';lock.write_text('sample==1\n');pins=self.root/'pins';value={'schema':2,'lock_sha256':file_hash(lock),'wheels':[{'name':'sample','version':'1','filename':'sample-1-py3-none-any.whl','size':1,'sha256':'a'*64}]};pins.write_text(json.dumps(value));lock_binding(lock,pins)
        lock.write_text('sample>=1\n')
        with self.assertRaises(ValueError):lock_binding(lock,pins)
    def test_inventory_detects_added_file(self):
        p=self.root/'x';p.write_text('x');snapshot=environment_tree(self.root);(self.root/'added').write_text('y')
        with self.assertRaises(ValueError):verify_environment_tree(self.root,snapshot)
    def test_inventory_rejects_escape_symlink(self):
        (self.root/'link').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):environment_tree(self.root)

    def partial_venv(self, identity='a'*64):
        runtime=self.root/'runtime';runtime.mkdir();venv=runtime/('venv-'+identity);venv.mkdir();venv.chmod(0o700)
        for name in ('bin','include','lib'):(venv/name).mkdir()
        (venv/'pyvenv.cfg').write_text('partial');(venv/'IIOS-REQUIREMENTS.txt').write_text('partial')
        quarantine=self.root/'qualification'/'native-v2'/'runtime-quarantine';quarantine.mkdir(parents=True)
        return runtime,venv,quarantine

    def test_explicit_partial_quarantine_moves_only_the_owned_incomplete_venv(self):
        runtime,venv,quarantine=self.partial_venv()
        bound={'root':str(self.root)}
        with patch('iios_qualification_v2.runtime.durable.contained',side_effect=lambda path,bound:path):
            target=quarantine_partial_venv(runtime,quarantine,'a'*64,bound=bound)
        self.assertFalse(venv.exists());self.assertEqual(target.name,'venv');self.assertTrue((target/'pyvenv.cfg').is_file())
        self.assertEqual(target.parent.stat().st_mode&0o777,0o700)

    def test_partial_quarantine_rejects_substitutes_and_completed_venvs(self):
        runtime,venv,quarantine=self.partial_venv();shutil.rmtree(venv);venv.symlink_to(self.root)
        with patch('iios_qualification_v2.runtime.durable.contained',side_effect=lambda path,bound:path):
            with self.assertRaisesRegex(ValueError,'PARTIAL_VENV_OWNER_MODE'):quarantine_partial_venv(runtime,quarantine,'a'*64,bound={'root':str(self.root)})
        venv.unlink();venv.mkdir();venv.chmod(0o700);(venv/'IIOS-RUNTIME.json').write_text('{}')
        with patch('iios_qualification_v2.runtime.durable.contained',side_effect=lambda path,bound:path):
            with self.assertRaisesRegex(ValueError,'RUNTIME_REBUILD_PARTIAL_ONLY'):quarantine_partial_venv(runtime,quarantine,'a'*64,bound={'root':str(self.root)})

    def test_partial_runtime_requires_explicit_rebuild_and_complete_runtime_cannot_move(self):
        runtime,venv,quarantine=self.partial_venv();identity='a'*64
        common=dict(verify_vendor=patch('iios_qualification_v2.runtime.verify_vendor',return_value={}),
                    lock_binding=patch('iios_qualification_v2.runtime.lock_binding',return_value={'wheels':[]}),
                    directory=patch('iios_qualification_v2.runtime.directory',side_effect=lambda path:path),
                    digest=patch('iios_qualification_v2.runtime.digest',return_value=identity),
                    file_hash=patch('iios_qualification_v2.runtime.file_hash',return_value='b'*64))
        with common['verify_vendor'],common['lock_binding'],common['directory'],common['digest'],common['file_hash']:
            with self.assertRaisesRegex(ValueError,'PARTIAL_VENV_REQUIRES_EXPLICIT_REBUILD'):
                environment(runtime,{},self.root/'lock',self.root/'artifacts',quarantine=quarantine,bound={'root':str(self.root)})
        (venv/'IIOS-RUNTIME.json').write_text('{}')
        with common['verify_vendor'],common['lock_binding'],common['directory'],common['digest'],common['file_hash']:
            with self.assertRaisesRegex(ValueError,'RUNTIME_REBUILD_PARTIAL_ONLY'):
                environment(runtime,{},self.root/'lock',self.root/'artifacts',rebuild=True,quarantine=quarantine,bound={'root':str(self.root)})
        self.assertTrue(venv.exists());self.assertTrue(partial_rebuild_required(runtime,identity) is False)

    def test_recovery_hint_is_limited_to_the_exact_safe_identity(self):
        runtime,venv,_=self.partial_venv();identity='a'*64
        self.assertTrue(partial_rebuild_required(runtime,identity))
        self.assertFalse(partial_rebuild_required(runtime,'b'*64))
        venv.chmod(0o755);self.assertFalse(partial_rebuild_required(runtime,identity))

    def test_partial_quarantine_rejects_uncontained_destination(self):
        runtime,venv,quarantine=self.partial_venv()
        with self.assertRaisesRegex(ValueError,'PARTIAL_VENV_QUARANTINE_CONTAINMENT'):
            quarantine_partial_venv(runtime,quarantine,'a'*64,bound={'root':str(self.root/'other')})

    def test_partial_quarantine_fails_closed_if_rename_target_is_replaced(self):
        runtime,venv,quarantine=self.partial_venv();original=os.rename
        def replace_after_move(source,target):
            original(source,target);shutil.rmtree(target);Path(target).mkdir();Path(target).chmod(0o700)
        with patch('iios_qualification_v2.runtime.durable.contained',side_effect=lambda path,bound:path),\
             patch('iios_qualification_v2.runtime.os.rename',side_effect=replace_after_move):
            with self.assertRaisesRegex(ValueError,'PARTIAL_VENV_REPLACED_DURING_MOVE'):
                quarantine_partial_venv(runtime,quarantine,'a'*64,bound={'root':str(self.root)})

    def test_missing_wheelhouse_fails_before_venv_or_pip(self):
        pins={'wheels':[{'filename':'missing-1-py3-none-any.whl','size':1,'sha256':'a'*64}]}
        with patch('iios_qualification_v2.runtime.verify_vendor',return_value={}),\
             patch('iios_qualification_v2.runtime.lock_binding',return_value=pins),\
             patch('iios_qualification_v2.runtime.directory',side_effect=lambda path: path),\
             patch('iios_qualification_v2.runtime.command') as command,\
             patch('iios_qualification_v2.runtime.pip_command') as pip:
            with self.assertRaisesRegex(ValueError,'WHEELHOUSE_MISSING:missing-1-py3-none-any.whl'):
                environment(self.root,{},self.root/'lock',self.root/'artifacts')
        pip.assert_not_called()
        command.assert_not_called()

    def test_symlinked_wheelhouse_entry_fails_before_venv_or_pip(self):
        filename='linked-1-py3-none-any.whl';wheelhouse=self.root/'wheelhouse';wheelhouse.mkdir()
        (wheelhouse/filename).symlink_to(self.root/'other.whl')
        pins={'wheels':[{'filename':filename,'size':1,'sha256':'a'*64}]}
        with patch('iios_qualification_v2.runtime.verify_vendor',return_value={}),\
             patch('iios_qualification_v2.runtime.lock_binding',return_value=pins),\
             patch('iios_qualification_v2.runtime.directory',side_effect=lambda path: path),\
             patch('iios_qualification_v2.runtime.command') as command,\
             patch('iios_qualification_v2.runtime.pip_command') as pip:
            with self.assertRaisesRegex(ValueError,'WHEELHOUSE_MISSING:'+filename):
                environment(self.root,{},self.root/'lock',self.root/'artifacts')
        pip.assert_not_called()
        command.assert_not_called()
    def test_no_package_network_or_install_into_system(self):
        import inspect
        text=inspect.getsource(environment)
        for flag in ('--no-index','--require-hashes','--no-deps','--only-binary=:all:'):self.assertIn(flag,text)
        self.assertNotIn('sudo',text)
    def test_unresolved_native_rpath_fails(self):
        with patch('iios_qualification_v2.runtime.command',side_effect=['x:\n\t@rpath/missing.dylib (compatibility version 1)\n','']):
            with self.assertRaisesRegex(ValueError,'RPATH'):native_dependencies(self.root/'image.so',self.root)
    def test_foreign_native_dependency_fails(self):
        with patch('iios_qualification_v2.runtime.command',side_effect=['x:\n\t/etc/passwd (compatibility version 1)\n','']):
            with self.assertRaisesRegex(ValueError,'ESCAPE'):native_dependencies(self.root/'image.so',self.root)
    def test_source_binding_requires_commit_inventory_origin_and_detached_head(self):
        expected={'repository':'mielechris/Investment-Intelligence-OS','commit':'a'*40,'inventory_sha256':'b'*64}
        identity={'commit':'a'*40,'inventory':[{'path':'x','sha256':'c'*64,'bytes':1,'mode':420}],'inventory_sha256':'b'*64}
        with patch('iios_qualification_v2.runtime.source_identity',return_value=identity),patch('iios_qualification_v2.runtime.command',side_effect=['https://github.com/mielechris/Investment-Intelligence-OS.git\n','HEAD\n']):
            self.assertEqual(source_binding(self.root,expected)['repository'],expected['repository'])
        changed=dict(expected,commit='d'*40)
        with patch('iios_qualification_v2.runtime.source_identity',return_value=identity):
            with self.assertRaisesRegex(ValueError,'MISMATCH'):source_binding(self.root,changed)
    def test_source_identity_accepts_owner_only_executable_mode(self):
        script=self.root/'script';script.write_text('#!/bin/sh\n');script.chmod(0o700)
        staged='100755 '+'a'*40+' 0\tscript\0'
        with patch('iios_qualification_v2.runtime.command',side_effect=['','a'*40+'\n',staged]):
            value=source_identity(self.root)
        self.assertEqual(value['inventory'][0]['mode'],0o755)

    def test_source_identity_excludes_generated_bazel_out_from_inventory(self):
        script=self.root/'script';script.write_text('x');script.chmod(0o600)
        generated=self.root/'bazel-out';generated.mkdir();(generated/'output.py').write_text('generated')
        staged='100644 '+'a'*40+' 0\tscript\0'
        with patch('iios_qualification_v2.runtime.command',side_effect=['','a'*40+'\n',staged]):
            value=source_identity(self.root)
        self.assertEqual([row['path'] for row in value['inventory']],['script'])
        with patch('iios_qualification_v2.runtime.command',side_effect=['','a'*40+'\n',staged]),\
             patch('iios_qualification_v2.runtime.os.open',side_effect=FileNotFoundError):
            value=source_identity(self.root)
        self.assertEqual([row['path'] for row in value['inventory']],['script'])

    def test_source_identity_rejects_unrelated_extra_and_generated_substitutes(self):
        script=self.root/'script';script.write_text('x');script.chmod(0o600)
        staged='100644 '+'a'*40+' 0\tscript\0'
        (self.root/'extra.py').write_text('extra')
        with patch('iios_qualification_v2.runtime.command',side_effect=['','a'*40+'\n',staged]):
            with self.assertRaisesRegex(ValueError,'SOURCE_EXTRA_FILE'):source_identity(self.root)
        (self.root/'extra.py').unlink();(self.root/'bazel-out').write_text('substitute')
        with patch('iios_qualification_v2.runtime.command',side_effect=['','a'*40+'\n',staged]):
            with self.assertRaisesRegex(ValueError,'SOURCE_GENERATED_ROOT_TYPE'):source_identity(self.root)
        (self.root/'bazel-out').unlink();(self.root/'bazel-out').symlink_to(self.root/'script')
        with patch('iios_qualification_v2.runtime.command',side_effect=['','a'*40+'\n',staged]):
            with self.assertRaisesRegex(ValueError,'SOURCE_GENERATED_ROOT_TYPE'):source_identity(self.root)
        (self.root/'bazel-out').unlink()
        generated='100644 '+'a'*40+' 0\tbazel-out/substitute.py\0'
        with patch('iios_qualification_v2.runtime.command',side_effect=['','a'*40+'\n',generated]):
            with self.assertRaisesRegex(ValueError,'SOURCE_INDEX_MODE'):source_identity(self.root)

    def codesign_success(self):
        return [SimpleNamespace(returncode=0,stdout=b'',stderr=b''),
                SimpleNamespace(returncode=0,stdout=b'',stderr=b'TeamIdentifier=BMM5U3QVKW\n')]

    def test_vendor_signature_targets_are_fixed_and_psf_bound(self):
        for target in ('launcher','app_image'):
            with self.subTest(target=target),patch('iios_qualification_v2.runtime.subprocess.run',side_effect=self.codesign_success()) as run:
                receipt=codesign_vendor_target('/fixed/vendor/image',target=target,resolved='FRAMEWORK_3_14')
            self.assertEqual(receipt,{'target':target,'resolved':'FRAMEWORK_3_14','signer':'MATCHED'})
            self.assertIn('-R='+VENDOR_REQUIREMENT,run.call_args_list[0].args[0])
            self.assertIn('--strict',run.call_args_list[0].args[0])
            self.assertNotIn('--ignore-resources',run.call_args_list[0].args[0])
            self.assertEqual(run.call_args_list[1].args[0][:3],['/usr/bin/codesign','-d','--verbose=4'])

    def test_framework_container_is_not_a_codesign_target(self):
        with self.assertRaisesRegex(ValueError,'VENDOR_SIGNATURE_TARGET'):
            codesign_vendor_target('/fixed/vendor/framework/Python',target='framework_library',resolved='FRAMEWORK_3_14')

    def framework_tree(self, *, link=False):
        tree=self.root/'framework';tree.mkdir();item=tree/'item';item.write_text('one');item.chmod(0o640)
        if link:(tree/'link').symlink_to('item')
        return tree,item

    def test_vendor_framework_inventory_rejects_content_mode_size_type_extra_and_missing(self):
        tree,item=self.framework_tree();expected=vendor_framework_inventory(tree)
        item.write_text('two');self.assertNotEqual(vendor_framework_inventory(tree),expected)
        item.write_text('one');item.chmod(0o600);self.assertNotEqual(vendor_framework_inventory(tree),expected)
        item.chmod(0o640);item.write_text('longer');self.assertNotEqual(vendor_framework_inventory(tree),expected)
        item.write_text('one');(tree/'extra').write_text('x');self.assertNotEqual(vendor_framework_inventory(tree),expected)
        (tree/'extra').unlink();item.unlink();self.assertNotEqual(vendor_framework_inventory(tree),expected)
        item.mkdir();self.assertNotEqual(vendor_framework_inventory(tree),expected)

    def test_vendor_framework_inventory_rejects_owner_group_and_size_mutation(self):
        tree,item=self.framework_tree();expected=vendor_framework_inventory(tree);original=Path.lstat
        for field in ('st_uid','st_gid','st_size'):
            with self.subTest(field=field):
                def changed(path,field=field):
                    value=original(path)
                    if path.name=='item':
                        values=dict(st_mode=value.st_mode,st_uid=value.st_uid,st_gid=value.st_gid,st_size=value.st_size)
                        values[field]+=1;return SimpleNamespace(**values)
                    return value
                with patch.object(Path,'lstat',autospec=True,side_effect=changed):self.assertNotEqual(vendor_framework_inventory(tree),expected)

    def test_vendor_framework_inventory_rejects_symlink_replacement_and_escape(self):
        tree,item=self.framework_tree(link=True);(tree/'other').write_text('one');expected=vendor_framework_inventory(tree)
        link=tree/'link';link.unlink();link.symlink_to('other');self.assertNotEqual(vendor_framework_inventory(tree),expected)
        link.unlink();link.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError,'VENDOR_FRAMEWORK_SYMLINK'):vendor_framework_inventory(tree)

    def test_vendor_framework_inventory_allows_only_pinned_dangling_symlink(self):
        tree=self.root/'framework';tree.mkdir();(tree/'link').symlink_to('missing')
        with patch('iios_qualification_v2.runtime._VENDOR_DANGLING_LINKS',frozenset((('link','missing'),))):
            self.assertIsInstance(vendor_framework_inventory(tree),list)
        with self.assertRaisesRegex(ValueError,'VENDOR_FRAMEWORK_SYMLINK'):vendor_framework_inventory(tree)

    def test_vendor_framework_contract_rejects_inventory_pin_and_duplicate_path(self):
        source=self.root/'source';config_dir=source/'config';config_dir.mkdir(parents=True);tree,item=self.framework_tree()
        entries=vendor_framework_inventory(tree);document={'schema':1,'root':'/Library/Frameworks/Python.framework/Versions/3.14',
            'python_version':'3.14.7','installer_sha256':'a'*64,'entries':entries}
        path=config_dir/'vendor.json';path.write_bytes(canonical(document))
        config={'vendor_framework_inventory_path':'config/vendor.json','vendor_framework_inventory_sha256':file_hash(path),'vendor_installer_sha256':'a'*64}
        self.assertEqual(bind_vendor_framework_contract(source,config)['vendor_framework_inventory_entries'],entries)
        config['vendor_framework_inventory_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'VENDOR_FRAMEWORK_INVENTORY_PIN'):bind_vendor_framework_contract(source,config)
        document['entries'].append(dict(entries[-1]));path.write_bytes(canonical(document));config['vendor_framework_inventory_sha256']=file_hash(path)
        with self.assertRaisesRegex(ValueError,'VENDOR_FRAMEWORK_INVENTORY_DUPLICATE'):bind_vendor_framework_contract(source,config)

    def test_vendor_codesign_nonzero_exit_is_sanitized(self):
        result=SimpleNamespace(returncode=1,stdout=b'',stderr=b'raw diagnostic')
        with patch('iios_qualification_v2.runtime.subprocess.run',return_value=result):
            with self.assertRaisesRegex(ValueError,'target=launcher;resolved=FRAMEWORK_3_14;action=verify;outcome=NONZERO_EXIT;exit=EXIT_NONZERO;stderr=TEXT;stderr_sha256=[0-9a-f]{64};signer=NOT_EVALUATED'):
                codesign_vendor_target('/fixed/vendor/image',target='launcher',resolved='FRAMEWORK_3_14')

    def test_vendor_codesign_timeout_is_sanitized(self):
        timeout=subprocess.TimeoutExpired(['/usr/bin/codesign'],10,stderr=b'late')
        with patch('iios_qualification_v2.runtime.subprocess.run',side_effect=timeout):
            with self.assertRaisesRegex(ValueError,'outcome=TIMEOUT;exit=NOT_AVAILABLE;stderr=TEXT;stderr_sha256=[0-9a-f]{64}'):
                codesign_vendor_target('/fixed/vendor/image',target='launcher',resolved='FRAMEWORK_3_14')

    def test_vendor_codesign_malformed_output_is_sanitized(self):
        results=[SimpleNamespace(returncode=0,stdout=b'',stderr=b''),SimpleNamespace(returncode=0,stdout=b'',stderr=b'no team')]
        with patch('iios_qualification_v2.runtime.subprocess.run',side_effect=results):
            with self.assertRaisesRegex(ValueError,'action=describe;outcome=MALFORMED_OUTPUT;exit=EXIT_ZERO;stderr=TEXT;stderr_sha256=[0-9a-f]{64};signer=MALFORMED'):
                codesign_vendor_target('/fixed/vendor/image',target='app_image',resolved='FRAMEWORK_3_14')

    def test_vendor_codesign_wrong_signer_is_sanitized(self):
        results=[SimpleNamespace(returncode=0,stdout=b'',stderr=b''),SimpleNamespace(returncode=0,stdout=b'',stderr=b'TeamIdentifier=WRONG\n')]
        with patch('iios_qualification_v2.runtime.subprocess.run',side_effect=results):
            with self.assertRaisesRegex(ValueError,'outcome=WRONG_SIGNER;exit=EXIT_ZERO;.*signer=MISMATCH'):
                codesign_vendor_target('/fixed/vendor/image',target='app_image',resolved='FRAMEWORK_3_14')

    def test_vendor_codesign_tool_launch_failure_is_sanitized(self):
        with patch('iios_qualification_v2.runtime.subprocess.run',side_effect=OSError(2,'missing')):
            with self.assertRaisesRegex(ValueError,'outcome=TOOL_LAUNCH_FAILURE;exit=NOT_AVAILABLE;stderr=TEXT;stderr_sha256=[0-9a-f]{64}'):
                codesign_vendor_target('/fixed/vendor/image',target='launcher',resolved='FRAMEWORK_3_14')

    def test_vendor_missing_target_is_sanitized(self):
        config={'vendor_python':'/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14','python_version':'3.14.7'}
        with patch.object(Path,'resolve',side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError,'target=launcher;resolved=MISSING;action=verify;outcome=MISSING_TARGET;exit=NOT_RUN;stderr=EMPTY;stderr_sha256=NONE;signer=NOT_EVALUATED'):
                verify_vendor(config)

    def test_vendor_launcher_cannot_substitute_app_executable(self):
        config={'vendor_python':'/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python','python_version':'3.14.7'}
        with self.assertRaisesRegex(ValueError,'VENDOR_LOCATION'):verify_vendor(config)

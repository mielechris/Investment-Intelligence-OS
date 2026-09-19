#!/usr/bin/env python3
"""Build, ad-hoc sign and bind the fixed local Native Qualification app."""
import argparse,hashlib,json,os,pwd,re,shutil,stat,subprocess,sys
from pathlib import Path

REPOSITORY='mielechris/Investment-Intelligence-OS';BRANCH='feature/iios-native-qualification-v2'
IDENTIFIER='com.miele.iios-native-qualification'
AUTHORITY={'broker_connection':False,'paper_order_permission':False,'trade_execution':False,'live_execution':False}
ENV={'PATH':'/usr/bin:/bin:/usr/sbin','LC_ALL':'C','TZ':'UTC'}
def require(value,code):
    if not value:raise ValueError(code)
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(argv,**kwargs):
    value=subprocess.run(argv,env=ENV,stdin=subprocess.DEVNULL,capture_output=True,timeout=120,**kwargs)
    require(value.returncode==0 and len(value.stdout)+len(value.stderr)<=1024*1024,'BUILD_TOOL_FAILED:'+Path(argv[0]).name)
    return value
def exclusive(path,value,mode):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:stream.write(value);stream.flush();os.fsync(stream.fileno())
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    source=Path(__file__).resolve().parents[1];home=Path(pwd.getpwuid(os.getuid()).pw_dir)
    output=Path(args.output);expected=home/'Applications/IIOS Native Qualification.app'
    require(output==expected and not output.exists() and not output.is_symlink(),'APP_OUTPUT_EXCLUSIVE')
    sys.path.insert(0,str(source/'BACK END/backend'));from iios_qualification_v2.runtime import source_identity
    from iios_qualification_v2.roots import binding,contained
    identity=source_identity(source);branch=run(['/usr/bin/git','branch','--show-current'],cwd=source,text=True).stdout.strip()
    origin=run(['/usr/bin/git','remote','get-url','origin'],cwd=source,text=True).stdout.strip()
    require(branch==BRANCH and origin in ('https://github.com/'+REPOSITORY,'https://github.com/'+REPOSITORY+'.git'),'APP_SOURCE_SCOPE')
    applications=home/'Applications'
    if not applications.exists():applications.mkdir(mode=0o700)
    st=applications.lstat();require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and st.st_uid==os.getuid() and not st.st_mode&0o022,'APPLICATIONS_ROOT')
    bound=binding();qualification=contained(Path(bound['root'])/'qualification',bound);host=qualification/'selected-host.json'
    require(not host.exists() and not host.is_symlink(),'SELECTED_HOST_EXCLUSIVE')
    version=qualification/('local-app-'+identity['commit'][:7]+'-01')
    version.mkdir(mode=0o700);bundle=version/'IIOS Native Qualification.app';macos=bundle/'Contents/MacOS';macos.mkdir(mode=0o700,parents=True)
    template=(source/'native-app/IIOSNativeQualification.m.in').read_text()
    values={'@@SOURCE_COMMIT@@':identity['commit'],'@@SOURCE_INVENTORY@@':identity['inventory_sha256'],
            '@@SOURCE_ROOT@@':str(source),'@@USER_HOME@@':str(home)}
    for old,new in values.items():template=template.replace(old,new)
    implementation=version/'IIOSNativeQualification.m';implementation.write_text(template);implementation.chmod(0o600)
    plist=(source/'native-app/Info.plist.in').read_text().replace('@@SOURCE_COMMIT@@',identity['commit'])
    (bundle/'Contents/Info.plist').write_text(plist);(bundle/'Contents/Info.plist').chmod(0o600)
    executable=macos/'IIOSNativeQualification'
    run(['/usr/bin/xcrun','clang','-fobjc-arc','-O2','-framework','Cocoa','-o',str(executable),str(implementation)])
    executable.chmod(0o700)
    run(['/usr/bin/codesign','--force','--sign','-','--timestamp=none','--options','runtime','--identifier',IDENTIFIER,str(bundle)])
    for path in sorted(bundle.rglob('*')):
        if path.is_dir():path.chmod(0o700)
        elif path==executable:path.chmod(0o700)
        else:path.chmod(0o600)
    bundle.chmod(0o700);(bundle/'Contents').chmod(0o700);macos.chmod(0o700)
    run(['/usr/bin/codesign','--verify','--deep','--strict','--all-architectures',str(bundle)])
    details=run(['/usr/bin/codesign','-d','--verbose=4',str(bundle)],text=True)
    description=details.stdout+details.stderr
    ids=re.findall(r'^Identifier=(.+)$',description,re.M);hashes=re.findall(r'^CDHash=([0-9A-Fa-f]+)$',description,re.M)
    require(ids==[IDENTIFIER] and len(hashes)==1 and ('Signature=adhoc' in description or 'adhoc' in description),'APP_SIGNING_INFO')
    bundle.rename(output)
    run(['/usr/bin/codesign','--verify','--deep','--strict','--all-architectures',str(output)])
    hardware=run(['/usr/sbin/ioreg','-rd1','-c','IOPlatformExpertDevice'],text=True).stdout
    matches=re.findall(r'"IOPlatformUUID"\s*=\s*"([A-Fa-f0-9-]+)"',hardware);require(len(matches)==1,'APP_HARDWARE')
    files={}
    for path in sorted(output.rglob('*')):
        if path.is_file():files[str(path.relative_to(output))]={'bytes':path.stat().st_size,'sha256':sha(path),'mode':stat.S_IMODE(path.stat().st_mode)}
    inventory_sha256=hashlib.sha256(canonical(files)).hexdigest()
    manifest={'schema':1,'status':'PREPARED_NOT_EXECUTED','repository':REPOSITORY,'source_commit':identity['commit'],
              'source_inventory_sha256':identity['inventory_sha256'],'branch':BRANCH,'bundle':str(output),
              'signing_method':'adhoc','identifier':IDENTIFIER,'cdhash':hashes[0].lower(),'files':files,
              'bundle_inventory_sha256':inventory_sha256,
              'provider_requests':0,'authority':AUTHORITY,
              'native_qualification_executed':False,'historical_cleanup':'NOT_ESTABLISHED'}
    app_manifest=version/'APP-MANIFEST.json'
    exclusive(app_manifest,canonical(manifest),0o400)
    contract={'schema':4,'launch_mode':'local_app','repository':REPOSITORY,'commit':identity['commit'],'branch':BRANCH,
              'inventory_sha256':identity['inventory_sha256'],'app_bundle':str(output),
              'app_executable':str(output/'Contents/MacOS/IIOSNativeQualification'),
              'app_executable_sha256':sha(output/'Contents/MacOS/IIOSNativeQualification'),
              'app_identifier':IDENTIFIER,'app_cdhash':hashes[0].lower(),'signing_method':'adhoc',
              'app_manifest':str(app_manifest),'app_manifest_sha256':sha(app_manifest),
              'hardware_uuid':matches[0].lower(),'uid':os.getuid()}
    exclusive(host,canonical(contract),0o600);implementation.chmod(0o400);version.chmod(0o500)
    print(canonical(manifest).decode(),end='')
if __name__=='__main__':main()

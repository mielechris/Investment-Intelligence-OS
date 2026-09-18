"""Serial native conductor audit boundary; never an OS sandbox attestation.

The preparation hook remains active until this hook has acknowledged a private
installation challenge. No handler is imported or resolved before that receipt.
Exact command grants are single-use and revoked on every exception path.
"""
from contextlib import contextmanager
import os
import hashlib
from pathlib import PurePosixPath
import sys
import stat
import importlib.machinery
import importlib.util
from iios_native_conductor import STAGES, digest, require, QualificationFailure, pin_file
from iios_native_terminal import FORBIDDEN_COMPONENTS

SCHEMA='IIOS_NATIVE_AUDIT_V1'
METADATA_STAGES=frozenset((STAGES[4],STAGES[5],STAGES[7],STAGES[8]))
METADATA_SYMBOLS=frozenset(('flistxattr','fgetxattr','filesec_init','filesec_free','fstatx_np','filesec_query_property','acl_get_fd_np','acl_get_entry','acl_free','acl_valid'))
READ=frozenset(('open','os.listdir','os.scandir','os.listxattr','os.getxattr','import','exec','compile'))
WRITE=frozenset(('os.mkdir','os.chmod','os.utime','os.setxattr','os.removexattr'))
INSPECT=frozenset(('subprocess.Popen','ctypes.dlopen','ctypes.dlsym','ctypes.create_string_buffer','ctypes.cdata/buffer','ctypes.get_errno','ctypes.set_errno'))
OPERATIONS={
    STAGES[0]:READ|INSPECT|frozenset(('os.mkdir',)),
    STAGES[1]:READ|INSPECT,
    STAGES[2]:READ|INSPECT,
    STAGES[3]:READ|frozenset(('os.mkdir',)),
    STAGES[4]:READ|WRITE|INSPECT,
    STAGES[5]:READ|INSPECT,
    STAGES[6]:READ,
    STAGES[7]:READ|INSPECT,
    STAGES[8]:READ|WRITE|INSPECT,
    STAGES[9]:READ,
    'CLEANUP':READ|INSPECT,
    'EXPORT':READ,
}
# Socket effects belong to sandboxed disposable children, never this controller.
FORBIDDEN=frozenset(('os.kill','os.killpg','os.system','os.posix_spawn','os.fork','os.forkpty',
    'os.exec','os.chdir','os.fchdir','os.putenv','os.unsetenv','os.chown','os.truncate',
    'os.remove','os.rmdir','os.rename','os.link','os.symlink','sys.settrace','sys.setprofile'))


def module_registry(hashes, roots):
    """Deterministic registry from admitted paths; no filesystem/import discovery."""
    rows={}
    for root in roots:
        base=PurePosixPath(root['path'])
        require(base.is_absolute() and '..' not in base.parts,STAGES[0],'MODULE_ROOT')
        for origin,parent in sorted(hashes.items()):
            path=PurePosixPath(origin)
            if not path.is_relative_to(base):continue
            relative=path.relative_to(base);parts=list(relative.parts)
            if '__pycache__' in parts:continue
            package=parts[-1]=='__init__.py'
            if origin.endswith('.py'):
                parts=parts[:-1] if package else parts[:-1]+[parts[-1][:-3]];kind='SOURCE'
            else:
                suffix=next((v for v in importlib.machinery.EXTENSION_SUFFIXES if origin.endswith(v)),None)
                if suffix is None:continue
                parts=parts[:-1]+[parts[-1][:-len(suffix)]];kind='EXTENSION'
            if not parts or not all(v.isidentifier() for v in parts):continue
            name='.'.join(parts)
            row=dict(origin=origin,sha256=parent,root=str(base),scope=root['scope'],kind=kind,package=package)
            require(name not in rows or rows[name]==row,STAGES[0],'MODULE_DUPLICATE_OR_SCOPE')
            rows[name]=row
    return rows


def controller_module_roots(manifest):
    source=manifest['source']['root']
    roots=[{'path':source+'/BACK END/backend','scope':'CONTROLLER_SOURCE'},
           {'path':source+'/scripts','scope':'CONTROLLER_SOURCE'}]
    bootstrap=manifest.get('native',{}).get('static_descriptor',{}).get('bootstrap_root')
    if bootstrap:
        library=bootstrap+'/lib/python3.14'
        roots.extend({'path':library+suffix,'scope':'BOOTSTRAP_CONTROLLER'} for suffix in ('','/lib-dynload','/site-packages'))
    return roots


class ReviewedModuleSpec(importlib.machinery.ModuleSpec):
    @property
    def cached(self):return None
    @cached.setter
    def cached(self,value):
        require(value is None,STAGES[0],'MODULE_CACHE_DISABLED')


class ReviewedSourceLoader(importlib.machinery.SourceFileLoader):
    """Execute stable pinned source, with independently checked module metadata."""
    def __init__(self,name,path,parent,stage=lambda:STAGES[0],row=None):
        super().__init__(name,path);self.parent=parent;self.stage=stage
        self.row=row or dict(origin=path,sha256=parent,root=str(PurePosixPath(path).parent),scope='REVIEWED_SOURCE',kind='SOURCE',package=False)
        self.binding=digest(self.row);self.observation=None;self.module=None
    def get_code(self,fullname):
        require(fullname==self.name,self.stage(),'SOURCE_MODULE_NAME')
        try:
            record=pin_file(self.path,self.parent,source_bytes=True)
            observed=(record['identity'],record['ancestors'])
            require(self.observation is None or self.observation==observed,self.stage(),'MODULE_SOURCE_REPLACED')
            self.observation=observed;raw=record['bytes']
        except QualificationFailure as error:
            error.detail['stage']=self.stage();raise
        return compile(raw,self.path,'exec',dont_inherit=True)
    def verify(self,module):
        require(self.path==self.row['origin'] and self.parent==self.row['sha256'] and self.row['kind']=='SOURCE'
                and self.path.endswith('.py') and PurePosixPath(self.path).is_relative_to(self.row['root']),self.stage(),'MODULE_PINNED_ORIGIN')
        spec=getattr(module,'__spec__',None);package=self.name if self.row['package'] else self.name.rpartition('.')[0]
        locations=[str(PurePosixPath(self.path).parent)] if self.row['package'] else None
        require(type(spec) is ReviewedModuleSpec and spec.name==self.name and spec.origin==self.path and spec.loader is self,
                self.stage(),'MODULE_SPEC_BINDING')
        require(getattr(module,'__name__',None)==self.name and getattr(module,'__file__',None)==self.path and getattr(module,'__loader__',None) is self and getattr(module,'__package__',None)==package,
                self.stage(),'MODULE_METADATA_BINDING')
        require(spec.submodule_search_locations==locations and (getattr(module,'__path__',None)==locations if self.row['package'] else not hasattr(module,'__path__')),self.stage(),'MODULE_PACKAGE_BINDING')
        require(spec.cached is None and getattr(module,'__cached__',None) is None and sys.dont_write_bytecode,self.stage(),'MODULE_CACHE_DISABLED')
        require(getattr(module,'__reviewed_source_parent__',None)==self.binding and digest(self.row)==self.binding,self.stage(),'MODULE_SOURCE_PARENT')
        require(sys.modules.get(self.name) is module and (self.module is None or self.module is module) and all(name==self.name or value is not module for name,value in tuple(sys.modules.items())),self.stage(),'MODULE_DUPLICATE_IDENTITY')
        record=pin_file(self.path,self.parent,source_bytes=True)
        observed=(record['identity'],record['ancestors'])
        if self.observation is not None:require(observed==self.observation,self.stage(),'MODULE_SOURCE_REPLACED')
        else:self.observation=observed
        return self.binding
    def exec_module(self,module):
        require(self.module is None,self.stage(),'MODULE_REEXECUTION_FORBIDDEN')
        module.__file__=self.path;module.__loader__=self;module.__cached__=None
        module.__package__=self.name if self.row['package'] else self.name.rpartition('.')[0]
        module.__reviewed_source_parent__=self.binding
        self.verify(module);code=self.get_code(self.name);self.verify(module)
        try:exec(code,module.__dict__)
        except QualificationFailure as error:
            error.detail.setdefault('module_binding',dict(name=self.name,origin=self.path,source_parent=self.binding));raise
        self.verify(module);self.module=module
    def set_data(self,*args,**kwargs):
        raise QualificationFailure(self.stage(),'BYTECODE_WRITE_FORBIDDEN','SOURCE_ONLY','WRITE_ATTEMPT')


class ReviewedSourceFinder:
    def __init__(self,hashes,stage=lambda:STAGES[0],roots=None):
        self.hashes=dict(hashes);self.stage=stage
        self.roots=roots if roots is not None else [{'path':str(PurePosixPath(p).parent),'scope':'REVIEWED_SOURCE'} for p in sorted(hashes)]
        self.registry=module_registry(self.hashes,self.roots);self.registry_parent=digest(self.registry)
    def optional_absence(self,fullname):
        caller={'_wmi':'platform','msvcrt':'subprocess'}.get(fullname)
        if caller is None:return False
        row=self.registry.get(caller)
        if row is None or row['scope']!='BOOTSTRAP_CONTROLLER':return False
        frame=sys._getframe(1)
        for _ in range(12):
            if frame is None:break
            values=frame.f_globals
            if values.get('__name__')==caller:
                loader=values.get('__loader__')
                require(type(loader) is ReviewedSourceLoader and loader.binding==digest(row) and frame.f_code.co_filename==row['origin'],self.stage(),'OPTIONAL_MODULE_CALLER')
                loader.verify(sys.modules[caller]);return True
            frame=frame.f_back
        return False
    def find_spec(self,fullname,path=None,target=None):
        require(digest(self.registry)==self.registry_parent,self.stage(),'MODULE_REGISTRY_MUTATION')
        row=self.registry.get(fullname)
        if row is None:
            if self.optional_absence(fullname):raise ModuleNotFoundError(name=fullname)
            error=QualificationFailure(self.stage(),'MODULE_ORIGIN_REQUIRED','PINNED_SOURCE_OR_EXTENSION','UNREGISTERED_MODULE')
            error.detail['module_binding']={'name':fullname if len(fullname)<=160 and all(p.isidentifier() for p in fullname.split('.')) else 'INVALID_NAME','registry_parent':self.registry_parent};raise error
        require(target is None,self.stage(),'MODULE_RELOAD_FORBIDDEN')
        if '.' in fullname:
            parent=self.registry.get(fullname.rpartition('.')[0]);expected=[str(PurePosixPath(parent['origin']).parent)] if parent and parent['package'] else None
            require(expected is not None and list(path or [])==expected,self.stage(),'MODULE_SEARCH_PARENT')
        else:require(path is None,self.stage(),'MODULE_SEARCH_PARENT')
        origin=row['origin'];require(self.hashes.get(origin)==row['sha256'],self.stage(),'MODULE_ORIGIN_PIN')
        if row['kind']=='SOURCE':loader=ReviewedSourceLoader(fullname,origin,row['sha256'],self.stage,row)
        else:
            pin_file(origin,row['sha256']);loader=importlib.machinery.ExtensionFileLoader(fullname,origin)
        spec=ReviewedModuleSpec(fullname,loader,origin=origin,is_package=row['package']);spec.has_location=True
        if row['package']:spec.submodule_search_locations=[str(PurePosixPath(origin).parent)]
        return spec
    def load(self,name,origin,parent):
        row=self.registry.get(name)
        require(row is not None and row['kind']=='SOURCE' and row['origin']==origin and row['sha256']==parent,self.stage(),'MODULE_EXPLICIT_BINDING')
        if name in sys.modules:
            module=sys.modules[name];loader=getattr(module,'__loader__',None)
            require(type(loader) is ReviewedSourceLoader and loader.binding==digest(row),self.stage(),'MODULE_EXISTING_UNREVIEWED')
            loader.verify(module);return module
        spec=self.find_spec(name);module=importlib.util.module_from_spec(spec);sys.modules[name]=module
        try:spec.loader.exec_module(module)
        except BaseException as error:
            if sys.modules.get(name) is module:del sys.modules[name]
            if isinstance(error,QualificationFailure):error.detail.setdefault('module_binding',dict(name=name,origin=origin,source_parent=digest(row)))
            raise
        return module


class NativeAudit:
    def __init__(self,manifest,parent):
        self.parent=parent;self.manifest=manifest;self.stage=STAGES[0]
        self.root=str(PurePosixPath(manifest['output_parent'])/manifest['output_name'])
        self.paths={str(PurePosixPath(manifest['source']['root'])/r['relative']) for r in manifest['source']['inventory']}
        self.paths.update(r['path'] for r in manifest['inputs']+manifest['historical_records'])
        self.paths.update(manifest['tool_pins']);self.paths.add(manifest['ci']['path'])
        self.paths.add(manifest['dispatcher']['path'])
        self.hashes={str(PurePosixPath(manifest['source']['root'])/r['relative']):r['sha256'] for r in manifest['source']['inventory']}
        self.hashes.update({r['path']:r['sha256'] for r in manifest['inputs']+manifest['historical_records']})
        self.hashes.update(manifest['tool_pins']);self.hashes.update({manifest['ci']['path']:manifest['ci']['sha256'],manifest['dispatcher']['path']:manifest['dispatcher']['sha256']})
        self.paths=frozenset(self.paths)
        self.directories=frozenset(str(p) for value in self.paths|{self.root} for p in PurePosixPath(value).parents)
        self.binding_parent=digest({'root':self.root,'paths':sorted(self.paths),'directories':sorted(self.directories),'hashes':self.hashes})
        self.fds={};self.fd_identity={};self.active=[];self.command=None;self.inspecting=False;self.metadata_read=False
        self.launching=False;self.installed=False;self.challenge=None;self.acknowledged=False;self.receipt=None
        self.originals={};self.sealed=();self.last_denial=None;self.finder=None;self.finders=None
    def reject(self,predicate,observed='UNDECLARED'):
        error=QualificationFailure(self.stage,predicate,'ADMITTED',observed,
            exception='PermissionError',errno_category='AUDIT_POLICY')
        self.last_denial=dict(error.detail);raise error
    def inside(self,path):return path==self.root or path.startswith(self.root+'/')
    def lexical(self,value,dir_fd=None):
        if isinstance(value,int):
            if value not in self.fds:self.reject('AUDIT_UNBOUND_FD')
            expected=self.fd_identity.get(value)
            if expected is not None:
                st=os.fstat(value)
                if (st.st_dev,st.st_ino)!=expected:self.reject('AUDIT_FD_REPLACED')
            return self.fds[value]
        if not isinstance(value,(str,bytes,os.PathLike)):self.reject('AUDIT_PATH_TYPE')
        raw=os.fsdecode(os.fspath(value));p=PurePosixPath(raw)
        if '\0' in raw or '..' in p.parts or any(x.lower() in FORBIDDEN_COMPONENTS or x.startswith('~') for x in p.parts):
            self.reject('AUDIT_PROTECTED_PATH')
        if not p.is_absolute():
            if dir_fd in (None,-1) or dir_fd not in self.fds:self.reject('AUDIT_UNBOUND_RELATIVE_PATH')
            p=PurePosixPath(self.fds[dir_fd])/p
        return str(p)
    def path(self,value,write=False,dir_fd=None,directory=False):
        path=self.lexical(value,dir_fd)
        if write:
            if not self.inside(path):self.reject('AUDIT_WRITE_ROOT')
            if any(path==s or path.startswith(s+'/') for s in self.sealed):self.reject('AUDIT_SEALED_WRITE')
            if self.stage not in (STAGES[0],STAGES[3],STAGES[4],STAGES[6],STAGES[7],STAGES[8],STAGES[9],'CLEANUP','EXPORT'):
                # Durable conductor checkpoint records are the only writes in
                # read-only stages. Their exclusive creation is enforced by Journal.
                p=PurePosixPath(path)
                if str(p.parent)!=self.root or not p.name.startswith('checkpoint-'):self.reject('AUDIT_STAGE_WRITE')
        elif not (self.inside(path) or path in self.paths or (directory and path in self.directories)):
            self.reject('AUDIT_READ_PIN')
        # Do not let an admitted lexical name substitute an outside inode.
        # Existing symlinks are never a blanket grant, including within output.
        for part in reversed((PurePosixPath(path),*PurePosixPath(path).parents)):
            try:st=os.lstat(part)
            except FileNotFoundError:continue
            if stat.S_ISLNK(st.st_mode):self.reject('AUDIT_PATH_SYMLINK')
        return path
    def __call__(self,event,args):
        if event=='iios.native.audit.challenge':
            if args!=(self.challenge,):self.reject('AUDIT_INSTALLATION_CHALLENGE')
            self.acknowledged=True;return
        if event=='compile' and isinstance(args[1],str) and args[1].startswith(self.manifest['source']['root']+'/') and args[1] not in self.hashes:self.reject('AUDIT_UNBOUND_SOURCE_COMPILE')
        if event=='compile' and args[1] in self.hashes:
            raw=args[0].encode('utf-8') if isinstance(args[0],str) else args[0]
            if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=self.hashes[args[1]]:self.reject('AUDIT_COMPILED_SOURCE_MUTATION')
        if event.startswith('fcntl.'):
            if event!='fcntl.flock':self.reject('AUDIT_LOCK_OPERATION')
            path=self.path(args[0],True)
            if not self.inside(path):self.reject('AUDIT_LOCK_ROOT')
            return
        if event in FORBIDDEN or event.startswith(('socket.','winreg.')):self.reject('AUDIT_FORBIDDEN_EFFECT')
        effect=event=='open' or event.startswith(('os.','subprocess.','ctypes.'))
        if effect and event not in OPERATIONS[self.stage]:self.reject('AUDIT_STAGE_OPERATION')
        if event=='subprocess.Popen':
            observed=(args[0],tuple(args[1]),args[2],args[3])
            if self.command is None or observed!=self.command:self.reject('AUDIT_COMMAND_BINDING')
            self.command=None
        elif event=='open':
            if isinstance(args[0],(str,bytes)) and os.fsdecode(args[0]).endswith(('.pyc','.pyo')):
                attempted=os.fsdecode(args[0]);source=None
                for candidate in self.hashes:
                    if candidate.endswith('.py') and importlib.util.cache_from_source(candidate)==attempted:
                        source=candidate;break
                try:self.reject('AUDIT_UNREVIEWED_BYTECODE')
                except QualificationFailure as error:
                    error.detail['bytecode_attempt']={'path':attempted if source else 'UNADMITTED_PATH',
                        'source':source or 'UNADMITTED_SOURCE','source_sha256':self.hashes[source] if source else 'UNBOUND',
                        'operation':'OPEN','loader':'SOURCE_FILE_LOADER_CACHE_LOOKUP' if source else 'UNBOUND_BYTECODE_LOOKUP'}
                    self.last_denial=dict(error.detail);raise
            if args[0]=='/dev/null' and self.launching and stat.S_ISCHR(os.lstat('/dev/null').st_mode):return
            if isinstance(args[0],int) and args[0] not in self.fds:
                if self.launching and stat.S_ISFIFO(os.fstat(args[0]).st_mode):return
                self.reject('AUDIT_UNBOUND_FD')
            value=self.active[-1] if self.active else args[0]
            mode,flags=args[1:];write=bool((flags or 0)&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)) or isinstance(mode,str) and any(x in mode for x in 'wax+')
            self.path(value,write,directory=bool((flags or 0)&os.O_DIRECTORY))
        elif event in ('os.listdir','os.scandir','os.listxattr','os.getxattr'):
            self.path(args[0],directory=True)
        elif event in WRITE:
            index=2 if event in ('os.mkdir','os.chmod') else None
            self.path(args[0],True, args[index] if index is not None and len(args)>index else None)
        elif event.startswith('ctypes.'):
            if not self.inspecting and not self.metadata_read:self.reject('AUDIT_INSPECTOR_SCOPE')
            if event=='ctypes.dlopen' and args[0] not in (None,'/usr/lib/libSystem.B.dylib'):self.reject('AUDIT_LIBRARY_BINDING')
            if event=='ctypes.dlsym' and args[1] not in ({'sysctl'} if self.inspecting else METADATA_SYMBOLS):self.reject('AUDIT_SYMBOL_BINDING')
            if event=='ctypes.set_errno' and args!=(0,):self.reject('AUDIT_ERRNO_RESET')
            if event=='ctypes.create_string_buffer' and args[1]>1024*1024:self.reject('AUDIT_INSPECTION_BOUND')
        elif event=='import' and args[1] is not None:self.path(args[1])
    def install(self):
        require(not self.installed,STAGES[0],'AUDIT_DUPLICATE_INSTALLATION')
        self.originals={'open':os.open,'close':os.close,'dup':os.dup}
        def opened(path,flags,mode=0o777,*,dir_fd=None):
            value=self.lexical(path,dir_fd);self.active.append(value)
            try:fd=self.originals['open'](path,flags,mode,dir_fd=dir_fd)
            finally:self.active.pop()
            self.fds[fd]=value;st=os.fstat(fd);self.fd_identity[fd]=(st.st_dev,st.st_ino);return fd
        def closed(fd):
            try:return self.originals['close'](fd)
            finally:self.fds.pop(fd,None);self.fd_identity.pop(fd,None)
        def duplicate(fd):
            value=self.lexical(fd);result=self.originals['dup'](fd);self.fds[result]=value
            st=os.fstat(result);self.fd_identity[result]=(st.st_dev,st.st_ino);return result
        os.open=opened;os.close=closed;os.dup=duplicate
        self.challenge=digest({'manifest':self.parent,'schema':SCHEMA})
        sys.addaudithook(self);sys.audit('iios.native.audit.challenge',self.challenge)
        require(self.acknowledged,STAGES[0],'AUDIT_INSTALLATION_ACKNOWLEDGED')
        self.finder=ReviewedSourceFinder(self.hashes,lambda:self.stage,controller_module_roots(self.manifest))
        self.finders=(importlib.machinery.BuiltinImporter,importlib.machinery.FrozenImporter,self.finder)
        sys.meta_path=list(self.finders);sys.dont_write_bytecode=True
        self.installed=True
        self.receipt={'schema':SCHEMA,'manifest':self.parent,'installed_before_dispatcher_import':True,
            'source_loader_parent':digest({'policy':'REVIEWED_SOURCE_ONLY_V1','origins':self.hashes,'registry':self.finder.registry_parent}),
            'operations_parent':digest({k:sorted(v) for k,v in OPERATIONS.items()}),'path_policy_parent':self.binding_parent,'signals_permitted':False}
        return dict(self.receipt)
    def verify(self):
        require(self.installed and self.receipt is not None,self.stage,'AUDIT_INSTALLATION_REQUIRED')
        require(tuple(sys.meta_path)==self.finders and sys.dont_write_bytecode is True,self.stage,'SOURCE_LOADER_INSTALLATION')
        require(digest(self.finder.registry)==self.finder.registry_parent and self.finder.registry==module_registry(self.hashes,controller_module_roots(self.manifest)) and self.finder.hashes==self.hashes and self.receipt['source_loader_parent']==digest({'policy':'REVIEWED_SOURCE_ONLY_V1','origins':self.hashes,'registry':self.finder.registry_parent}),self.stage,'SOURCE_LOADER_BINDINGS')
        require(self.receipt['manifest']==self.parent,self.stage,'AUDIT_RECEIPT_PARENT')
        require(self.receipt['operations_parent']==digest({k:sorted(v) for k,v in OPERATIONS.items()}),self.stage,'AUDIT_OPERATION_POLICY_MUTATION')
        require(self.binding_parent==digest({'root':self.root,'paths':sorted(self.paths),'directories':sorted(self.directories),'hashes':self.hashes}),self.stage,'AUDIT_PATH_POLICY_MUTATION')
        self.acknowledged=False;sys.audit('iios.native.audit.challenge',self.challenge)
        require(self.acknowledged,self.stage,'AUDIT_HOOK_REQUIRED')
        return digest(self.receipt)
    def enter(self,stage):
        require(stage in OPERATIONS,self.stage,'AUDIT_STAGE_DECLARED')
        self.verify();self.stage=stage
    @contextmanager
    def launch(self,argv,cwd,environment):
        self.verify()
        require(self.command is None,self.stage,'AUDIT_NESTED_COMMAND_GRANT')
        require('subprocess.Popen' in OPERATIONS[self.stage],self.stage,'AUDIT_STAGE_COMMAND')
        self.command=(argv[0],tuple(argv),cwd,dict(environment))
        self.launching=True
        try:yield
        finally:self.command=None;self.launching=False
    @contextmanager
    def inspection(self):
        self.verify();require(not self.inspecting,self.stage,'AUDIT_NESTED_INSPECTION')
        self.inspecting=True
        try:yield
        finally:self.inspecting=False

    @contextmanager
    def metadata(self):
        self.verify();require(self.stage in METADATA_STAGES,self.stage,'AUDIT_METADATA_STAGE')
        require(not self.metadata_read,self.stage,'AUDIT_NESTED_METADATA')
        self.metadata_read=True
        try:yield
        finally:self.metadata_read=False

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
from iios_native_conductor import STAGES, digest, require, QualificationFailure
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
        self.originals={};self.sealed=();self.last_denial=None
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
            if isinstance(args[0],(str,bytes)) and os.fsdecode(args[0]).endswith(('.pyc','.pyo')):self.reject('AUDIT_UNREVIEWED_BYTECODE')
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
        self.installed=True
        self.receipt={'schema':SCHEMA,'manifest':self.parent,'installed_before_dispatcher_import':True,
            'operations_parent':digest({k:sorted(v) for k,v in OPERATIONS.items()}),'path_policy_parent':self.binding_parent,'signals_permitted':False}
        return dict(self.receipt)
    def verify(self):
        require(self.installed and self.receipt is not None,self.stage,'AUDIT_INSTALLATION_REQUIRED')
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

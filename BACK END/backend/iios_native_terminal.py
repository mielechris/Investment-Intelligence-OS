"""Terminal admission predicates extracted from the accepted Terminal launcher.

No query, hook installation or environment mutation occurs on import. Native
callers supply the pinned, bounded query transport; tests replace that effect.
"""
import errno
import os
from pathlib import PurePosixPath
from iios_native_conductor import QualificationFailure, require, STAGES
from iios_native_admission import terminal_categories

SHELL_ANCESTORS=('/bin/zsh','/bin/bash','/usr/bin/login','login','-zsh','-bash','zsh','bash')
FORBIDDEN_MARKERS=('VSCODE_PID','VSCODE_IPC_HOOK_CLI','CODEX_THREAD_ID','CODEX_SANDBOX_NETWORK_DISABLED')
FORBIDDEN_COMPONENTS=frozenset(('keychains','credentials','ledger','ledgers','.ssh','.aws'))


def ancestor(command,terminal):
    """Exact accepted predicate; never accepts a matching substring."""
    if command==terminal:return True
    require(command in SHELL_ANCESTORS,STAGES[1],'ANCESTOR_EXECUTABLE','ADMITTED_SHELL_OR_TERMINAL','OTHER')
    return False


def admit_terminal(binding,*,environment,ttys,host,parent_pid,query,clock,deadline):
    terminal_categories(environment.get('TERM_PROGRAM'),ttys,
        any(k in environment for k in FORBIDDEN_MARKERS),host,binding['host'])
    # Only these selector values are retained as equality results. The complete
    # inherited environment is never exported and never passed to a workload.
    require(all(environment.get(k)==v for k,v in binding['selectors'].items()),STAGES[1],'TERMINAL_ENVIRONMENT_BINDING','EXACT','ALTERED')
    seen=set();pid=parent_pid;found=False
    for _ in range(6):
        require(clock()<deadline,STAGES[1],'TERMINAL_ANCESTRY_DEADLINE')
        require(type(pid) is int and pid>1 and pid not in seen,STAGES[1],'TERMINAL_ANCESTRY_PID','NEW_ANCESTOR','MISSING_OR_REUSED')
        seen.add(pid)
        command=query(['/bin/ps','-ww','-p',str(pid),'-o','comm='])
        if ancestor(command,binding['terminal_executable']):found=True;break
        value=query(['/bin/ps','-ww','-p',str(pid),'-o','ppid='])
        require(type(value) is str and value.isascii() and value.isdecimal(),STAGES[1],'TERMINAL_ANCESTRY_PPID','DECIMAL','MALFORMED')
        pid=int(value)
    require(found,STAGES[1],'TERMINAL_ANCESTOR_REQUIRED','PINNED_TERMINAL','MISSING')
    require(clock()<deadline,STAGES[1],'TERMINAL_ANCESTRY_DEADLINE')
    return {'application':True,'tty':True,'markers_absent':True,'host':True,'selectors':True,'ancestry':True}


class AuditBoundary:
    """Fail-closed policy for a serial conductor, not an OS confinement claim.

    The caller admits exact launch tuples in a scoped interval and revokes them
    immediately after Popen. Commands cannot grant filesystem or signal access.
    Native child entrypoints still require their own established restrictions.
    """
    def __init__(self,*,read_paths,write_root,stage):
        self.read_paths=frozenset(read_paths);self.write_root=write_root;self.stage=stage
        self.command=None;self.last_denial=None
    def reject(self,predicate,observed):
        self.last_denial={'stage':self.stage,'predicate':predicate,'expected':'ADMITTED','observed':observed,
                          'exception_subtype':'PermissionError','errno_category':'AUDIT_POLICY'}
        raise QualificationFailure(self.stage,predicate,'ADMITTED',observed,exception='PermissionError',errno_category='AUDIT_POLICY')
    def path(self,value,write=False):
        if not isinstance(value,(str,bytes,os.PathLike)):self.reject('AUDIT_PATH_TYPE','NON_PATH')
        value=os.fsdecode(os.fspath(value));parts=PurePosixPath(value).parts
        if '\x00' in value or '..' in parts or any(p.lower() in FORBIDDEN_COMPONENTS or p.startswith('~') for p in parts):self.reject('AUDIT_PROTECTED_PATH','FORBIDDEN')
        # Descriptor-relative operations require a separately tracked FD policy;
        # never treat an arbitrary relative path as contained.
        if not value.startswith('/'):self.reject('AUDIT_UNBOUND_RELATIVE_PATH','RELATIVE')
        inside=value==self.write_root or value.startswith(self.write_root+'/')
        if (write and not inside) or (not write and not inside and value not in self.read_paths):self.reject('AUDIT_FILE_BOUNDARY','OUTSIDE')
        return value
    def __call__(self,event,args):
        if event.startswith('socket.') or event in ('os.kill','os.killpg','os.system','os.posix_spawn','os.fork','os.forkpty','os.exec'):
            self.reject('AUDIT_FORBIDDEN_EFFECT','FORBIDDEN')
        if event=='subprocess.Popen':
            if self.command is None or (args[0],tuple(args[1]),args[2],args[3])!=self.command:self.reject('AUDIT_COMMAND_BINDING','UNBOUND_COMMAND')
        if event=='open' and not isinstance(args[0],int):
            flags=args[2] or 0;mode=args[1]
            write=bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)) or (isinstance(mode,str) and any(c in mode for c in 'wax+'))
            self.path(args[0],write)
        if event in ('os.remove','os.rmdir','os.rename','os.link','os.symlink','os.chown','os.truncate'):
            self.reject('AUDIT_DESTRUCTIVE_EFFECT','FORBIDDEN')
        if event in ('os.mkdir','os.chmod','os.utime','os.setxattr','os.removexattr'):
            self.path(args[0],True)

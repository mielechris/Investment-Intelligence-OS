"""Explicit enrollment of the exact durable root; never adopt an existing tree."""
import os
from pathlib import Path
import pwd
import stat
from .state import require, publish, decode, directory, file_hash

CHILDREN=('runtime','qualification','evidence')
MARKER='IIOS-NATIVE-V2-ROOT.json'

def expected_root():
    return Path(pwd.getpwuid(os.getuid()).pw_dir)/'Library/IIOS'

def checked(path):
    st=path.lstat()
    require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode),'DURABLE_ALIAS')
    require(st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o700,'DURABLE_OWNER_MODE')
    return dict(device=st.st_dev,inode=st.st_ino)

def binding(*, initialize=False):
    root=expected_root()
    require(root.is_absolute() and not any(' ' in part or part=='..' for part in root.parts),'DURABLE_EXACT_ROOT')
    # Validate ancestors without adopting or chmodding the root.
    for parent in root.parents:
        st=parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and not st.st_mode&0o022,'DURABLE_ANCESTOR')
    if initialize:
        root.mkdir(mode=0o700)  # Existing roots, including empty ones, require review.
        for name in CHILDREN:(root/name).mkdir(mode=0o700)
        value=dict(schema=2,root=str(root),uid=os.getuid(),directories={name:checked(root/name) for name in CHILDREN})
        value['identity']=checked(root)
        publish(root/MARKER,value)
    checked(root)
    marker=root/MARKER;st=marker.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and stat.S_IMODE(st.st_mode)==0o400,'DURABLE_MARKER')
    value=decode(marker.read_bytes())
    require(value.get('schema')==2 and value.get('root')==str(root) and value.get('uid')==os.getuid(),'DURABLE_BINDING')
    require(value.get('identity')==checked(root) and set(value.get('directories',{}))==set(CHILDREN),'DURABLE_IDENTITY')
    for name in CHILDREN:require(value['directories'][name]==checked(root/name),'DURABLE_CHILD_IDENTITY')
    return dict(value,marker_sha256=file_hash(marker))

def contained(path, bound):
    require(binding()==bound,'DURABLE_BINDING_CHANGED')
    path=Path(path);root=Path(bound['root'])
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(root) and path!=root,'DURABLE_ESCAPE')
    current=root
    for part in path.relative_to(root).parts:
        current=current/part
        if not current.exists() and not current.is_symlink():current.mkdir(mode=0o700)
        checked(current)
    return path

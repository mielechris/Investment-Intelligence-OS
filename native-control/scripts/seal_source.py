#!/usr/bin/env python3
"""Make the already-verified source checkout owner-read-only without following links."""
import argparse
import os
from pathlib import Path
import stat

def require(value,code):
    if not value:raise ValueError(code)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);root=Path(parser.parse_args().source).resolve(strict=True)
    require(root.is_dir() and not root.is_symlink(),'SOURCE_ROOT')
    paths=sorted(root.rglob('*'),key=lambda path:len(path.parts),reverse=True)
    for path in paths:
        if '.git' in path.relative_to(root).parts:continue
        st=path.lstat();require(not stat.S_ISLNK(st.st_mode),'SOURCE_SYMLINK')
        if stat.S_ISREG(st.st_mode):path.chmod(0o500 if st.st_mode&0o111 else 0o400)
        elif stat.S_ISDIR(st.st_mode):path.chmod(0o500)
        else:raise ValueError('SOURCE_SPECIAL_FILE')
    root.chmod(0o500)
    print('SOURCE_READ_ONLY')

if __name__=='__main__':main()

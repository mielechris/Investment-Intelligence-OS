"""Fixed resource-seal delta; no signature claims derived from a hash alone."""
DERIVED_CODE=(
 'lib/python3.14/site-packages/charset_normalizer/cd.cpython-314-darwin.so',
 'lib/python3.14/site-packages/charset_normalizer/md.cpython-314-darwin.so',
 'lib/python3.14/site-packages/google/_upb/_message.abi3.so',
 'lib/python3.14/site-packages/grpc/_cython/cygrpc.cpython-314-darwin.so',
)
SEAL_FILES=frozenset((*DERIVED_CODE,'Python','_CodeSignature/CodeResources'))
def need(v,c):
    if not v:raise ValueError(c)
def verify_seal_delta(before,after,receipt):
    a={r['path']:r for r in before['files']};b={r['path']:r for r in after['files']}
    need(len(a)==len(before['files']) and len(b)==len(after['files']) and set(a)==set(b) and SEAL_FILES<=set(a),'SEAL_FILE_SET')
    need(before['metadata']==after['metadata'],'SEAL_METADATA')
    need({k:v for k,v in before.items() if k not in ('files','metadata')}=={k:v for k,v in after.items() if k not in ('files','metadata')},'SEAL_IDENTITY')
    for name in a:
        if name in SEAL_FILES:
            need(a[name]['mode']==b[name]['mode'] and b[name]==receipt['derived_files'][name] and a[name]==receipt['original_files'][name],'SEAL_IDENTITY')
        else:need(a[name]==b[name],'SEAL_UNEXPECTED_MUTATION')
    need(set(receipt['derived_files'])==set(receipt['original_files'])==SEAL_FILES,'SEAL_FILE_SET')
def read_owned_json(path,limit):
    import os,stat,json
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1 and stat.S_IMODE(before.st_mode)==0o400 and 0<before.st_size<=limit,'SEAL_RECORD_IDENTITY')
        out=bytearray()
        while len(out)<before.st_size:
            b=os.read(fd,min(65536,before.st_size-len(out)));need(bool(b),'SEAL_RECORD_SHORT');out.extend(b)
        key=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns,x.st_mode,x.st_uid,x.st_nlink)
        need(not os.read(fd,1) and key(before)==key(os.fstat(fd))==key(os.stat(path,follow_symlinks=False)),'SEAL_RECORD_RACE')
        raw=bytes(out)
        need(raw.endswith(b'\n') and not raw.endswith((b'\n\n',b'\r\n')),'SEAL_RECORD_TERMINAL_LF')
        value=json.loads(raw)
        from truth_spine_contract import canonical
        need(canonical(value)==raw,'SEAL_RECORD_CANONICAL')
        return value,raw
    finally:os.close(fd)

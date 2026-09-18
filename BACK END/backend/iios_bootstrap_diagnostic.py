"""Bounded discovery only. No bootstrap/reference acceptance is issued here."""
import hashlib
import json
import re
import struct

MAX_IMAGES = 4096
MAX_REPORT = 8 * 1024 * 1024
FALSE = dict(bootstrap_accepted=False, production_qualified=False, provider_access=False,
             credential_access=False, broker_connected=False, paper_order_permission=False,
             trade_execution_permission=False, live_execution=False)
IMPORTS = ('os','time','select','json','hashlib','ssl','ctypes','sysconfig','zipfile',
           'tarfile','shutil','tempfile','pathlib','_sqlite3','_bz2','_lzma','zlib','_tkinter')


def need(value, code):
    if not value:
        raise ValueError(code)


def mapped_header(raw, address, slide, allow_dyld=False, cache_pin=None):
    need(type(raw) is bytes and 32 <= len(raw) <= 65568, 'HEADER_BOUND')
    magic,cpu,sub,kind,count,total,flags,reserved = struct.unpack_from('<8I',raw)
    need(magic == 0xfeedfacf and cpu == 0x100000c and (kind in (2,6,8) or (allow_dyld and kind==7)), 'HEADER_ARCH_KIND')
    need(0 < count <= 512 and total == len(raw)-32, 'HEADER_COMMAND_BOUND')
    cursor=32;identity=None;segments=[]
    for _ in range(count):
        need(cursor+8<=len(raw),'COMMAND_TRUNCATED')
        cmd,size=struct.unpack_from('<II',raw,cursor)
        need(size>=8 and size%8==0 and cursor+size<=len(raw),'COMMAND_SIZE')
        if cmd==0x1b:
            need(size==24 and identity is None,'UUID_COMMAND')
            identity=raw[cursor+8:cursor+24].hex()
        if cmd==0x19:
            need(size>=72,'SEGMENT_SIZE')
            name,vm,sizevm,offset,sizefile,maxprot,prot,nsects,segflags=struct.unpack_from('<16sQQQQiiII',raw,cursor+8)
            need(size==72+80*nsects and 0<=sizefile<=sizevm,'SEGMENT_LAYOUT')
            actual=vm+slide
            need(0<=actual<2**64 and actual+sizevm<=2**64,'SEGMENT_MAPPING')
            segments.append(dict(name=name.rstrip(b'\0').decode('ascii'),vmaddr=vm,
                address=actual,vmsize=sizevm,file_offset=offset,file_size=sizefile,
                max_protection=maxprot,initial_protection=prot))
        cursor+=size
    need(cursor==len(raw) and identity is not None and identity!='0'*32,'UUID_MISSING')
    expected_offset=0
    if cache_pin is not None:
        need(type(cache_pin) is dict and set(cache_pin)=={'address','file_offset','sha256','cache_file'},'CACHE_HEADER_PIN')
        need(address-slide==cache_pin['address'] and hashlib.sha256(raw).hexdigest()==cache_pin['sha256'],'CACHE_HEADER_IDENTITY')
        expected_offset=cache_pin['file_offset']
        need(type(expected_offset) is int and expected_offset>0,'CACHE_HEADER_OFFSET')
    need(any(s['address']==address and s['file_offset']==expected_offset and s['file_size']>=len(raw)
             for s in segments),'HEADER_MAPPING')
    return dict(file_type=kind,uuid=identity,header_sha256=hashlib.sha256(raw).hexdigest(),segments=segments)


def review_scans(first, second, catalog, cache_uuids, expected_cache, expected=None):
    need(type(first) is list and type(second) is list and 0<len(first)<=MAX_IMAGES,'COUNT_BOUND')
    need(first==second,'SCAN_MISSING_ADDITIONAL_SUBSTITUTED_OR_REORDERED')
    need(cache_uuids==[expected_cache,expected_cache],'CACHE_IDENTITY')
    paths=set();addresses=set()
    for index,row in enumerate(first):
        need(type(row) is dict and set(row)=={'index','path','uuid','address','slide','kind','backing','header_sha256','segments','file_type'} and row['index']==index,'ORDER')
        path=row['path'];address=row['address']
        need(path not in paths and address not in addresses,'DUPLICATE')
        paths.add(path);addresses.add(address)
        need(path in catalog,'UNREVIEWED_IMAGE')
        pin=catalog[path]
        need(row['file_type'] in (2,6,8) or (row['file_type']==7 and path=='/usr/lib/dyld'),'IMAGE_KIND')
        need(row['uuid']==pin['uuid'] and row['kind']==pin['kind'],'SUBSTITUTED_IMAGE')
        need(row['backing']==pin['backing'],'BACKING_IDENTITY')
        if pin['kind']=='APPLE_SIGNED_CACHE':
            cp=pin.get('header_mapping');need(type(cp) is dict,'CACHE_HEADER_PIN')
            need(row['header_sha256']==cp['sha256'] and row['address']-row['slide']==cp['address'],'CACHE_HEADER_IDENTITY')
            need(any(s['address']==row['address'] and s['file_offset']==cp['file_offset'] for s in row['segments']),'CACHE_HEADER_MAPPING')
        need(type(address) is int and 0<address<2**64 and type(row['slide']) is int,'MAPPING')
        need(re.fullmatch('[0-9a-f]{64}',row['header_sha256']) is not None,'HEADER_HASH')
        need(type(row['segments']) is list and row['segments'],'SEGMENTS')
    if expected is not None:
        need([(x['path'],x['uuid'],x['kind'],x['backing']) for x in first]==expected,'EXACT_REFERENCE_MEMBERSHIP')
    return len(first)


def run(binding):
    # The generated entrypoint installs the read/effect audit before this module body.
    import sys
    for name in IMPORTS:
        __import__(name)
    import ctypes, time, os
    need(sys.executable==binding['interpreter'] and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'INTERPRETER_SCOPE')
    need(sys.version_info[:3]==(3,14,7),'INTERPRETER_VERSION')
    started=time.monotonic();deadline=started+90
    catalog=binding['catalog'];lib=ctypes.CDLL(None)
    count=lib._dyld_image_count;count.restype=ctypes.c_uint32;count.argtypes=[]
    name=lib._dyld_get_image_name;name.restype=ctypes.c_char_p;name.argtypes=[ctypes.c_uint32]
    header=lib._dyld_get_image_header;header.restype=ctypes.c_void_p;header.argtypes=[ctypes.c_uint32]
    slide=lib._dyld_get_image_vmaddr_slide;slide.restype=ctypes.c_int64;slide.argtypes=[ctypes.c_uint32]
    cache=lib._dyld_get_shared_cache_uuid;cache.restype=ctypes.c_bool;cache.argtypes=[ctypes.c_void_p]
    hashlib.sha256(b'warm').hexdigest()
    def cache_uuid():
        value=(ctypes.c_ubyte*16)();need(cache(value),'CACHE_UUID_UNAVAILABLE');return bytes(value).hex()
    def scan():
        n=count();need(0<n<=MAX_IMAGES,'COUNT_BOUND');rows=[]
        for index in range(n):
            need(time.monotonic()<deadline,'SCAN_DEADLINE')
            rawname=name(index);address=header(index);delta=slide(index)
            need(rawname is not None and 0<len(rawname)<=4096 and address,'IMAGE_MISSING')
            path=rawname.decode('utf-8');need(path.startswith('/') and '\0' not in path,'IMAGE_PATH')
            prefix=ctypes.string_at(address,32);ncmds,total=struct.unpack_from('<II',prefix,16)
            need(0<ncmds<=512 and 0<total<=65536,'HEADER_BOUND')
            pin=catalog.get(path,{'kind':'UNREVIEWED','backing':None})
            raw=ctypes.string_at(address,32+total)
            try:
                value=mapped_header(raw,address,delta,allow_dyld=path=='/usr/lib/dyld',cache_pin=pin.get('header_mapping') if pin['kind']=='APPLE_SIGNED_CACHE' else None)
            except ValueError as error:
                sys.stderr.write(json.dumps(dict(error=str(error),index=index,path=path,address=address,slide=delta,header_sha256=hashlib.sha256(raw).hexdigest()))+'\n')
                raise
            rows.append(dict(index=index,path=path,address=address,slide=delta,kind=pin['kind'],backing=pin['backing'],**value))
        need(count()==n,'SCAN_INCOMPLETE')
        return rows
    cache_first=cache_uuid();first=scan();second=scan();cache_second=cache_uuid()
    errors=[]
    try:
        need(first and first[0]['path']==binding['interpreter'] and first[0]['file_type']==2,'MAIN_EXECUTABLE_MISSING')
        review_scans(first,second,catalog,[cache_first,cache_second],binding['cache_uuid'])
    except ValueError as error:
        errors.append(str(error))
    measured=len(first)
    origins=[]
    for module,obj in sorted(sys.modules.copy().items()):
        origin=getattr(obj,'__file__',None)
        if origin:
            if origin not in binding['read_files']:
                errors.append('MODULE_ORIGIN');origins.append(dict(module=module,path=origin,sha256=None))
            else:
                origins.append(dict(module=module,path=origin,sha256=hashlib.sha256(open(origin,'rb').read()).hexdigest()))
    need(len(origins)<=512 and time.monotonic()<deadline,'ORIGIN_BOUND')
    result=dict(schema='IIOS_BOOTSTRAP_IMAGE_DISCOVERY_V1',status='REJECTED_DISCOVERY' if errors else 'TWO_MATCHING_SCANS_PENDING_INDEPENDENT_REVIEW',
        validation_errors=sorted(set(errors)),complete_matching_scans=first==second,
        descriptor_parent=binding['descriptor_parent'],boot_session_uuid=binding['boot_session_uuid'],
        source_commit=binding['source_commit'],runtime_root=binding['runtime_root'],imports=list(IMPORTS),
        image_count=measured,image_bound=MAX_IMAGES,scans=[first,second],cache_uuids=[cache_first,cache_second],
        module_origins=origins,cache_backing_files=binding['cache_files'],seconds=time.monotonic()-started,historical_cleanup='NOT_ESTABLISHED',
        mapped_memory_integrity='UNVERIFIED',boot_attestation='UNRESOLVED',**FALSE)
    raw=json.dumps(result,sort_keys=True,separators=(',',':')).encode()+b'\n'
    need(len(raw)<=MAX_REPORT,'REPORT_BOUND')
    sys.stdout.buffer.write(raw);sys.stdout.buffer.flush()
    if errors:raise SystemExit(2)

"""Pure admission of the independently pinned final-runtime identity reference.

This does not discover images, execute a runtime, mint qualification evidence or
turn a bootstrap reference into a production-runtime reference. The expected
ordered image membership is independent input to the accepted dynamic protocol.
"""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from iios_native_conductor import require, STAGES, pin_file

STAGE=STAGES[7]
SCHEMA='SCOPED_FINAL_RUNTIME_IMAGE_REFERENCE_V1'
HEX=re.compile(r'[0-9a-f]{64}\Z')
UUID=re.compile(r'[0-9a-f]{32}\Z')


def required_imports(bootstrap_imports,policy):
    """The approved projection keeps the bootstrap's relative import ordering."""
    forbidden=policy['forbidden_import_roots']
    return [name for name in bootstrap_imports if name.split('.')[0] not in forbidden]


def conflicts(reference,policy):
    """Sanitized fixed categories only; no observation or permission inference."""
    imports=reference.get('imports',[]);rows=reference.get('ordered_rows',[])
    forbidden=set(policy['forbidden_import_roots'])
    excluded=policy['excluded_prefixes']
    bad_imports=sum(type(n) is str and n.split('.')[0] in forbidden for n in imports)
    bad_images=sum(type(r) is dict and type(r.get('file')) is str and any(r['file']==p or r['file'].startswith(p+'/') for p in excluded) for r in rows)
    return {'scope':'FINAL_RUNTIME_REFERENCE_COMPATIBILITY_ONLY',
            'schema_matches':reference.get('schema')==SCHEMA,
            'forbidden_import_count':bad_imports,'excluded_private_image_count':bad_images,
            'dynamic_acceptance':False,'native_executed':False}


def validate_reference(reference,*,source,root,host,layout_parent,policy,imports,now):
    require(type(reference) is dict and reference.get('schema')==SCHEMA,STAGE,'FINAL_RUNTIME_REFERENCE_SCOPE','FINAL_RUNTIME','OTHER_SCOPE')
    expected={'schema','source_commit','runtime_root','host','layout_parent','imports','ordered_rows','expected_count',
              'cache_uuid','independent_catalog_parent','membership_review_parent','expires_at'}
    require(set(reference)==expected,STAGE,'FINAL_RUNTIME_REFERENCE_SCHEMA')
    require(reference['source_commit']==source and reference['runtime_root']==root and reference['host']==host and reference['layout_parent']==layout_parent,
            STAGE,'FINAL_RUNTIME_REFERENCE_PARENTS','EXACT','MISMATCH')
    require(type(root) is str and root.startswith('/') and str(PurePosixPath(root))==root and '..' not in PurePosixPath(root).parts,STAGE,'FINAL_RUNTIME_REFERENCE_ROOT')
    require(type(reference['expires_at']) in (int,float) and now<reference['expires_at'],STAGE,'FINAL_RUNTIME_REFERENCE_EXPIRED')
    require(reference['imports']==imports and type(imports) is list and imports and len(set(imports))==len(imports),STAGE,'FINAL_RUNTIME_IMPORT_ORDER')
    c=conflicts(reference,policy)
    require(c['forbidden_import_count']==c['excluded_private_image_count']==0,STAGE,'FINAL_RUNTIME_REFERENCE_EXCLUDED_COMPONENT','ABSENT','PRESENT')
    rows=reference['ordered_rows'];count=reference['expected_count']
    require(type(count) is int and 0<count<=4096 and type(rows) is list and len(rows)==count,STAGE,'FINAL_RUNTIME_IMAGE_COUNT')
    paths=set()
    for index,row in enumerate(rows):
        require(type(row) is dict and set(row)=={'id','path','uuid','kind','file','sha256','size'} and row['id']==index,STAGE,'FINAL_RUNTIME_IMAGE_ROW')
        path=row['path'];identity=row['uuid']
        require(type(path) is str and path.startswith('/') and str(PurePosixPath(path))==path and '..' not in PurePosixPath(path).parts and path not in paths,STAGE,'FINAL_RUNTIME_IMAGE_PATH')
        require(type(identity) is str and UUID.fullmatch(identity) and identity!='0'*32,STAGE,'FINAL_RUNTIME_IMAGE_UUID')
        paths.add(path)
        if row['kind']=='PRIVATE_SEALED':
            name=row['file']
            require(type(name) is str and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and path==root+'/'+name,STAGE,'FINAL_RUNTIME_PRIVATE_IMAGE_ROOT')
            require(type(row['sha256']) is str and HEX.fullmatch(row['sha256']) and type(row['size']) is int and row['size']>0,STAGE,'FINAL_RUNTIME_PRIVATE_IMAGE_PIN')
        else:
            require(row['kind']=='SIGNED_OS_CACHE' and path.startswith(('/usr/lib/','/System/Library/')),STAGE,'FINAL_RUNTIME_PLATFORM_IMAGE_SCOPE')
    require(type(reference['cache_uuid']) is str and UUID.fullmatch(reference['cache_uuid']) and reference['cache_uuid']!='0'*32,STAGE,'FINAL_RUNTIME_CACHE_UUID')
    for key in ('independent_catalog_parent','membership_review_parent'):
        require(type(reference[key]) is str and HEX.fullmatch(reference[key]),STAGE,'FINAL_RUNTIME_REFERENCE_INDEPENDENT_PARENT')
    return reference


def admit_reference(binding,**expectations):
    require(type(binding) is dict and set(binding)=={'path','sha256'},STAGE,'FINAL_RUNTIME_IMAGE_REFERENCE_REQUIRED','INDEPENDENT_FINAL_RUNTIME_REFERENCE','MISSING')
    p=Path(binding['path']);pin_file(p,binding['sha256']);raw=p.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==binding['sha256'],STAGE,'FINAL_RUNTIME_REFERENCE_READ_MUTATION')
    return validate_reference(json.loads(raw),**expectations)

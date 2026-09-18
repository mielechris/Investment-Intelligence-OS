"""Pure pinned profile admission shared by prelaunch and the lifecycle stage."""
import hashlib
import json
import re
from pathlib import Path
from iios_native_conductor import require,digest,pin_file,STAGES

def need(value,predicate):require(value,STAGES[8],predicate)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bound_json(binding):
    pin_file(binding['path'],binding['sha256']);raw=Path(binding['path']).read_bytes()
    need(sha(raw)==binding['sha256'],'LIFECYCLE_PROFILE_REVIEW_MUTATION');return json.loads(raw)

# Revision of the existing default-deny qualification profile. Only the exact
# process-image and self-inspection tools are added; no external endpoint,
# credential location, provider route or general executable subtree is granted.
RULES=(('version','1'),('deny','default'),('allow','file-read-metadata'),
    ('allow','file-read*',('subpath','@RUNTIME@'),('subpath','@RELEASE@'),('subpath','@CONTROL@'),('subpath','@OUTPUT@'),
     ('literal','@CONFIG@'),('literal','@DRIVER@'),('subpath','/System/Library'),('subpath','/usr/lib'),
     ('literal','/bin/ps'),('literal','/usr/sbin/lsof'),
     ('literal','/dev/null'),('literal','/dev/urandom'),('literal','/dev/random')),
    ('allow','file-write*',('subpath','@OUTPUT@')),
    ('allow','process-exec',('literal','@INTERPRETER@'),('literal','@PROCESS_IMAGE@'),('literal','/bin/ps'),('literal','/usr/sbin/lsof')),
    ('allow','sysctl-read'),('allow','network-outbound',('remote','ip','@ENDPOINT@')),
    ('allow','network-inbound',('local','ip','@ENDPOINT@')),('allow','network-bind',('local','ip','@ENDPOINT@')))

def template_bytes():
    def render(value):
        if isinstance(value,tuple):return '('+' '.join(render(x) for x in value)+')'
        return json.dumps(value) if value.startswith('/') else value
    return ('\n'.join(render(row) for row in RULES)+'\n').encode('ascii')

def tokens(raw):
    need(type(raw) is bytes and len(raw)<=32768,'LIFECYCLE_PROFILE_SIZE')
    text=raw.decode('ascii');parts=[];end=0
    for match in re.finditer(r';[^\n]*|[()]|"[^"\\]*"|[A-Za-z0-9_@*/.:-]+',text):
        need(not text[end:match.start()].strip(),'LIFECYCLE_PROFILE_SYNTAX');end=match.end()
        if not match[0].startswith(';'):parts.append(match[0])
    need(not text[end:].strip() and len(parts)<=512,'LIFECYCLE_PROFILE_SYNTAX')
    return parts


def reviewed_profile(manifest,d,roots):
    """Fresh-root substitution only, authorized by a separately pinned review."""
    review=bound_json(d['profile_review']);binding=d['profile_template']
    pin_file(binding['path'],binding['sha256']);raw=Path(binding['path']).read_bytes()
    need(sha(raw)==binding['sha256']==review['template_sha256'],'LIFECYCLE_PROFILE_TEMPLATE')
    need(tokens(raw)==tokens(template_bytes()),'LIFECYCLE_PROFILE_OPERATION_ALLOWLIST')
    need(review['scope']=='DISPOSABLE_NATIVE_QUALIFICATION_ONLY' and review['default_deny'] is True and
        review['network']==['127.0.0.1:38493'] and review['credentials'] is False and review['providers'] is False,
        'LIFECYCLE_PROFILE_SCOPE')
    required=['/bin/ps','/usr/sbin/lsof']
    need(all(p in manifest['tool_pins'] for p in required),'LIFECYCLE_PROFILE_TOOL_IDENTITY_MISSING')
    need(review['inspection_tools']=={p:manifest['tool_pins'][p] for p in required},'LIFECYCLE_PROFILE_INSPECTION_TOOLS')
    from iios_native_role_transport import POLICY
    need(review.get('inspector_policy')==POLICY,'LIFECYCLE_INSPECTOR_POLICY')
    need(review.get('host')==manifest['terminal_binding']['host'] and review.get('os_build')==manifest['os_build'],'LIFECYCLE_PROFILE_OS_BINDING')
    rendered=render_profile(raw,manifest,roots,review['substitutions'])
    bound=d.get('profile_rendered',{})
    need(bound.get('sha256')==sha(rendered),'LIFECYCLE_RENDERED_PROFILE_HASH')
    pin_file(bound['path'],bound['sha256'])
    need(Path(bound['path']).read_bytes()==rendered,'LIFECYCLE_RENDERED_PROFILE_BYTES')
    return rendered,digest(review)


def render_profile(raw,manifest,roots,expected_substitutions):
    image=Path(manifest['native']['runtime_acceptance']['image_relative'])
    need(not image.is_absolute() and '..' not in image.parts and str(image)==manifest['native']['runtime_acceptance']['image_relative'],'LIFECYCLE_PROFILE_IMAGE_PATH')
    substitutions={'@PROCESS_IMAGE@':str(Path(roots['runtime'])/image),'@RUNTIME@':roots['runtime'],'@RELEASE@':roots['release'],'@CONTROL@':roots['control'],
        '@OUTPUT@':roots['output'],'@CONFIG@':str(Path(roots['output']).parent/'qualification.json'),'@DRIVER@':str(Path(roots['output']).parent/'conductor-lifecycle.py'),'@INTERPRETER@':roots['runtime']+'/bin/python3.14','@ENDPOINT@':'127.0.0.1:38493'}
    text=raw.decode('ascii');need('(deny default)' in text,'LIFECYCLE_DEFAULT_DENY')
    need(expected_substitutions==sorted(substitutions),'LIFECYCLE_PROFILE_SUBSTITUTIONS')
    for marker,value in substitutions.items():
        need(marker in text and all(c not in value for c in ('"','\\','\n','\r')),'LIFECYCLE_PROFILE_PATH')
        text=text.replace(marker,json.dumps(value))
    need('@' not in text,'LIFECYCLE_PROFILE_UNBOUND_MARKER')
    return text.encode()

"""Non-circular vendor-binary bootstrap recipe admission, no build effects.

Stage zero uses independently reviewed OS archive/Mach-O/signature tools only.
A private, separately qualified vendor interpreter then runs the existing IIOS
assembler. The production output is never needed to create its bootstrap.
"""
import re
from alpha_session_contract import require
from provider_gateway_contract import safe_document, pin, locked_authority
from alpha_observation_launch import lexical

SCHEMA='iios-vendor-bootstrap-recipe-v1'
TOOLS=('/usr/bin/xar','/usr/sbin/pkgutil','/usr/bin/tar','/usr/bin/shasum',
       '/Library/Developer/CommandLineTools/usr/bin/otool',
       '/Library/Developer/CommandLineTools/usr/bin/install_name_tool','/usr/bin/codesign')
STEPS=('VERIFY_VENDOR_AND_TOOLS','INSPECT_ARCHIVE','EXTRACT_BOOTSTRAP_WITH_OS_TOOLS',
       'RELOCATE_WITH_OS_TOOLS','SEAL_BOOTSTRAP','VERIFY_BOOTSTRAP_STATIC_CLOSURE',
       'QUALIFY_FINAL_BOOTSTRAP_DESTINATION','EXTRACT_VERIFIED_WHEELS',
       'RUN_EXISTING_ASSEMBLER','QUALIFY_FINAL_PRODUCTION_DESTINATION')


def validate_recipe(recipe, expected, *, roots, source, vendor_parent, tool_parents, script_parent):
    safe_document(recipe);pin(recipe,expected)
    require(set(recipe)=={'schema','scope','source','roots','vendor_parent','tools','script_parent',
        'steps','dependencies','authority'},'BOOTSTRAP_SCHEMA')
    require(recipe['schema']==SCHEMA and recipe['scope']=='PRIVATE_BUILD_DESIGN_ONLY' and
        recipe['source']==source and re.fullmatch('[0-9a-f]{40}',source),'BOOTSTRAP_SOURCE')
    require(recipe['roots']==roots and set(roots)=={'quarantine','bootstrap','staging','output'},'BOOTSTRAP_ROOTS')
    paths=[lexical(p) for p in roots.values()]
    require(all(not a.is_relative_to(b) and not b.is_relative_to(a)
        for i,a in enumerate(paths) for b in paths[i+1:]),'BOOTSTRAP_ROOT_ALIAS')
    require(recipe['vendor_parent']==vendor_parent and recipe['script_parent']==script_parent and
        recipe['tools']==tool_parents and set(tool_parents)==set(TOOLS),'BOOTSTRAP_PARENTS')
    for value in (vendor_parent,script_parent,*tool_parents.values()):
        require(type(value) is str and re.fullmatch('[0-9a-f]{64}',value),'BOOTSTRAP_PIN')
    require(recipe['steps']==list(STEPS),'BOOTSTRAP_ORDER')
    graph=recipe['dependencies']
    # Exact graph prevents an assembly/output dependency from entering stage zero.
    require(graph=={step:[] if i==0 else [STEPS[i-1]] for i,step in enumerate(STEPS)},'BOOTSTRAP_DEPENDENCIES')
    require(recipe['authority']==locked_authority() and all(v is False for v in recipe['authority'].values()),'BOOTSTRAP_AUTHORITY')
    return {'schema':'iios-bootstrap-recipe-review-v1','scope':'PRIVATE_BUILD_DESIGN_ONLY',
        'recipe_parent':expected,'interpreter':roots['bootstrap']+'/bin/python3.14',
        'assembler_source_parent':script_parent,'production_destination':roots['output']+'/runtime-pilot',
        'status':'RECIPE_BOUND_NOT_EXECUTED','execution_authorized':False,'production_qualified':False,
        'authority':locked_authority()}


def admit_build_control(evidence, expected, *, recipe_parent, bootstrap_manifest_parent,
                        vendor_parent, tools_parent, script_parent, host_parent):
    """Independent acceptance records needed before any Python build script.

    This does not self-generate signature, provenance or native import evidence.
    Failed installed-tool verification cannot be replaced by a supplied PASS.
    """
    safe_document(evidence);pin(evidence,expected)
    require(set(evidence)=={'schema','scope','recipe_parent','bootstrap_manifest_parent','vendor_parent',
        'tools_parent','script_parent','host_parent','checks','authority'},'BUILD_CONTROL_SCHEMA')
    require(evidence['schema']=='iios-reviewed-build-control-v1' and evidence['scope']=='PRIVATE_BUILD_CONTROL_ONLY',
            'BUILD_CONTROL_SCOPE')
    parents=dict(recipe_parent=recipe_parent,bootstrap_manifest_parent=bootstrap_manifest_parent,
        vendor_parent=vendor_parent,tools_parent=tools_parent,script_parent=script_parent,host_parent=host_parent)
    require(all(evidence[k]==v and type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for k,v in parents.items()),
            'BUILD_CONTROL_PARENT')
    required={'vendor_signature','os_tool_trust','complete_closure','immutable_ownership','final_destination_imports',
        'no_historical_dependencies','scrubbed_environment'}
    require(set(evidence['checks'])==required,'BUILD_CONTROL_CHECKS')
    require(all(type(v) is dict and set(v)=={'status','independent_parent'} and v['status']=='ACCEPTED' and
        re.fullmatch('[0-9a-f]{64}',v['independent_parent']) for v in evidence['checks'].values()),'BUILD_CONTROL_UNVERIFIED')
    require(evidence['authority']==locked_authority() and all(v is False for v in evidence['authority'].values()),'BUILD_CONTROL_AUTHORITY')
    return {'status':'REVIEW_PARENTS_BOUND','production_qualified':False,'authority':locked_authority()}

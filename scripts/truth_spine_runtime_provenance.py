"""Fresh runtime assembly from independently pinned toolchain files, not old packages."""
from pathlib import Path
import os
import stat

from truth_spine_contract import canonical, seal, verified
from truth_spine_lineage import check_pin, contained, copy_pinned, file_hash, require, safe_path, write_new


def validate_inputs(spec):
    require(set(spec) == {'files','platform_dependencies','interpreter','process_executable'}, 'RUNTIME_INPUT_SCHEMA')
    require(spec['files'] and spec['platform_dependencies'] and spec['interpreter'] == 'bin/python',
            'COMPLETE_RUNTIME_PINS_REQUIRED')
    names = [r['target'] for r in spec['files']]
    require(len(names) == len(set(names)) and 'bin/python' in names and 'pyvenv.cfg' in names
            and 'runtime-manifest.json' not in names, 'RUNTIME_GRAPH_REQUIRED')
    for row in spec['files']:
        rel = Path(row['target'])
        require(not rel.is_absolute() and '..' not in rel.parts and rel.parts, 'RUNTIME_RELATIVE_PATH')
        p = Path(row['pin']['path'])
        require(not any('acceptance-sb' in s or 'runtime-template' in s for s in p.parts)
                and 'Application Support' not in p.parts, 'OLD_RUNTIME_REJECTED')
        require(row['mode'] in (0o400,0o500), 'RUNTIME_MODE')
        check_pin(row['pin'])
    for row in spec['platform_dependencies']:
        check_pin(row)
    check_pin(spec['process_executable'])
    require(spec['process_executable'] in spec['platform_dependencies'], 'PROCESS_EXECUTABLE_PIN_REQUIRED')
    return spec


def assemble(root, spec, commit, intent):
    validate_inputs(spec)
    root = safe_path(root)
    runtime = root/'runtime'
    runtime.mkdir(mode=0o700)
    rows = []
    for row in spec['files']:
        target = contained(runtime,row['target'])
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        copy_pinned(row['pin'],runtime,row['target'])
        # This file was exclusively created by this operation, never preexisting evidence.
        os.chmod(target,row['mode'])
        rows.append({'path':row['target'],'bytes':row['pin']['bytes'],
                     'sha256':row['pin']['sha256'],'mode':row['mode']})
    rows.sort(key=lambda r:r['path'])
    interpreter = next(r for r in rows if r['path']=='bin/python')
    require(interpreter['mode'] == 0o500, 'INTERPRETER_EXECUTABLE_REQUIRED')
    record = seal({'schema':'iios-fresh-historical-runtime-v1','source_commit':commit,
                   'package_generation':intent,'installed_root':str(root),'runtime_relative':'runtime',
                   'interpreter_relative':'runtime/bin/python','interpreter_sha256':interpreter['sha256'],
                   'runtime_id':'historical-runtime-'+intent[:24], 'files':rows,
                   'process_executable':spec['process_executable']['path'],
                   'process_executable_hash':spec['process_executable']['sha256'],
                   'platform_dependencies':spec['platform_dependencies']})
    write_new(root,'runtime/runtime-manifest.json',canonical(record))
    return record


def verify_runtime(root, manifest, runtime):
    verified(runtime)
    root = safe_path(root)
    require(runtime['schema']=='iios-fresh-historical-runtime-v1' and
            runtime['source_commit']==manifest['source_base'] and runtime['installed_root']==str(root) and
            runtime['package_generation']==manifest['lineage']['package_generation'] and
            runtime['runtime_relative']=='runtime' and runtime['interpreter_relative']=='runtime/bin/python' and
            manifest['runtime_root']==str(root/'runtime'), 'RUNTIME_INSTALLATION_MISMATCH')
    require(runtime['interpreter_sha256']==manifest['interpreter_hash'], 'INTERPRETER_PIN_MISMATCH')
    names = [r['path'] for r in runtime['files']]
    require(len(names)==len(set(names)), 'DUPLICATE_RUNTIME_FILE')
    actual = set()
    for p in (root/'runtime').rglob('*'):
        require(not p.is_symlink(), 'RUNTIME_SYMLINK')
        if p.is_file(): actual.add(p.relative_to(root/'runtime').as_posix())
    require(actual==set(names)|{'runtime-manifest.json'}, 'RUNTIME_INVENTORY_MISMATCH')
    for row in runtime['files']:
        p=contained(root/'runtime',row['path'])
        require(p.stat().st_size==row['bytes'] and stat.S_IMODE(p.stat().st_mode)==row['mode'] and
                file_hash(p)==row['sha256'], 'RUNTIME_FILE_MISMATCH')
    for row in runtime['platform_dependencies']:
        check_pin(row)
    require(any(row['path']==runtime['process_executable'] and row['sha256']==runtime['process_executable_hash']
                for row in runtime['platform_dependencies']), 'PROCESS_EXECUTABLE_PIN_REQUIRED')
    require(file_hash(contained(root,runtime['interpreter_relative']))==runtime['interpreter_sha256'],
            'INTERPRETER_PIN_MISMATCH')
    return contained(root,runtime['interpreter_relative'])
